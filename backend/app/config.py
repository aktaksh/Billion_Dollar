from pydantic import BaseModel


class AppConfig(BaseModel):
    app_name: str = "Stock Tiger API"
    app_version: str = "0.1.0"
    default_trading_mode: str = "paper"
    database_url: str = "sqlite:///./stock_tiger.db"
    ibkr_gateway_base_url: str = "https://localhost:5000/v1/api"
    ibkr_timeout_seconds: float = 10.0
    ibkr_verify_tls: bool = False


settings = AppConfig()


