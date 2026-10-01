from io import BytesIO
from pathlib import Path
from textwrap import wrap

from data.defaults import CREW_MEMBERS
from models.domain import Team
from models.enums import CrewSlot, PartSlot
from services.builds import BuildService
from services.garage_sheet import car_asset_candidates

SHEET_SIZE = (1397, 1126)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEAM_ASSET_DIR = PROJECT_ROOT / "assets" / "team"
TEAM_CARD_TEMPLATE = TEAM_ASSET_DIR / "team_card_template.png"

DRIVER_STAT_BOXES = {
    "nerve": (910, 384, 965, 438),
    "mechanics": (1207, 384, 1263, 438),
    "handling": (910, 431, 965, 485),
    "reflexes": (1207, 431, 1263, 485),
    "aggression": (910, 482, 965, 524),
    "showmanship": (1207, 482, 1263, 524),
}

EFFECTIVE_STAT_ROWS = (
    ("speed", 672),
    ("acceleration", 701),
    ("handling", 730),
    ("durability", 759),
    ("braking", 787),
    ("heat", 815),
    ("intimidation", 844),
    ("reliability", 873),
    ("pit_friendliness", 907),
)

PART_ROWS = [704, 745, 785, 825, 866, 906, 946, 986]

STAT_ABBREVIATIONS = {
    "speed": "Spd",
    "acceleration": "Acc",
    "handling": "Hnd",
    "durability": "Dur",
    "braking": "Brk",
    "heat": "Heat",
    "intimidation": "Int",
    "reliability": "Rel",
    "pit_friendliness": "Pit",
}

SLOT_LABELS = {
    PartSlot.ENGINE: "Engine",
    PartSlot.TYRES: "Tyres",
    PartSlot.SUSPENSION: "Susp.",
    PartSlot.BRAKES: "Brakes",
    PartSlot.BODY: "Body",
    PartSlot.TRANSMISSION: "Trans.",
    PartSlot.FUEL: "Fuel",
    PartSlot.TRICK: "Trick",
}


def render_team_sheet(team: Team) -> BytesIO | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    image = _background(Image)
    draw = ImageDraw.Draw(image)
    fonts = _fonts(ImageFont)

    _draw_car(Image, image, team)
    _draw_identity(draw, fonts, team)
    _draw_driver_stats(draw, fonts, team)
    _draw_effective_stats(draw, fonts, team)
    _draw_parts(draw, fonts, team)
    _draw_notes(draw, fonts, team)

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def _background(Image):
    if TEAM_CARD_TEMPLATE.exists():
        try:
            template = Image.open(TEAM_CARD_TEMPLATE).convert("RGB")
            if template.size != SHEET_SIZE:
                template = template.resize(SHEET_SIZE, Image.Resampling.LANCZOS)
            return template
        except OSError:
            pass
    return Image.new("RGB", SHEET_SIZE, (239, 225, 196))


def _fonts(ImageFont):
    def load(size: int, bold: bool = False):
        if bold:
            names = ("segoeprb.ttf", "comicbd.ttf", "arialbd.ttf", "arial.ttf")
        else:
            names = ("segoepr.ttf", "comic.ttf", "arial.ttf", "calibri.ttf")
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    return {
        "id": load(26, True),
        "body": load(27, True),
        "small": load(20, True),
        "tiny": load(17),
        "stat": load(31, True),
        "total": load(34, True),
        "note": load(19, True),
    }


def _draw_identity(draw, fonts, team: Team) -> None:
    _centered_text(draw, str(team.id or "-"), (1120, 75, 1290, 112), fonts["id"])
    draw.text((325, 297), _fit(team.name, 28), fill=(20, 20, 18), font=fonts["body"])
    draw.text((255, 348), _fit(team.driver_name, 34), fill=(20, 20, 18), font=fonts["body"])
    draw.text((305, 400), _fit(team.pit_crew_name, 30), fill=(20, 20, 18), font=fonts["body"])
    draw.text((305, 452), _fit(team.car_name, 28), fill=(20, 20, 18), font=fonts["body"])
    draw.text((330, 502), _fit(team.archetype.value, 27), fill=(20, 20, 18), font=fonts["body"])


def _draw_driver_stats(draw, fonts, team: Team) -> None:
    stats = team.stats
    for key, box in DRIVER_STAT_BOXES.items():
        value = getattr(stats, key)
        _centered_text(draw, str(value), box, fonts["stat"])

    draw.rectangle((1185, 528, 1236, 572), fill=(238, 221, 190))
    _centered_text(draw, str(stats.total), (1188, 520, 1233, 566), fonts["total"], fill=(154, 24, 24))


