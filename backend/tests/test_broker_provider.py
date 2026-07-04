import unittest
from unittest.mock import MagicMock, patch

from app.services.broker.broker_provider import AutoBrokerProvider, CpGatewayProvider, TwsBrokerProvider


class BrokerProviderTests(unittest.TestCase):
    @patch("app.services.broker.broker_provider.TwsBrokerProvider.is_available", return_value=(True, "TWS ok"))
    @patch("app.services.broker.broker_provider.CpGatewayProvider.is_available", return_value=(False, "CP down"))
    @patch("app.services.broker.broker_provider.settings")
    def test_auto_prefers_tws(self, mock_settings, _cp, _tws):
        mock_settings.ibkr_broker_backend = "auto"
        provider = AutoBrokerProvider()
        ok, msg = provider.is_available()
        self.assertTrue(ok)
        self.assertEqual(provider.active_name, "tws")
        self.assertIn("TWS", msg)

    @patch("app.services.broker.broker_provider.TwsBrokerProvider.is_available", return_value=(False, "TWS down"))
    @patch("app.services.broker.broker_provider.CpGatewayProvider.is_available", return_value=(True, "CP ok"))
    @patch("app.services.broker.broker_provider.settings")
    def test_auto_falls_back_to_cp(self, mock_settings, _cp, _tws):
        mock_settings.ibkr_broker_backend = "auto"
        mock_settings.tws_host = "127.0.0.1"
        mock_settings.tws_port = 4001
        provider = AutoBrokerProvider()
        ok, _msg = provider.is_available()
        self.assertTrue(ok)
        self.assertEqual(provider.active_name, "cp_gateway")

    @patch("app.services.broker.broker_provider.TwsBrokerProvider.is_available", return_value=(False, "TWS down"))
    @patch("app.services.broker.broker_provider.CpGatewayProvider.is_available", return_value=(False, "CP down"))
    @patch("app.services.broker.broker_provider.settings")
    def test_auto_none_available(self, mock_settings, _cp, _tws):
        mock_settings.ibkr_broker_backend = "auto"
        mock_settings.tws_host = "127.0.0.1"
        mock_settings.tws_port = 4001
        provider = AutoBrokerProvider()
        ok, msg = provider.is_available()
        self.assertFalse(ok)
        self.assertIn("4001", msg)

    @patch("app.services.broker.broker_provider.settings")
    def test_get_broker_provider_tws_mode(self, mock_settings):
        mock_settings.ibkr_broker_backend = "tws"
        from app.services.broker.broker_provider import get_broker_provider

        self.assertIsInstance(get_broker_provider(), TwsBrokerProvider)

    @patch("app.services.broker.broker_provider.settings")
    def test_get_broker_provider_cp_mode(self, mock_settings):
        mock_settings.ibkr_broker_backend = "cp_gateway"
        from app.services.broker.broker_provider import get_broker_provider

        self.assertIsInstance(get_broker_provider(), CpGatewayProvider)


if __name__ == "__main__":
    unittest.main()
