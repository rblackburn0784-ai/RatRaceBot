from io import BytesIO
from pathlib import Path

from data.defaults import PARTS
from models.domain import Team
from models.enums import CarArchetype, PartSlot
from services.builds import BuildService, ILLEGAL_PART_DISQUALIFICATION_RISK

SHEET_SIZE = (1536, 1024)
CAR_ASSET_DIR = Path("assets/cars")

SLOT_LAYOUT = {
    PartSlot.ENGINE: {
        "box": (55, 105, 395, 260),
        "title": (150, 58),
        "line": ((395, 155), (520, 155), (580, 315)),
    },
    PartSlot.FUEL: {
        "box": (55, 375, 300, 525),
        "title": (145, 330),
        "line": ((300, 395), (375, 395), (410, 355)),
    },
    PartSlot.TYRES: {
        "box": (55, 765, 350, 915),
        "title": (150, 725),
        "line": ((350, 765), (410, 660), (500, 610)),
    },
    PartSlot.SUSPENSION: {
        "box": (445, 805, 725, 955),
        "title": (530, 765),
        "line": ((590, 805), (625, 745), (650, 650)),
    },
    PartSlot.BRAKES: {
        "box": (815, 805, 1095, 955),
        "title": (910, 765),
        "line": ((920, 805), (850, 710), (780, 650)),
    },
    PartSlot.BODY: {
        "box": (1120, 105, 1455, 260),
        "title": (1210, 58),
        "line": ((1120, 140), (1030, 140), (985, 205)),
    },
    PartSlot.TRANSMISSION: {
        "box": (1230, 410, 1490, 560),
        "title": (1295, 370),
        "line": ((1230, 420), (1190, 370), (1090, 370)),
    },
    PartSlot.TRICK: {
        "box": (1180, 770, 1470, 920),
        "title": (1290, 730),
        "line": ((1180, 770), (1110, 700), (1110, 615)),
    },
}


def car_asset_candidates(archetype: CarArchetype) -> list[Path]:
    safe_name = _safe_asset_name(archetype.value)
    return [
        CAR_ASSET_DIR / f"{archetype.name.lower()}.png",
        CAR_ASSET_DIR / f"{safe_name}.png",
        CAR_ASSET_DIR / f"{archetype.name.lower()}.jpg",
        CAR_ASSET_DIR / f"{safe_name}.jpg",
    ]


def render_parts_sheet(team: Team) -> BytesIO | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    image = Image.new("RGB", SHEET_SIZE, "white")
    draw = ImageDraw.Draw(image)
    fonts = _fonts(ImageFont)

    _draw_car(Image, image, draw, fonts, team)
    _draw_slots(draw, fonts, team)

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def _safe_asset_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def _fonts(ImageFont):
    def load(size: int, bold: bool = False):
        names = ["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf", "calibri.ttf"]
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    return {
        "title": load(38, True),
        "slot": load(34, True),
        "body": load(22),
        "small": load(18),
        "car": load(30, True),
    }


def _draw_car(Image, image, draw, fonts, team: Team) -> None:
    asset = next((path for path in car_asset_candidates(team.archetype) if path.exists()), None)
    car_area = (360, 230, 1175, 710)
    if asset:
        car = Image.open(asset).convert("RGBA")
        car.thumbnail((car_area[2] - car_area[0], car_area[3] - car_area[1]))
        x = car_area[0] + ((car_area[2] - car_area[0]) - car.width) // 2
        y = car_area[1] + ((car_area[3] - car_area[1]) - car.height) // 2
        image.paste(car, (x, y), car)
        return

    draw.rounded_rectangle((450, 335, 1085, 560), radius=45, outline="black", width=5, fill=(238, 238, 232))
    draw.rounded_rectangle((630, 255, 940, 385), radius=35, outline="black", width=5, fill=(224, 224, 218))
    draw.rectangle((480, 420, 610, 500), outline="black", width=4, fill=(214, 214, 208))
    draw.ellipse((500, 530, 675, 705), outline="black", width=10, fill=(30, 30, 30))
    draw.ellipse((890, 530, 1065, 705), outline="black", width=10, fill=(30, 30, 30))
    draw.ellipse((555, 585, 620, 650), fill=(190, 190, 185))
    draw.ellipse((945, 585, 1010, 650), fill=(190, 190, 185))
    draw.text((575, 435), team.car_name, fill="black", font=fonts["car"])
    draw.text((575, 480), team.archetype.value, fill=(70, 70, 70), font=fonts["body"])


def _draw_slots(draw, fonts, team: Team) -> None:
    installed_by_slot = {
        PARTS[key].slot: PARTS[key]
        for key in team.parts
        if key in PARTS
    }

    for slot, layout in SLOT_LAYOUT.items():
        box = layout["box"]
        title = layout["title"]
        line = layout["line"]
        installed = installed_by_slot.get(slot)
        draw.line(line, fill="black", width=3)
        draw.ellipse((line[-1][0] - 5, line[-1][1] - 5, line[-1][0] + 5, line[-1][1] + 5), fill="black")
        draw.text(title, slot.value.upper(), fill="black", font=fonts["slot"])
        draw.rounded_rectangle(box, radius=8, outline="black", width=3, fill=(252, 252, 250))
        if installed:
            draw.text((box[0] + 18, box[1] + 22), installed.name, fill="black", font=fonts["body"])
            mods = [f"{key.title()} {value:+d}" for key, value in installed.modifiers.as_dict().items() if value]
            if BuildService.is_illegal_part_key(installed.key):
                draw.text(
                    (box[0] + 18, box[1] + 52),
                    f"ILLEGAL: +{ILLEGAL_PART_DISQUALIFICATION_RISK}% DSQ risk",
                    fill=(170, 20, 20),
                    font=fonts["small"],
                )
                start_index = 2
            else:
                start_index = 1
            for index, line_text in enumerate(mods[:3], start=start_index):
                draw.text((box[0] + 18, box[1] + 22 + index * 30), line_text, fill=(60, 60, 60), font=fonts["small"])
        else:
            draw.text((box[0] + 18, box[1] + 24), "No part installed", fill=(95, 95, 95), font=fonts["body"])
            for y in range(box[1] + 78, box[3] - 20, 34):
                draw.line((box[0] + 18, y, box[2] - 18, y), fill=(190, 190, 190), width=1)
