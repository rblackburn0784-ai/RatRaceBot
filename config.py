import os
import logging

BOT_VERSION = "0.4.3"
from dataclasses import dataclass

@dataclass(slots=True)
class Settings:
    discord_token: str
    guild_id: int | None
    database_path: str
    race_tick_seconds: float
    admin_role_ids: set[int]
    audit_log_channel_id: int | None

    @classmethod
    def from_env(cls) -> "Settings":
        guild_raw = os.getenv("GUILD_ID", "").strip()
        audit_raw = os.getenv("AUDIT_LOG_CHANNEL_ID", "").strip()
        return cls(
            discord_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            guild_id=int(guild_raw) if guild_raw.isdigit() else None,
            database_path=os.getenv("DATABASE_PATH", "rat_rod_racing.sqlite3"),
            race_tick_seconds=_parse_tick_seconds(os.getenv("RACE_TICK_SECONDS", "5.0")),
            admin_role_ids=_parse_ids(os.getenv("ADMIN_ROLE_IDS", os.getenv("ADMIN_ROLE_ID", ""))),
            audit_log_channel_id=int(audit_raw) if audit_raw.isdigit() else None,
        )


def _parse_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.replace(";", ",").split(","):
        value = part.strip()
        if value.isdigit():
            ids.add(int(value))
    return ids


def _parse_tick_seconds(raw: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.warning("Invalid RACE_TICK_SECONDS=%r; using 5.0", raw)
        return 5.0
    if value < 0 or value > 30:
        logging.warning("RACE_TICK_SECONDS %.2f outside 0..30; clamping", value)
    return max(0.0, min(30.0, value))