def _draw_effective_stats(draw, fonts, team: Team) -> None:
    stats = BuildService.effective_car_stats(team).as_dict()
    for key, y in EFFECTIVE_STAT_ROWS:
        value = stats[key]
        colour = (154, 24, 24) if key == "heat" and value > 8 else (20, 20, 18)
        _centered_text(draw, f"{value:+d}", (922, y - 18, 1080, y + 12), fonts["small"], fill=colour)
        _draw_stat_bar(draw, 1114, y + 5, value, key == "heat")


def _draw_stat_bar(draw, x: int, y: int, value: int, is_heat: bool) -> None:
    width = 150
    midpoint = x + width // 2
    draw.line((x, y, x + width, y), fill=(92, 76, 58), width=2)
    draw.line((midpoint, y - 5, midpoint, y + 5), fill=(92, 76, 58), width=2)
    scale = max(-6, min(14, value))
    if scale >= 0:
        end = midpoint + int((width // 2) * min(scale, 14) / 14)
        colour = (154, 24, 24) if is_heat and scale > 8 else (35, 35, 31)
        draw.line((midpoint, y, end, y), fill=colour, width=6)
    else:
        end = midpoint - int((width // 2) * abs(scale) / 6)
        draw.line((midpoint, y, end, y), fill=(154, 24, 24), width=6)


def _draw_parts(draw, fonts, team: Team) -> None:
    parts = BuildService.equipped_parts_by_slot(team)
    for index, slot in enumerate(PartSlot):
        if index >= len(PART_ROWS):
            break
        y = PART_ROWS[index]
        part = parts.get(slot)
        draw.text((122, y), SLOT_LABELS.get(slot, slot.value.title()), fill=(20, 20, 18), font=fonts["tiny"])
        if not part:
            draw.text((255, y), "-", fill=(85, 74, 60), font=fonts["tiny"])
            continue
        draw.text((230, y), _fit(part.name, 24), fill=(20, 20, 18), font=fonts["tiny"])
        key_text = "ILLEGAL" if BuildService.is_illegal_part_key(part.key) else "Fitted"
        key_colour = (154, 24, 24) if key_text == "ILLEGAL" else (20, 20, 18)
        draw.text((454, y), key_text, fill=key_colour, font=fonts["tiny"])
        draw.text((560, y), _modifier_text(part.modifiers), fill=(20, 20, 18), font=fonts["tiny"])


def _draw_notes(draw, fonts, team: Team) -> None:
    crew_lines = []
    for slot in CrewSlot:
        key = team.crew.get(slot.value)
        member = CREW_MEMBERS.get(key) if key else None
        if member:
            crew_lines.append(f"{slot.value.replace('_', ' ').title()}: {member.name}")

    notes = crew_lines or ["No custom pit crew assigned yet."]
    illegal_risk = BuildService.illegal_disqualification_risk_percent(team)
    if illegal_risk:
        notes.append(f"Illegal parts risk: {illegal_risk}% DSQ per race")

    y = 982
    for line in notes[:4]:
        for piece in wrap(line, width=55)[:2]:
            draw.text((795, y), piece, fill=(20, 20, 18), font=fonts["note"])
            y += 25
            if y > 1080:
                return


def _draw_car(Image, image, team: Team) -> None:
    asset = next((path for path in car_asset_candidates(team.archetype) if path.exists()), None)
    if not asset:
        return
    try:
        car = Image.open(asset).convert("RGBA")
    except OSError:
        return

    car.thumbnail((880, 410), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    x = 625 + (760 - car.width) // 2
    y = 55 + (320 - car.height) // 2
    layer.paste(car, (x, y), car)
    image.paste(Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB"))


def _modifier_text(modifiers) -> str:
    labels = []
    for key, value in modifiers.as_dict().items():
        if value:
            label = STAT_ABBREVIATIONS.get(key, key.replace("_", " ").title())
            labels.append(f"{label} {value:+d}")
    return _fit(", ".join(labels) if labels else "No stat change", 21)


def _fit(value: str, max_chars: int) -> str:
    value = value.strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars - 1].rstrip()}."


def _centered_text(draw, text: str, box: tuple[int, int, int, int], font, fill=(20, 20, 18)) -> None:
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    try:
        draw.text(center, text, fill=fill, font=font, anchor="mm")
        return
    except TypeError:
        pass

    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = box[0] + ((box[2] - box[0]) - width) // 2
    y = box[1] + ((box[3] - box[1]) - height) // 2 - 2
    draw.text((x, y), text, fill=fill, font=font)
