from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.engine import Engine

from app.config import settings
from app.services.broker.base import ChainSource
from app.services.event_store import append_event
from app.services.market_hours import empty_quotes_reason
from app.services.options_chain_planner import plan_scan_scope
from app.services.options_chain_store import (
    coerce_utc_datetime,
    get_contracts,
    get_metadata,
    get_scan_status,
    invalidate_mock_scanner_cache,
    recover_stuck_scan_if_needed,
    replace_contracts,
    update_scan_status,
    upsert_metadata,
)

_scan_locks: dict[str, threading.Lock] = {}
_scan_lock_guard = threading.Lock()
log = logging.getLogger(__name__)


def _lock_for(symbol: str) -> threading.Lock:
    sym = symbol.upper()
    with _scan_lock_guard:
        if sym not in _scan_locks:
            _scan_locks[sym] = threading.Lock()
        return _scan_locks[sym]


def reset_scan_lock(symbol: str) -> None:
    sym = symbol.strip().upper()
    with _scan_lock_guard:
        _scan_locks[sym] = threading.Lock()


def _row_has_quotes(row: dict[str, Any]) -> bool:
    bid = float(row.get("bid") or 0)
    ask = float(row.get("ask") or 0)
    mid = float(row.get("mid") or 0)
    return bid > 0 or ask > 0 or mid > 0


def _classify_row(row: dict[str, Any], cfg: Any) -> dict[str, Any]:
    bid = float(row.get("bid") or 0)
    ask = float(row.get("ask") or 0)
    mid = float(row.get("mid") or 0)
    if mid <= 0 and bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        row["mid"] = round(mid, 4)
    if bid > 0 and ask > 0 and mid > 0:
        spread_pct = (ask - bid) / mid
    else:
        spread_pct = 0.0
    row["spread_pct"] = round(max(0.0, spread_pct), 4)
    volume = int(row.get("volume") or 0)
    oi = int(row.get("open_interest") or 0)
    reasons: list[str] = []
    if bid <= 0 and ask <= 0 and mid <= 0:
        reasons.append("no live quotes (market closed or illiquid)")
    if bid > 0 and ask > 0 and spread_pct > cfg.max_spread_pct:
        reasons.append(f"spread {spread_pct:.1%} > max {cfg.max_spread_pct:.1%}")
    if oi > 0 and oi < cfg.min_open_interest:
        reasons.append(f"OI {oi} < min {cfg.min_open_interest}")
    if volume > 0 and volume < cfg.min_volume:
        reasons.append(f"volume {volume} < min {cfg.min_volume}")
    if reasons:
        row["status"] = "reject"
        row["rejection_reason"] = "; ".join(reasons)
    else:
        row["status"] = "usable"
        row["rejection_reason"] = None
    return row


