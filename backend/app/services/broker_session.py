from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.broker.factory import get_broker_client
from app.services.broker_endpoint import (
    connect_setup_hint,
    find_open_ibkr_ports,
    format_broker_endpoint,
    format_connect_exception,
    port_open,
)


def _is_client_id_in_use_error(err: str) -> bool:
    lowered = err.lower()
    return "client id" in lowered or "clientid" in lowered or "326" in lowered


def evaluate_broker_connection() -> dict[str, Any]:
    client = get_broker_client()
    state = client.connection_state()
    return {
        "tws_reachable": state.tws_reachable,
        "gateway_reachable": state.tws_reachable,
        "connected": state.broker_connected,
        "authenticated": state.broker_authenticated,
        "read_only": state.read_only,
        "tws_host": state.tws_host,
        "tws_port": state.tws_port,
        "tws_client_id": state.tws_client_id,
        "checked_at": state.checked_at or datetime.now(UTC).isoformat(),
    }


def _port_closed_message() -> tuple[str, str]:
    host = settings.tws_host
    port = settings.tws_port
    endpoint = format_broker_endpoint(host, port)
    open_ports = find_open_ibkr_ports(host)
    if open_ports:
        suggested_port, suggested_label = open_ports[0]
        message = (
            f"Configured {endpoint} is not accepting connections. "
            f"{suggested_label} is listening on port {suggested_port} — "
            f"set tws_port={suggested_port} in config.yaml and restart the backend."
        )
        return message, "fix_tws_port_config"
    message = f"No IBKR API port is open on {host}. {connect_setup_hint(host, port)}"
    return message, "start_ibkr_api"


def connect_broker_session() -> dict[str, Any]:
    client = get_broker_client()
    steps: list[str] = []
    host = settings.tws_host
    port = settings.tws_port
    endpoint = format_broker_endpoint(host, port)

    existing = client.connection_state()
    if existing.broker_connected:
        steps.extend(["tws_connect", "tws_authenticated"])
        return {
            "status": "connected",
            "message": f"Read-only session already active on {endpoint}.",
            "next_action": "run_ingestion",
            "gateway_login_url": "",
            "auth_status": {"read_only": settings.tws_read_only},
            "steps": steps,
        }

    try:
        state = client.connect()
        steps.append("tws_connect")
    except Exception as exc:
        err = format_connect_exception(exc)
        if settings.broker_backend == "tws" and not port_open(host, port):
            message, next_action = _port_closed_message()
            return {
                "status": "tws_unreachable",
                "message": message,
                "next_action": next_action,
                "gateway_login_url": "",
                "steps": steps,
            }
        if _is_client_id_in_use_error(err):
            hint = (
                f"Client ID {settings.tws_client_id} is already in use on IB Gateway. "
                "Disconnect the stale session in Gateway API settings, or set tws_client_id to a "
                "different value (e.g. 2) in config.yaml and restart the backend."
            )
            return {
                "status": "tws_unreachable",
                "message": f"Unable to connect to {endpoint} — {err}. {hint}",
                "next_action": "client_id_in_use",
                "gateway_login_url": "",
                "steps": steps,
            }
        hint = (
            f"Check client ID {settings.tws_client_id}, approve the incoming API connection prompt "
            f"in IB Gateway/TWS, and verify API settings match read_only={settings.tws_read_only}."
        )
        return {
            "status": "tws_unreachable",
            "message": f"Unable to connect to {endpoint} — {err}. {hint}",
            "next_action": "check_tws_api_settings",
            "gateway_login_url": "",
            "steps": steps,
        }

    if not state.broker_connected:
        if settings.broker_backend == "tws" and not port_open(host, port):
            message, next_action = _port_closed_message()
            return {
                "status": "tws_unreachable",
                "message": message,
                "next_action": next_action,
                "gateway_login_url": "",
                "steps": steps,
            }
        return {
            "status": "tws_unreachable",
            "message": (
                f"IBKR API handshake did not complete on {endpoint}. "
                f"{connect_setup_hint(host, port)}"
            ),
            "next_action": "check_tws_api_settings",
            "gateway_login_url": "",
            "steps": steps,
        }

    steps.append("tws_authenticated")
    return {
        "status": "connected",
        "message": f"Read-only session connected to {endpoint}. Realtime ingestion can proceed.",
        "next_action": "run_ingestion",
        "gateway_login_url": "",
        "auth_status": {"read_only": settings.tws_read_only},
        "steps": steps,
    }
