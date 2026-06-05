from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.broker.factory import get_broker_client


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


def connect_broker_session() -> dict[str, Any]:
    client = get_broker_client()
    steps: list[str] = []
    try:
        state = client.connect()
        steps.append("tws_connect")
    except Exception as exc:
        return {
            "status": "tws_unreachable",
            "message": f"Unable to connect to TWS at {settings.tws_host}:{settings.tws_port} — {exc}",
            "next_action": "start_tws_paper",
            "gateway_login_url": "",
            "steps": steps,
        }

    if not state.broker_connected:
        return {
            "status": "tws_unreachable",
            "message": (
                f"TWS is not connected on {settings.tws_host}:{settings.tws_port}. "
                "Open TWS paper, enable API (read-only), then retry."
            ),
            "next_action": "start_tws_paper",
            "gateway_login_url": "",
            "steps": steps,
        }

    steps.append("tws_authenticated")
    return {
        "status": "connected",
        "message": "TWS read-only session is connected. Realtime ingestion can proceed.",
        "next_action": "run_ingestion",
        "gateway_login_url": "",
        "auth_status": {"read_only": settings.tws_read_only},
        "steps": steps,
    }