class OptionsChainScanner:
    def __init__(
        self,
        *,
        engine: Engine,
        broker: Any,
        trace_fn: Callable[[], tuple[str, str]],
        broker_connected_fn: Callable[[], bool],
    ) -> None:
        self._engine = engine
        self._broker = broker
        self._trace = trace_fn
        self._broker_connected = broker_connected_fn

    def _prior_usable_count(self, symbol: str) -> int:
        return sum(1 for row in get_contracts(self._engine, symbol) if row.get("status") == "usable")

    def _preserve_cached_chain(
        self,
        *,
        symbol: str,
        reason: str,
        underlying_price: float | None = None,
        chain_source: ChainSource | None = None,
    ) -> bool:
        sym = symbol.strip().upper()
        existing = get_contracts(self._engine, sym)
        if not existing:
            return False
        prior_usable = sum(1 for row in existing if row.get("status") == "usable")
        prior_status = get_scan_status(self._engine, sym) or {}
        prior_source = str(prior_status.get("chain_source") or "")
        if settings.broker_backend == "tws" and prior_source == "mock":
            return False
        fields: dict[str, Any] = {
            "scanner_status": "stale",
            "last_error": reason[:500],
            "contracts_usable": prior_usable,
            "contracts_scanned": int(prior_status.get("contracts_scanned") or len(existing)),
            "contracts_rejected": int(prior_status.get("contracts_rejected") or max(0, len(existing) - prior_usable)),
        }
        if chain_source is not None:
            fields["chain_source"] = chain_source
        if underlying_price is not None:
            fields["underlying_price"] = underlying_price
        update_scan_status(self._engine, sym, **fields)
        return True

    def refresh_metadata(self, symbol: str) -> bool:
        sym = symbol.strip().upper()
        cfg = settings.options_chain
        if not cfg.is_scanner_symbol(sym):
            return False
        if not self._broker_connected():
            prior_status = get_scan_status(self._engine, sym) or {}
            prior_source = str(prior_status.get("chain_source") or "")
            if get_contracts(self._engine, sym) and prior_source == "broker":
                update_scan_status(
                    self._engine,
                    sym,
                    last_error="broker disconnected",
                )
                return False
            update_scan_status(
                self._engine,
                sym,
                scanner_status="failed",
                last_error="broker disconnected",
            )
            self._emit_failure(sym, "metadata", "broker disconnected")
            return False
        try:
            meta = self._broker.fetch_secdef_metadata(sym)
            if not meta:
                raise RuntimeError("empty secdef metadata")
            upsert_metadata(self._engine, meta)
            diag = meta.get("diagnostics")
            if diag:
                log.info(
                    "secdef metadata %s conid=%s chains=%s exchange=%s tradingClass=%s",
                    sym,
                    diag.get("underlying_conid"),
                    diag.get("chains_returned"),
                    diag.get("selected_exchange"),
                    diag.get("selected_trading_class"),
                )
            corr, caus = self._trace()
            append_event(
                engine=self._engine,
                event_type="OptionsChainMetadataRefreshed",
                aggregate_type="options_chain",
                aggregate_id=sym,
                producer="options_chain_scanner",
                payload={**meta, "refreshed_at": datetime.now(UTC).isoformat()},
                schema_ref="bd.events.options_chain_metadata_refreshed.v1",
                idempotency_key=f"scanner:OptionsChainMetadataRefreshed:{sym}:{datetime.now(UTC).strftime('%Y%m%d%H%M')}",
                correlation_id=corr,
                causation_id=caus,
            )
            return True
        except Exception as exc:
            update_scan_status(self._engine, sym, scanner_status="failed", last_error=str(exc)[:500])
            self._emit_failure(sym, "metadata", str(exc))
            return False

    def run_quote_scan(self, symbol: str) -> bool:
        sym = symbol.strip().upper()
        cfg = settings.options_chain
        if not cfg.is_scanner_symbol(sym):
            return False
        if recover_stuck_scan_if_needed(self._engine, sym):
            with _scan_lock_guard:
                _scan_locks[sym] = threading.Lock()
        lock = _lock_for(sym)
        if not lock.acquire(blocking=False):
            return False
        scan_run_id = f"ocs_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        chain_source: ChainSource = "none"
        try:
            if not self._broker_connected():
                has_cache = bool(get_contracts(self._engine, sym))
                if has_cache:
                    update_scan_status(
                        self._engine,
                        sym,
                        scanner_status="stale",
                        last_error="broker disconnected; serving last cache",
                    )
                else:
                    update_scan_status(
                        self._engine,
                        sym,
                        scanner_status="failed",
                        last_error="broker disconnected",
                    )
                return False

            if settings.broker_backend == "tws":
                if invalidate_mock_scanner_cache(self._engine, sym):
                    log.info("scan %s cleared stale mock cache before broker rescan", sym)
                    self.refresh_metadata(sym)

            update_scan_status(
                self._engine,
                sym,
                scanner_status="scanning",
                last_scan_started_at=now,
                scan_run_id=scan_run_id,
                last_error=None,
            )

            meta = get_metadata(self._engine, sym)
            if not meta:
                self.refresh_metadata(sym)
                meta = get_metadata(self._engine, sym)
            if not meta:
                raise RuntimeError("no cached metadata")

            snap = self._broker.market_snapshot(sym)
            spot = float(snap["last"]) if snap else 700.0
            all_strikes = [float(s) for s in meta.get("strikes") or []]
            expiries = [str(e) for e in meta.get("expiries") or []]
            plan = plan_scan_scope(
                spot=spot,
                all_expiries=expiries,
                all_strikes=all_strikes,
                cfg=cfg,
            )
            selected_expiries = plan.expiries
            selected_strikes = plan.strikes
            strike_low = plan.strike_low
            strike_high = plan.strike_high
            scan_notes = list(plan.truncation_notes)
            contracts_planned = plan.planned_contracts

            if not selected_expiries or not selected_strikes:
                raise RuntimeError("empty scan plan (no expiries or strikes in DTE/strike window)")

            update_scan_status(
                self._engine,
                sym,
                scanner_status="scanning",
                last_scan_started_at=now,
                scan_run_id=scan_run_id,
                last_error=None,
                underlying_price=spot,
                strike_low=strike_low,
                strike_high=strike_high,
                expiries_selected=selected_expiries,
                contracts_planned=contracts_planned,
            )

            corr, caus = self._trace()
            append_event(
                engine=self._engine,
                event_type="OptionsChainScanStarted",
                aggregate_type="options_chain",
                aggregate_id=sym,
                producer="options_chain_scanner",
                payload={
                    "symbol": sym,
                    "scan_run_id": scan_run_id,
                    "started_at": now.isoformat(),
                    "planned_contracts": contracts_planned,
                    "expiries": selected_expiries,
                    "strike_low": strike_low,
                    "strike_high": strike_high,
                    "strike_interval": plan.strike_interval,
                    "truncation_notes": scan_notes,
                },
                schema_ref="bd.events.options_chain_scan_started.v1",
                idempotency_key=f"scanner:OptionsChainScanStarted:{scan_run_id}",
                correlation_id=corr,
                causation_id=caus,
            )

            all_rows: list[dict[str, Any]] = []
            batch_errors = 0
            batch_total = len(selected_expiries)
            for idx, expiry in enumerate(selected_expiries):
                try:
                    raw_rows = self._broker.fetch_expiry_quotes(
                        symbol=sym,
                        expiry=expiry,
                        strikes=selected_strikes,
                        exchange=str(meta.get("exchange") or "SMART"),
                        trading_class=str(meta.get("trading_class") or "") or None,
                        multiplier=int(meta.get("multiplier") or 100),
                    )
                    if raw_rows:
                        chain_source = "broker" if settings.broker_backend == "tws" else "mock"
                    for raw in raw_rows:
                        all_rows.append(_classify_row(raw, cfg))
                    log.info(
                        "scan %s batch %s/%s expiry=%s quotes=%s",
                        sym,
                        idx + 1,
                        batch_total,
                        expiry,
                        len(raw_rows),
                    )
                    append_event(
                        engine=self._engine,
                        event_type="OptionsChainExpiryBatchScanned",
                        aggregate_type="options_chain",
                        aggregate_id=f"{sym}:{expiry}",
                        producer="options_chain_scanner",
                        payload={
                            "symbol": sym,
                            "expiry": expiry,
                            "contracts": len(raw_rows),
                            "scan_run_id": scan_run_id,
                        },
                        schema_ref="bd.events.options_chain_expiry_batch_scanned.v1",
                        idempotency_key=f"scanner:OptionsChainExpiryBatchScanned:{scan_run_id}:{expiry}",
                        correlation_id=corr,
                        causation_id=caus,
                    )
                except Exception:
                    batch_errors += 1
                if idx < len(selected_expiries) - 1:
                    delay = max(0, cfg.batch_delay_seconds)
                    if delay > 0:
                        log.info(
                            "scan %s waiting %ss before next expiry batch",
                            sym,
                            delay,
                        )
                    time.sleep(delay)

            scanned = len(all_rows)
            rejected = sum(1 for r in all_rows if r.get("status") == "reject")
            usable = scanned - rejected
            prior_usable = self._prior_usable_count(sym)
            rows_with_quotes = sum(1 for r in all_rows if _row_has_quotes(r))
            if chain_source == "none" and rows_with_quotes > 0 and settings.broker_backend == "tws":
                chain_source = "broker"

            if not all_rows:
                if self._preserve_cached_chain(symbol=sym, reason=empty_quotes_reason(), underlying_price=spot):
                    return True
                update_scan_status(
                    self._engine,
                    sym,
                    scanner_status="partial",
                    last_error=empty_quotes_reason()[:500],
                    underlying_price=spot,
                    contracts_scanned=0,
                    contracts_rejected=0,
                    contracts_usable=0,
                )
                return False

            if rows_with_quotes == 0 and prior_usable > 0:
                self._preserve_cached_chain(
                    symbol=sym,
                    reason=f"{empty_quotes_reason()}; kept last usable snapshot",
                    underlying_price=spot,
                    chain_source=chain_source if chain_source != "none" else None,
                )
                return True

            replace_contracts(self._engine, symbol=sym, scan_run_id=scan_run_id, rows=all_rows)
            completed = datetime.now(UTC)
            final_status = "partial" if batch_errors or usable == 0 else "fresh"

            update_scan_status(
                self._engine,
                sym,
                scanner_status=final_status,
                chain_source=chain_source,
                chain_origin="broker_live",
                last_scan_completed_at=completed,
                expiries_selected=selected_expiries,
                strike_low=strike_low,
                strike_high=strike_high,
                underlying_price=spot,
                contracts_scanned=scanned,
                contracts_rejected=rejected,
                contracts_usable=usable,
                contracts_planned=contracts_planned,
                scan_notes=scan_notes,
                scan_run_id=scan_run_id,
                last_error=None if not batch_errors else f"{batch_errors} expiry batches failed",
            )

            append_event(
                engine=self._engine,
                event_type="OptionsChainSnapshotCaptured",
                aggregate_type="ticker",
                aggregate_id=sym,
                producer="options_chain_scanner",
                payload={
                    "ticker": sym,
                    "captured_at": completed.isoformat(),
                    "rows": all_rows,
                    "data_status": "live" if chain_source == "broker" else "mock",
                    "chain_source": chain_source,
                    "scan_run_id": scan_run_id,
                },
                schema_ref="bd.events.options_chain_snapshot_captured.v1",
                idempotency_key=f"scanner:OptionsChainSnapshotCaptured:{scan_run_id}",
                correlation_id=corr,
                causation_id=caus,
            )
            return True
        except Exception as exc:
            if self._preserve_cached_chain(symbol=sym, reason=f"{exc}; serving last cache"):
                return False
            update_scan_status(
                self._engine,
                sym,
                scanner_status="failed",
                last_error=str(exc)[:500],
            )
            self._emit_failure(sym, "quote_scan", str(exc))
            return False
        finally:
            lock.release()

    def _emit_failure(self, symbol: str, phase: str, error: str) -> None:
        corr, caus = self._trace()
        append_event(
            engine=self._engine,
            event_type="OptionsChainScanFailed",
            aggregate_type="options_chain",
            aggregate_id=symbol,
            producer="options_chain_scanner",
            payload={"symbol": symbol, "phase": phase, "error": error},
            schema_ref="bd.events.options_chain_scan_failed.v1",
            idempotency_key=f"scanner:OptionsChainScanFailed:{symbol}:{uuid4().hex[:8]}",
            correlation_id=corr,
            causation_id=caus,
        )

    def mark_stale_if_needed(self, symbol: str) -> None:
        sym = symbol.strip().upper()
        recover_stuck_scan_if_needed(self._engine, sym)
        status = get_scan_status(self._engine, sym)
        if not status:
            return
        completed = status.get("last_scan_completed_at")
        completed_dt = coerce_utc_datetime(completed)
        if not completed_dt:
            return
        age = (datetime.now(UTC) - completed_dt).total_seconds()
        if age > settings.options_chain.runtime_max_age_seconds:
            if status.get("scanner_status") == "fresh":
                update_scan_status(self._engine, sym, scanner_status="stale")
