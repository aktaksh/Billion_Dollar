import unittest
from unittest.mock import MagicMock, patch

from app.workers.options_chain_scheduler import OptionsChainScheduler


class OptionsChainSchedulerStartupTests(unittest.TestCase):
    def test_skips_immediate_jobs_when_broker_disconnected(self):
        metadata = MagicMock()
        quote = MagicMock()
        scheduler = OptionsChainScheduler(
            metadata_fn=metadata,
            quote_fn=quote,
            broker_connected_fn=lambda: False,
        )
        with patch("app.workers.options_chain_scheduler.settings") as mock_settings:
            mock_settings.options_chain.enabled = True
            mock_settings.options_chain.symbols = ["QQQ"]
            mock_settings.options_chain.metadata_refresh_minutes = 20
            mock_settings.options_chain.refresh_seconds = 120
            scheduler.start()
        try:
            metadata.assert_not_called()
            quote.assert_not_called()
            self.assertEqual(scheduler.last_status, "running")
        finally:
            scheduler.stop()

    def test_runs_immediate_jobs_when_broker_connected(self):
        metadata = MagicMock()
        quote = MagicMock()
        scheduler = OptionsChainScheduler(
            metadata_fn=metadata,
            quote_fn=quote,
            broker_connected_fn=lambda: True,
        )
        with patch("app.workers.options_chain_scheduler.settings") as mock_settings:
            mock_settings.options_chain.enabled = True
            mock_settings.options_chain.symbols = ["QQQ"]
            mock_settings.options_chain.metadata_refresh_minutes = 20
            mock_settings.options_chain.refresh_seconds = 120
            scheduler.start()
        try:
            metadata.assert_called_once_with("QQQ")
            quote.assert_called_once_with("QQQ")
        finally:
            scheduler.stop()


if __name__ == "__main__":
    unittest.main()
