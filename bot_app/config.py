from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


def _parse_admin_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for raw_id in value.split(","):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            ids.add(int(raw_id))
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    database_path: str
    telegram_proxy: str | None = None
    feedback_channel_id: str | None = None


def load_config() -> Config:
    load_dotenv()
    token = getenv("BOT_TOKEN", "").strip()
    if not token:
      raise RuntimeError("BOT_TOKEN .env faylida berilishi kerak.")

    return Config(
        bot_token=token,
        admin_ids=_parse_admin_ids(getenv("ADMIN_IDS", "")),
        database_path=getenv("DATABASE_PATH", "./data/support-manager.sqlite"),
        telegram_proxy=getenv("TELEGRAM_PROXY") or None,
        feedback_channel_id=getenv("FEEDBACK_CHANNEL_ID") or None,
    )
