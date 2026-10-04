from __future__ import annotations

from pathlib import Path
import hashlib
import re
import tempfile
import time

from models.domain import RaceEvent
from models.enums import EventType

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_DIR = PROJECT_ROOT / "assets" / "track"
CAR_DIR = PROJECT_ROOT / "assets" / "cars"
OUTPUT_DIR = Path(tempfile.gettempdir()) / "rat_race_event_gifs"
FRAME_COUNT = 10
FRAME_MS = 500

CACHE_MAX_FILES = 500
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
CAR_ALIASES = {
    "leadsled": ("leadsled", "ledsled"),
    "ledsled": ("ledsled", "leadsled"),
}


TRACK_BASES = {
    EventType.START: "Start",
    EventType.OVERTAKE: "Overtake",
    EventType.DAMAGE_MINOR: "Minor Damage",
    EventType.DAMAGE_MAJOR: "Major Damage",
    EventType.DESTROYED: "Destroyed",
    EventType.PIT_STOP: "Pitstop",
    EventType.ILLEGAL_MOVE: "Illegal",
    EventType.WARNING: "Illegal",
    EventType.DISQUALIFIED: "Disqualified",
    EventType.LAST_MINUTE_WIN: "Finish",
    EventType.FINISH: "Finish",
    EventType.PODIUM: "Podium",
}


