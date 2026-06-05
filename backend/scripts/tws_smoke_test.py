#!/usr/bin/env python3
"""Connect to TWS paper and fetch a QQQ market snapshot + option chain sample."""

from __future__ import annotations

import json
import socket
import sys

from app.config import settings
from app.services.broker.factory import get_broker_client


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


def main() -> int:
    host = settings.tws_host
    port = settings.tws_port
    print(f"TWS target: {host}:{port} (client_id={settings.tws_client_id}, read_only={settings.tws_read_only})")

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
                f"Set tws_port={suggested} in backend/app/config.py (or env) and retry."
            )
        else:
            print(
                f"\nERROR: Nothing is listening on {host}:{port}.\n"
                "TWS is running but the API socket is OFF. Fix:\n"
                "  1. In TWS: Edit → Global Configuration → API → Settings\n"
                "     - Enable ActiveX and Socket Clients: ON\n"
                "     - Read-Only API: ON\n"
                "     - Socket port: 7497 (paper) or 7496 (live)\n"
                "     - Trusted IP: 127.0.0.1\n"
                "  2. Click Apply, then OK\n"
                "  3. Fully quit TWS (Cmd+Q) and reopen — API settings only bind after restart\n"
                "  4. On the login dialog, enable socket clients if that checkbox appears\n"
                "  5. Approve the 'Incoming API connection' popup when the app connects\n"
                "\nNote: Your Jts config shows tradingMode=l (live). Paper uses port 7497; live uses 7496.\n"
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

    symbol = "QQQ"
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
    print(f"\nOption chain sample (last={last})...")
    chain, source, reason = client.option_chain(symbol=symbol, last_price=last)
    print(f"  source={source} reason={reason} legs={len(chain)}")
    if chain:
        print(json.dumps(chain[:4], indent=2))
        if len(chain) > 4:
            print(f"  ... and {len(chain) - 4} more legs")

    print("\nAccounts:", client.list_accounts())
    print("Positions:", len(client.list_positions()))
    print("Open orders:", len(client.list_open_orders()))

    client.disconnect()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
