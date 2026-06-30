#!/usr/bin/env python3
"""Connect to TWS/IB Gateway and fetch QQQ snapshot, option chain, and scanner cache."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
from pathlib import Path
from uuid import uuid4

_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.config import settings
from app.db import get_engine
from app.services.broker.factory import get_broker_client
from app.services.market_hours import is_us_equity_regular_session
from app.services.options_chain_scanner import OptionsChainScanner, _classify_row
from app.services.options_chain_store import get_contracts, get_scan_status


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


IBKR_PORTS = {
    7497: "TWS paper",
    7496: "TWS live",
    4002: "IB Gateway paper",
    4001: "IB Gateway live",
}


def _find_open_ports(host: str) -> list[tuple[int, str]]:
    open_ports: list[tuple[int, str]] = []
    for port, label in IBKR_PORTS.items():
        if _port_open(host, port):
            open_ports.append((port, label))
    return open_ports


def _quote_summary(contracts: list[dict]) -> None:
    priced = mid_only = no_quote = 0
    reasons: dict[str, int] = {}
    for c in contracts:
        bid = float(c.get("bid") or 0)
        ask = float(c.get("ask") or 0)
        mid = float(c.get("mid") or 0)
        if bid > 0 and ask > 0:
            priced += 1
        elif mid > 0:
            mid_only += 1
        else:
            no_quote += 1
        reason = str(c.get("rejection_reason") or "")
        if reason:
            key = reason.split(";")[0][:60]
            reasons[key] = reasons.get(key, 0) + 1
    print(f"  quote_summary: priced={priced} mid_only={mid_only} no_quote={no_quote}")
    if reasons:
        top = sorted(reasons.items(), key=lambda x: -x[1])[:3]
        print(f"  rejection_top: {dict(top)}")


def _run_strategy_builder_smoke(client: object, symbol: str) -> int:
    print(f"\n--- Strategy builder runtime ({symbol}) ---")
    import app.main as main_app

    main_app.broker_client = client  # type: ignore[assignment]
    runtime = main_app._run_strategy_runtime_once(
        ticker=symbol,
        direction="bullish",
        reconciliation_mismatch_active=False,
        thresholds={"max_loss_per_trade_usd": 750},
    )
    print(f"  data_status={runtime.data_status} runtime_allowed={runtime.runtime_allowed}")
    if runtime.runtime_warning:
        print(f"  runtime_warning={runtime.runtime_warning}")
    if runtime.runtime_block_reason:
        print(f"  runtime_block_reason={runtime.runtime_block_reason}")
    print(f"  candidates={len(runtime.candidates)}")
    if runtime.candidates:
        types = [c.strategy_type for c in runtime.candidates[:5]]
        print(f"  top_strategies={types}")
    if not runtime.runtime_allowed:
        return 5
    if not runtime.candidates:
        print("  WARNING: runtime allowed but no candidates generated")
        return 5
    return 0


def _run_known_positions_smoke(client: object, symbol: str) -> int:
    print(f"\n--- Known QQQ positions smoke ({symbol}) ---")
    fetch = getattr(client, "fetch_exact_option_quotes", None)
    if fetch is None:
        print("  SKIP: client has no fetch_exact_option_quotes")
        return 0
    contracts = [
        {"expiry": "20260717", "strike": 710.0, "right": "C"},
        {"expiry": "20260717", "strike": 740.0, "right": "C"},
    ]
    results = fetch(symbol=symbol, contracts=contracts, trading_class=symbol)
    failures = 0
    for row in results:
        label = f"{row.get('expiry')} {row.get('strike')} {row.get('right')}"
        qualified = bool(row.get("qualified"))
        has_quote = bool(row.get("has_quote")) or (
            float(row.get("bid") or 0) > 0 or float(row.get("ask") or 0) > 0
        )
        data_type = row.get("data_type") or "-"
        print(
            f"  {label}: qualified={qualified} bid={row.get('bid')} ask={row.get('ask')} "
            f"data_type={data_type} error={row.get('error')}"
        )
        if not qualified:
            failures += 1
        elif not has_quote:
            print(f"    WARNING: qualified but no bid/ask (permissions or off-hours)")
    return failures


def _run_scanner_smoke(client: object, symbol: str) -> int:
    print(f"\n--- Options chain scanner ({symbol}) ---")
    engine = get_engine()

    def _trace() -> tuple[str, str]:
        cid = f"smoke_{uuid4().hex[:8]}"
        return cid, cid

    scanner = OptionsChainScanner(
        engine=engine,
        broker=client,
        trace_fn=_trace,
        broker_connected_fn=lambda: bool(getattr(client, "connection_state")().broker_connected),
    )

    print("Refreshing secdef metadata...")
    meta_ok = scanner.refresh_metadata(symbol)
    meta = client.fetch_secdef_metadata(symbol)  # type: ignore[attr-defined]
    if meta:
        expiries = meta.get("expiries") or []
        strikes = meta.get("strikes") or []
        print(
            f"  metadata ok={meta_ok} conid={meta.get('conid')} chains={meta.get('chains_returned')} "
            f"exchange={meta.get('exchange')} tradingClass={meta.get('trading_class')} "
            f"multiplier={meta.get('multiplier')} expiries={len(expiries)} strikes={len(strikes)}"
        )
    else:
        print(f"  metadata ok={meta_ok} (no live secdef payload)")

    prior_count = len(get_contracts(engine, symbol))
    cfg = settings.options_chain
    batch_total = cfg.max_expiries
    delay = cfg.batch_delay_seconds
    est_wait = max(0, batch_total - 1) * delay
    print(
        f"Running quote scan (prior cached contracts={prior_count}, "
        f"~{batch_total} expiry batches, {delay}s inter-batch delay, ~{est_wait}s wait)..."
    )
    if delay > 0:
        print("  (inter-batch sleep is normal — do not interrupt unless using --quick)")
    scan_ok = scanner.run_quote_scan(symbol)
    status = get_scan_status(engine, symbol) or {}
    contracts = get_contracts(engine, symbol)
    scanner_status = str(status.get("scanner_status", "idle"))
    print(f"  scan_ok={scan_ok} scanner_status={scanner_status}")
    print(f"  contracts_planned={status.get('contracts_planned')} chain_source={status.get('chain_source')}")
    print(f"  contracts_scanned={status.get('contracts_scanned')} contracts_usable={status.get('contracts_usable')} contracts_rejected={status.get('contracts_rejected')}")
    notes = status.get("scan_notes") or []
    if notes:
        print(f"  scan_notes={notes}")
    if status.get("last_error"):
        print(f"  last_error={status.get('last_error')}")
    print(f"  cached_contracts={len(contracts)}")
    _quote_summary(contracts)

    if not is_us_equity_regular_session() and prior_count > 0 and scanner_status == "stale":
        print("  NOTE: off-hours — serving last cache (stale); this is expected.")

    if scanner_status == "failed":
        return 4
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TWS/IB Gateway smoke test")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Set batch_delay_seconds=0 for faster scanner runs",
    )
    parser.add_argument(
        "--skip-strategy",
        action="store_true",
        help="Skip strategy builder runtime step after scanner",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="  %(message)s")

    if args.quick:
        settings.options_chain.batch_delay_seconds = 0
        print("Quick mode: batch_delay_seconds=0")

    host = settings.tws_host
    port = settings.tws_port
    print(f"IBKR target: {host}:{port} (client_id={settings.tws_client_id}, read_only={settings.tws_read_only})")
    print(f"Session: {'regular RTH' if is_us_equity_regular_session() else 'off-hours / extended'}")

    open_ports = _find_open_ports(host)
    if open_ports:
        print("Open IBKR API ports:")
        for p, label in open_ports:
            marker = " <-- configured" if p == port else ""
            print(f"  {host}:{p} ({label}){marker}")
    else:
        print(f"\nNo IBKR API ports open on {host} (checked 7497 paper, 7496 live, 4002/4001 gateway).")

    if not _port_open(host, port):
        if open_ports:
            suggested = open_ports[0][0]
            print(
                f"\nERROR: Configured port {port} is closed, but {suggested} is open.\n"
                f"Set tws_port={suggested} in backend/config.yaml and retry."
            )
        else:
            print(
                f"\nERROR: Nothing is listening on {host}:{port}.\n"
                "IB Gateway / TWS API socket is OFF. Fix:\n"
                "  1. Configure → Settings → API\n"
                "     - Enable ActiveX and Socket Clients: ON\n"
                "     - Read-Only API: ON\n"
                "     - Socket port: 4001 (Gateway live) or 4002 (Gateway paper)\n"
                "     - Trusted IP: 127.0.0.1\n"
                "  2. Restart Gateway/TWS after changing API settings\n"
                "  3. Approve the 'Incoming API connection' popup when the app connects\n"
            )
        return 1

    get_broker_client.cache_clear()
    settings.broker_backend = "tws"
    client = get_broker_client()

    print("\nConnecting...")
    try:
        state = client.connect()
    except Exception as exc:
        print(f"CONNECT FAILED: {exc}")
        return 2

    print(f"Connected: {state.broker_connected} — {state.message}")

    symbol = settings.options_chain.default_symbol or "QQQ"
    print(f"\nQualifying {symbol}...")
    info = client.qualify_stock(symbol)
    if not info:
        print(f"Could not qualify {symbol}")
        client.disconnect()
        return 3
    print(f"  conid={info.conid} exchange={info.exchange}")

    print(f"\nMarket snapshot for {symbol}...")
    snap = client.market_snapshot(symbol)
    if not snap:
        print("  No snapshot (market data subscription may be missing; try tws_market_data_type=3 for delayed)")
    else:
        print(json.dumps(snap, indent=2))

    last = float(snap["last"]) if snap else 480.0
    print(f"\nSkipping legacy option_chain sample (use bounded scanner below; avoids unlisted strike/expiry pairs).")

    print("\nAccounts:", client.list_accounts())
    print("Positions:", len(client.list_positions()))
    print("Open orders:", len(client.list_open_orders()))

    known_rc = _run_known_positions_smoke(client, symbol)
    scanner_rc = _run_scanner_smoke(client, symbol)
    strategy_rc = 0 if args.skip_strategy else _run_strategy_builder_smoke(client, symbol)

    client.disconnect()
    print("\nDone.")
    return known_rc or scanner_rc or strategy_rc


if __name__ == "__main__":
    sys.exit(main())
