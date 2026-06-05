from pydantic import BaseModel


class AppConfig(BaseModel):
    app_name: str = "Billion Dollar API"
    app_version: str = "0.3.0"
    default_trading_mode: str = "paper"
    database_url: str = "sqlite:///./billion_dollar.db"
    broker_backend: str = "tws"
    tws_host: str = "127.0.0.1"
    tws_port: int = 7496
    tws_client_id: int = 1
    tws_read_only: bool = True
    tws_connect_timeout_seconds: float = 10.0
    tws_market_data_type: int = 1
    tws_connection_interval_seconds: int = 60
    auto_ingestion_on_startup: bool = True
    default_runtime_tickers: list[str] = ["QQQ", "SPY", "IWM", "DIA", "XLK", "SMH"]
    reconcile_worker_interval_seconds: int = 60
    reconcile_mismatch_halt_seconds: int = 600
    allow_mock_option_chain: bool = True
    execution_mode: str = "paper_only"


settings = AppConfig()


