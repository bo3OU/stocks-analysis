import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from a local .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    sec_user_agent: str
    tiingo_api_key: str | None
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        data_dir = Path(os.environ.get("DATA_DIR", "./data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            sec_user_agent=os.environ.get("SEC_USER_AGENT", "stocks-analysis (set SEC_USER_AGENT)"),
            tiingo_api_key=os.environ.get("TIINGO_API_KEY") or None,
            data_dir=data_dir,
        )
