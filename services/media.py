import json
from pathlib import Path

DEFAULT_REGISTRY = {
    "gifs": {
        "start": "assets/gifs/start.gif",
        "overtake": "assets/gifs/overtake.gif",
        "damage_minor": "assets/gifs/damage_minor.gif",
        "damage_major": "assets/gifs/damage_major.gif",
        "destroyed": "assets/gifs/destroyed.gif",
        "pit_stop": "assets/gifs/pit_stop.gif",
        "illegal_move": "assets/gifs/illegal_move.gif",
        "disqualified": "assets/gifs/disqualified.gif",
        "lap_leader": "assets/gifs/lap_leader.gif",
        "finish_line": "assets/gifs/finish_line.gif",
        "podium": "assets/gifs/podium.gif"
    },
    "audio": {
        "start": "assets/audio/start.mp3",
        "overtake": "assets/audio/overtake.mp3",
        "damage_minor": "assets/audio/damage_minor.mp3",
        "damage_major": "assets/audio/damage_major.mp3",
        "destroyed": "assets/audio/destroyed.mp3",
        "pit_stop": "assets/audio/pit_stop.mp3",
        "illegal_move": "assets/audio/illegal_move.mp3",
        "disqualified": "assets/audio/disqualified.mp3",
        "lap_leader": "assets/audio/lap_leader.mp3",
        "finish_line": "assets/audio/finish_line.mp3",
        "podium": "assets/audio/podium.mp3"
    }
}

class MediaRegistry:
    """
    Supports both explicit JSON entries and direct files in assets/gifs.

    Example lookup order for overtake_red_blue:
      1) data/media_registry.json entry named overtake_red_blue
      2) assets/gifs/overtake_red_blue.gif
      3) assets/gifs/overtake.gif
      4) no GIF
    """
    def __init__(self, path: str = "data/media_registry.json"):
        self.path = Path(path)
        self.data = DEFAULT_REGISTRY
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(DEFAULT_REGISTRY, indent=2), encoding="utf-8")
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _existing_path(raw: str | None) -> Path | None:
        if not raw:
            return None
        p = Path(raw)
        return p if p.exists() else None

    @staticmethod
    def _fallback_keys(key: str) -> list[str]:
        parts = key.split("_")
        if len(parts) <= 1:
            return []

        # Preserve two-word event bases before dropping colour suffixes.
        two_word_bases = {
            "damage_minor", "damage_major", "pit_stop", "illegal_move",
            "finish_line", "lap_leader"
        }
        first_two = "_".join(parts[:2])
        if first_two in two_word_bases:
            return [first_two]
        return [parts[0]]

    def gif_path(self, key: str | None) -> Path | None:
        if not key:
            return None

        keys_to_try = [key, *self._fallback_keys(key)]
        for lookup_key in keys_to_try:
            registered = self._existing_path(self.data.get("gifs", {}).get(lookup_key))
            if registered:
                return registered

            direct_file = Path("assets/gifs") / f"{lookup_key}.gif"
            if direct_file.exists():
                return direct_file

        return None

    def audio_path(self, key: str | None) -> Path | None:
        if not key:
            return None
        raw = self.data.get("audio", {}).get(key)
        if not raw:
            return None
        p = Path(raw)
        return p if p.exists() else None

    def keys_text(self) -> str:
        gifs = ", ".join(sorted(self.data.get("gifs", {}).keys())) or "none"
        audio = ", ".join(sorted(self.data.get("audio", {}).keys())) or "none"
        return (
            f"GIF keys: {gifs}\n"
            f"Audio keys: {audio}\n\n"
            "Colour GIFs do not need to be listed here if they follow the naming rules in assets/gifs.\n"
            "Examples: overtake_red_blue.gif, pit_stop_green.gif, damage_major_orange.gif, "
            "finish_line_black.gif, podium_red_blue_green.gif"
        )
