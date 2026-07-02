from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.config import Settings, get_settings


class Storage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = Path(self.settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bars (
                symbol VARCHAR,
                timeframe VARCHAR,
                ts TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                fetched_at TIMESTAMP,
                PRIMARY KEY (symbol, timeframe, ts)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS option_snapshots (
                snapshot_date DATE,
                symbol VARCHAR,
                expiry VARCHAR,
                strike DOUBLE,
                option_right VARCHAR,
                bid DOUBLE,
                ask DOUBLE,
                last DOUBLE,
                delta DOUBLE,
                gamma DOUBLE,
                theta DOUBLE,
                vega DOUBLE,
                iv DOUBLE,
                volume BIGINT,
                open_interest BIGINT,
                dte INTEGER,
                fetched_at TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id VARCHAR PRIMARY KEY,
                symbol VARCHAR,
                run_at TIMESTAMP,
                bias VARCHAR,
                confidence VARCHAR,
                bullish_score INTEGER,
                bearish_score INTEGER,
                action VARCHAR,
                underlying_price DOUBLE,
                payload JSON
            )
            """
        )

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        rows = self._conn.execute(
            """
            SELECT ts, open, high, low, close, volume
            FROM bars WHERE symbol = ? AND timeframe = ?
            ORDER BY ts
            """,
            [symbol.upper(), timeframe],
        ).df()
        if rows.empty:
            return None
        rows["ts"] = pd.to_datetime(rows["ts"], utc=True)
        return rows.set_index("ts")

    def save_bars(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        out = df.reset_index().rename(columns={"index": "ts"})
        if "date" in out.columns and "ts" not in out.columns:
            out = out.rename(columns={"date": "ts"})
        out["symbol"] = symbol.upper()
        out["timeframe"] = timeframe
        out["fetched_at"] = datetime.now(timezone.utc)
        cols = ["symbol", "timeframe", "ts", "open", "high", "low", "close", "volume", "fetched_at"]
        self._conn.register("_bars_tmp", out[cols])
        self._conn.execute(
            """
            INSERT OR REPLACE INTO bars
            SELECT symbol, timeframe, ts, open, high, low, close, volume, fetched_at
            FROM _bars_tmp
            """
        )
        self._conn.unregister("_bars_tmp")

    def save_option_snapshot(self, symbol: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        today = datetime.now(timezone.utc).date()
        fetched = datetime.now(timezone.utc)
        for row in rows:
            row["snapshot_date"] = today
            row["symbol"] = symbol.upper()
            row["fetched_at"] = fetched
        df = pd.DataFrame(rows)
        self._conn.register("_opt_tmp", df)
        self._conn.execute("INSERT INTO option_snapshots SELECT * FROM _opt_tmp")
        self._conn.unregister("_opt_tmp")
        return len(rows)

    def close(self) -> None:
        self._conn.close()
