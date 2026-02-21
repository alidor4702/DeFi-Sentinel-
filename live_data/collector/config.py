from pathlib import Path

from pydantic_settings import BaseSettings

# Look for .env in live_data/ directory (parent of collector/)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class CollectorSettings(BaseSettings):
    HELIUS_API_KEY: str
    JUPITER_API_KEY: str = ""
    HELIUS_RPC_URL: str = "https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    RUGCHECK_BASE_URL: str = "https://api.rugcheck.xyz"
    GECKOTERMINAL_BASE_URL: str = "https://api.geckoterminal.com"
    JUPITER_BASE_URL: str = "https://api.jup.ag"
    REQUEST_TIMEOUT: float = 10.0
    MAX_RETRIES: int = 3

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}

    @property
    def helius_rpc_url(self) -> str:
        return self.HELIUS_RPC_URL.format(HELIUS_API_KEY=self.HELIUS_API_KEY)
