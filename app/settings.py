from dataclasses import dataclass, asdict
from pathlib import Path
import json
from app.config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"

@dataclass
class ServerSettings:
    home_count: int = 5
    per_feed_cap: int = 3
    per_domain_quota: int = 2
    recency_half_life_hours: int = 24

def load_settings() -> ServerSettings:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text("utf-8"))
            home_count = int(data.get("home_count", 5))
            return ServerSettings(home_count=home_count)
        except Exception:
            pass
    s = ServerSettings()
    SETTINGS_PATH.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), "utf-8")
    return s

def save_settings(new_data: dict) -> ServerSettings:
    home_count = int(new_data.get("home_count", 5))
    home_count = max(1, min(home_count, 20))
    s = ServerSettings(home_count=home_count)
    SETTINGS_PATH.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), "utf-8")
    return s