class DynamicRaceGifRenderer:
    def __init__(self, track_dir: Path = TRACK_DIR, car_dir: Path = CAR_DIR, output_dir: Path = OUTPUT_DIR):
        self.track_dir = track_dir
        self.car_dir = car_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._file_index: dict[str, Path] | None = None

    def cleanup_cache(self, max_files: int = CACHE_MAX_FILES, max_age_seconds: int = CACHE_MAX_AGE_SECONDS) -> int:
        """Remove stale/excess generated GIFs. Returns the number of deleted files."""
        try:
            files = [path for path in self.output_dir.glob("*.gif") if path.is_file()]
        except OSError:
            return 0
        now = time.time()
        deleted = 0
        survivors = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            if now - stat.st_mtime > max_age_seconds:
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    pass
            else:
                survivors.append((stat.st_mtime, path))
        survivors.sort(reverse=True)
        for _, path in survivors[max_files:]:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                pass
        return deleted

    def render(self, event: RaceEvent) -> Path | None:
        if Image is None or ImageDraw is None or ImageFont is None or ImageOps is None:
            return None

        background = self._background_for(event)
        if not background:
            return None

        cars = self._event_cars(event)
        if not cars:
            return None

        cache_key = self._cache_key(event, background, cars)
        output = self.output_dir / f"{cache_key}.gif"
        if output.exists():
            return output

        try:
            base = Image.open(background).convert("RGBA")
            frames = self._frames(base, event, cars)
            if not frames:
                return None
            frames[0].save(
                output,
                save_all=True,
                append_images=frames[1:],
                duration=FRAME_MS,
                loop=0,
                optimize=True,
                disposal=2,
            )
            return output
        except OSError:
            return None

    def _background_for(self, event: RaceEvent) -> Path | None:
        base = TRACK_BASES.get(event.event_type)
        if event.event_type == EventType.LAP:
            base = "Minor Damage" if (event.media_key or "").startswith("lap_save") else "LapLeader"
        if not base:
            return None
        variant = self._variant(event, 3)
        return self._find_file(f"{base}{variant}.png")

    def _event_cars(self, event: RaceEvent) -> list[dict]:
        cars = list(event.participants or [])
        if event.actor:
            cars.insert(0, event.actor)
        if event.target:
            cars.append(event.target)

        seen = set()
        usable = []
        for car in cars:
            colour = str(car.get("colour") or "").lower()
            model = str(car.get("car_key") or "").lower()
            if not colour or not model:
                continue
            key = (car.get("team_id"), colour, model)
            if key in seen:
                continue
            sprite = self._car_sprite_path(colour, model)
            if not sprite:
                continue
            enriched = dict(car)
            enriched["sprite_path"] = sprite
            usable.append(enriched)
            seen.add(key)
        return usable

    def _frames(self, base, event: RaceEvent, cars: list[dict]) -> list:
        frames = []
        for index in range(FRAME_COUNT):
            progress = index / max(1, FRAME_COUNT - 1)
            frame = base.copy()
            draw = ImageDraw.Draw(frame)
            for car, x, y, width, flip in self._placements(event, cars, progress, base.size):
                self._paste_car(frame, car, x, y, width, flip)
            self._caption(draw, event, base.size)
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))
        return frames

    def _placements(self, event: RaceEvent, cars: list[dict], progress: float, size: tuple[int, int]) -> list[tuple[dict, int, int, int, bool]]:
        width, height = size
        road_y = int(height * 0.64)
        main = cars[0]
        target = cars[1] if len(cars) > 1 else None

        if event.event_type == EventType.START:
            return self._grid_placements(cars[:10], progress, size)
        if event.event_type == EventType.PODIUM:
            return [
                (car, int(width * x), int(height * y), int(width * w), False)
                for car, x, y, w in zip(cars[:3], (0.39, 0.14, 0.64), (0.44, 0.56, 0.58), (0.21, 0.18, 0.18))
            ]
        if event.event_type == EventType.OVERTAKE:
            placements = []
            if target:
                placements.append((target, int(width * (0.56 - progress * 0.08)), road_y + 40, int(width * 0.23), False))
            placements.append((main, int(width * (0.20 + progress * 0.36)), road_y + 95 - int(progress * 60), int(width * 0.27), False))
            return placements
        if event.event_type in {EventType.DAMAGE_MINOR, EventType.DAMAGE_MAJOR, EventType.DESTROYED} or (event.media_key or "").startswith("lap_save"):
            shake = [-12, 10, -8, 7, -5, 4, -3, 2, 0, 0][min(FRAME_COUNT - 1, int(progress * (FRAME_COUNT - 1)))]
            return [(main, int(width * 0.36) + shake, road_y + 58, int(width * 0.28), False)]
        if event.event_type in {EventType.ILLEGAL_MOVE, EventType.WARNING, EventType.DISQUALIFIED}:
            placements = []
            if target:
                placements.append((target, int(width * 0.50), road_y + 50, int(width * 0.24), False))
            placements.append((main, int(width * (0.24 + progress * 0.14)), road_y + 78, int(width * 0.26), False))
            return placements
        if event.event_type == EventType.PIT_STOP:
            bob = int(8 * abs(0.5 - progress))
            return [(main, int(width * 0.38), road_y + 65 - bob, int(width * 0.27), False)]
        if event.event_type in {EventType.FINISH, EventType.LAST_MINUTE_WIN}:
            return [(main, int(width * (0.13 + progress * 0.58)), road_y + 70, int(width * 0.27), False)]

        return [(main, int(width * (0.26 + progress * 0.12)), road_y + 70, int(width * 0.27), False)]

    def _grid_placements(self, cars: list[dict], progress: float, size: tuple[int, int]) -> list[tuple[dict, int, int, int, bool]]:
        width, height = size
        placements = []
        for index, car in enumerate(cars):
            row = index // 5
            col = index % 5
            x = int(width * (0.08 + col * 0.17 + progress * 0.05))
            y = int(height * (0.54 + row * 0.14))
            placements.append((car, x, y, int(width * 0.16), False))
        return placements

    def _paste_car(self, frame, car: dict, x: int, y: int, target_width: int, flip: bool) -> None:
        try:
            sprite = Image.open(car["sprite_path"]).convert("RGBA")
        except OSError:
            return
        if flip:
            sprite = ImageOps.mirror(sprite)
        scale = target_width / max(1, sprite.width)
        sprite = sprite.resize((target_width, max(1, int(sprite.height * scale))), Image.Resampling.LANCZOS)
        frame.alpha_composite(sprite, (x, y))

    def _caption(self, draw, event: RaceEvent, size: tuple[int, int]) -> None:
        width, height = size
        font = self._font(30)
        small = self._font(22)
        text = self._caption_text(event.message)
        if len(text) > 112:
            text = text[:109].rstrip() + "..."
        margin = 28
        box_top = height - 92
        draw.rounded_rectangle((margin, box_top, width - margin, height - 24), radius=14, fill=(0, 0, 0, 165))
        draw.text((margin + 22, box_top + 16), text, fill=(245, 232, 197), font=font)
        if event.lap:
            draw.text((margin + 22, box_top - 34), f"Lap {event.lap}", fill=(245, 232, 197), font=small)

    @staticmethod
    def _caption_text(message: str) -> str:
        text = message.replace("\n", " ")
        text = text.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", text).strip()

    def _car_sprite_path(self, colour: str, model: str) -> Path | None:
        names = []
        for model_name in CAR_ALIASES.get(model, (model,)):
            names.extend([
                f"{colour}_{model_name}.png",
                f"{colour}_{model_name.lower()}.png",
                f"{colour}_{model_name.title()}.png",
            ])
        for name in names:
            found = self._find_file(name, self.car_dir)
            if found:
                return found
        for model_name in CAR_ALIASES.get(model, (model,)):
            found = self._find_file(f"{model_name}.png", self.car_dir)
            if found:
                return found
        return None

    def _find_file(self, name: str, base_dir: Path | None = None) -> Path | None:
        directory = base_dir or self.track_dir
        direct = directory / name
        if direct.exists():
            return direct
        if self._file_index is None:
            self._file_index = {
                path.name.lower(): path
                for folder in (self.track_dir, self.car_dir)
                if folder.exists()
                for path in folder.glob("*.png")
            }
        return self._file_index.get(name.lower())

    def _variant(self, event: RaceEvent, count: int) -> int:
        digest = hashlib.sha1(f"{event.event_type.value}:{event.lap}:{event.message}".encode("utf-8")).hexdigest()
        return int(digest[:4], 16) % count + 1

    def _cache_key(self, event: RaceEvent, background: Path, cars: list[dict]) -> str:
        car_bits = "|".join(f"{car.get('team_id')}:{car.get('colour')}:{car.get('car_key')}" for car in cars)
        raw = f"{background.name}|{event.event_type.value}|{event.lap}|{event.message}|{car_bits}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _font(size: int):
        for path in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()
