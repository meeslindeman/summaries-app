from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    request_timeout_s: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
    input_char_cap: int = int(os.getenv("INPUT_CHAR_CAP", "12000"))
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "220"))
    db_path: Path = DATA_DIR / "cache.sqlite"
    user_agent: str = os.getenv("USER_AGENT", "news-summarizer/0.1 (+https://example.local)")
    refresh_token: str = os.getenv("REFRESH_TOKEN", "")

settings = Settings()
