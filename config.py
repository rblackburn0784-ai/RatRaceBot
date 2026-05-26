import os
from dataclasses import dataclass

@dataclass(slots=True)
class Settings:
    discord_token: str
    guild_id: int | None
    database_path: str
    race_tick_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        guild_raw = os.getenv("GUILD_ID", "").strip()
        return cls(
            discord_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            guild_id=int(guild_raw) if guild_raw.isdigit() else None,
            database_path=os.getenv("DATABASE_PATH", "rat_rod_racing.sqlite3"),
            race_tick_seconds=float(os.getenv("RACE_TICK_SECONDS", "5.0")),
        )
