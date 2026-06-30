from __future__ import annotations

import socket

IBKR_PORTS: dict[int, str] = {
    7497: "TWS paper",
    7496: "TWS live",
    4002: "IB Gateway paper",
    4001: "IB Gateway live",
}


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_open_ibkr_ports(host: str) -> list[tuple[int, str]]:
    open_ports: list[tuple[int, str]] = []
    for port, label in IBKR_PORTS.items():
        if port_open(host, port):
            open_ports.append((port, label))
    return open_ports


def endpoint_label(port: int) -> str:
    return IBKR_PORTS.get(port, f"IBKR API port {port}")


def format_broker_endpoint(host: str, port: int) -> str:
    return f"{endpoint_label(port)} at {host}:{port}"


def connect_setup_hint(host: str, port: int) -> str:
    label = endpoint_label(port)
    return (
        f"Start {label}, enable ActiveX/Socket clients and Read-Only API on port {port}, "
        f"trusted IP 127.0.0.1, then Connect Broker."
    )


def format_connect_exception(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc).strip()
    if msg:
        return f"{name}: {msg}"
    return name
