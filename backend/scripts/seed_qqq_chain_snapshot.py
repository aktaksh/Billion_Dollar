#!/usr/bin/env python3
"""Seed a broker-backed QQQ options chain snapshot for off-hours UI testing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.services.chain_fixture_seed import seed_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed broker QQQ chain snapshot into SQLite")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="JSON fixture (e.g. fixtures/qqq_broker_snapshot.json); omit to use built-in sample",
    )
    parser.add_argument("--symbol", default=None, help="Override symbol (default: fixture symbol or QQQ)")
    args = parser.parse_args()
    result = seed_snapshot(fixture_path=args.fixture, symbol=args.symbol)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
