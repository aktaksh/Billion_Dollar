import os
import unittest
from unittest.mock import MagicMock, patch

from app.config import settings
from app.services.broker.base import BrokerConnectionState
from app.services.broker.factory import get_broker_client
from app.services.broker.mock_client import MockBrokerClient
from app.services.broker_session import connect_broker_session


class TwsClientConnectTests(unittest.TestCase):
    def test_connect_keeps_session_when_market_data_type_fails(self) -> None:
        mock_ib = MagicMock()
        mock_ib.isConnected.side_effect = [False, True, True]
        mock_ib.reqMarketDataType.side_effect = RuntimeError("market data type rejected")

        with patch("app.services.broker.tws_client._ensure_event_loop"):
            with patch("ib_insync.IB", return_value=mock_ib):
                from app.services.broker.tws_client import TwsBrokerClient

                client = TwsBrokerClient()
                state = client.connect()
                self.assertTrue(state.broker_connected)
                mock_ib.connect.assert_called_once()
                mock_ib.reqMarketDataType.assert_called_once()

    def test_connect_disconnects_on_handshake_failure(self) -> None:
        mock_ib = MagicMock()
        mock_ib.isConnected.side_effect = [False, True]
        mock_ib.connect.side_effect = RuntimeError("handshake failed")

        with patch("app.services.broker.tws_client._ensure_event_loop"):
            with patch("ib_insync.IB", return_value=mock_ib):
                from app.services.broker.tws_client import TwsBrokerClient

                client = TwsBrokerClient()
                with self.assertRaises(RuntimeError):
                    client.connect()
                mock_ib.disconnect.assert_called_once()


class BrokerConnectErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        get_broker_client.cache_clear()

    def tearDown(self) -> None:
        get_broker_client.cache_clear()
        os.environ["BROKER_BACKEND"] = "mock"
        settings.broker_backend = "mock"

    @patch("app.services.broker_session.port_open", return_value=False)
    @patch("app.services.broker_session.find_open_ibkr_ports", return_value=[(4001, "IB Gateway live")])
    def test_port_closed_after_connect_failure(self, _find: MagicMock, _port_open: MagicMock) -> None:
        settings.broker_backend = "tws"
        settings.tws_port = 7497
        get_broker_client.cache_clear()

        class FailingClient:
            def connection_state(self) -> BrokerConnectionState:
                return BrokerConnectionState(broker_connected=False)

            def connect(self) -> BrokerConnectionState:
                raise ConnectionError("connection refused")

        with patch("app.services.broker_session.get_broker_client", return_value=FailingClient()):
            result = connect_broker_session()
        self.assertEqual(result["status"], "tws_unreachable")
        self.assertIn("4001", result["message"])

    @patch("app.services.broker_session.port_open", return_value=True)
    def test_client_id_in_use_error(self, _port_open: MagicMock) -> None:
        settings.broker_backend = "tws"

        class ClientIdConflictClient:
            def connection_state(self) -> BrokerConnectionState:
                return BrokerConnectionState(broker_connected=False)

            def connect(self) -> BrokerConnectionState:
                raise RuntimeError("Unable to connect as the client id is already in use")

        with patch("app.services.broker_session.get_broker_client", return_value=ClientIdConflictClient()):
            result = connect_broker_session()
        self.assertEqual(result["status"], "tws_unreachable")
        self.assertEqual(result["next_action"], "client_id_in_use")
        self.assertIn("already in use", result["message"].lower())

    def test_short_circuit_when_already_connected(self) -> None:
        os.environ["BROKER_BACKEND"] = "mock"
        settings.broker_backend = "mock"
        get_broker_client.cache_clear()
        client = get_broker_client()
        assert isinstance(client, MockBrokerClient)
        client.connect()

        with patch.object(client, "connect") as mock_connect:
            result = connect_broker_session()
            mock_connect.assert_not_called()
        self.assertEqual(result["status"], "connected")
        self.assertIn("already active", result["message"].lower())

    def test_connect_broker_session_mock(self) -> None:
        os.environ["BROKER_BACKEND"] = "mock"
        settings.broker_backend = "mock"
        get_broker_client.cache_clear()
        client = get_broker_client()
        assert isinstance(client, MockBrokerClient)
        result = connect_broker_session()
        self.assertEqual(result["status"], "connected")
        self.assertIn(str(settings.tws_port), result["message"])


class ShellStatusBrokerBlockTests(unittest.TestCase):
    def test_shell_status_clears_broker_disconnected_when_connected(self) -> None:
        from app.main import _shell_status

        with patch("app.main._broker_state", return_value={"connected": True, "authenticated": True, "tws_reachable": True}):
            with patch("app.main._broker_data_status", return_value="live"):
                shell = _shell_status()
        self.assertTrue(shell.broker_connected)
        self.assertIsNone(shell.runtime_block_reason)


class BrokerConnectClearsScannerErrorsTests(unittest.TestCase):
    def test_clear_stale_scanner_disconnect_errors(self) -> None:
        from app.db import get_engine, init_db
        from app.main import _clear_stale_scanner_disconnect_errors
        from app.services.options_chain_store import get_scan_status, update_scan_status

        engine = get_engine()
        init_db(engine)
        update_scan_status(
            engine,
            "QQQ",
            scanner_status="failed",
            last_error="scan timed out; refresh to retry",
        )
        _clear_stale_scanner_disconnect_errors()
        row = get_scan_status(engine, "QQQ") or {}
        self.assertIsNone(row.get("last_error"))
        self.assertEqual(row.get("scanner_status"), "idle")


class ChainOriginResolutionTests(unittest.TestCase):
    def test_stale_broker_live_cleared_when_no_cache(self) -> None:
        from app.db import get_engine, init_db
        from app.main import _chain_origin_for_symbol
        from app.services.options_chain_store import update_scan_status

        engine = get_engine()
        init_db(engine)
        update_scan_status(
            engine,
            "QQQ",
            chain_origin="broker_live",
            chain_source="none",
            contracts_usable=0,
        )
        self.assertEqual(_chain_origin_for_symbol("QQQ"), "none")


if __name__ == "__main__":
    unittest.main()
