from io import BytesIO

from data.defaults import CREW_MEMBERS
from models.domain import Team
from models.enums import CrewSlot
from services.builds import BuildService

SHEET_SIZE = (1536, 1024)

SLOT_LAYOUT = {
    CrewSlot.CREW_CHIEF: {
        "person": (768, 250),
        "box": (55, 90, 430, 255),
        "line": ((430, 170), (650, 250)),
    },
    CrewSlot.LEAD_MECHANIC: {
        "person": (590, 455),
        "box": (55, 410, 430, 575),
        "line": ((430, 490), (545, 455)),
    },
    CrewSlot.TYRE_CHANGER: {
        "person": (945, 455),
        "box": (1105, 410, 1480, 575),
        "line": ((1105, 490), (990, 455)),
    },
    CrewSlot.FUEL_RUNNER: {
        "person": (690, 655),
        "box": (120, 760, 495, 925),
        "line": ((495, 830), (655, 655)),
    },
    CrewSlot.SPOTTER: {
        "person": (845, 655),
        "box": (1040, 760, 1415, 925),
        "line": ((1040, 830), (880, 655)),
    },
}


def render_crew_sheet(team: Team) -> BytesIO | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    image = Image.new("RGB", SHEET_SIZE, (250, 250, 246))
    draw = ImageDraw.Draw(image)
    fonts = _fonts(ImageFont)

    _draw_title(draw, fonts, team)
    _draw_crew_group(draw, fonts)
    _draw_slots(draw, fonts, team)
    _draw_totals(draw, fonts, team)

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


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
        "title": load(44, True),
        "slot": load(28, True),
        "body": load(22),
        "small": load(18),
        "tiny": load(16),
    }


def _draw_title(draw, fonts, team: Team) -> None:
    draw.text((535, 45), f"{team.pit_crew_name} Pit Crew", fill="black", font=fonts["title"])
    draw.text((610, 95), f"{team.name} - {team.car_name}", fill=(70, 70, 70), font=fonts["body"])


def _draw_crew_group(draw, fonts) -> None:
    draw.rounded_rectangle((500, 165, 1035, 760), radius=18, outline=(30, 30, 30), width=3, fill=(236, 235, 229))
    draw.text((665, 180), "PIT CREW", fill=(25, 25, 25), font=fonts["title"])
    for slot, layout in SLOT_LAYOUT.items():
        x, y = layout["person"]
        _draw_person(draw, x, y, slot)


def _draw_person(draw, x: int, y: int, slot: CrewSlot) -> None:
    palette = {
        CrewSlot.CREW_CHIEF: (70, 95, 130),
        CrewSlot.LEAD_MECHANIC: (125, 72, 52),
        CrewSlot.TYRE_CHANGER: (55, 105, 72),
        CrewSlot.FUEL_RUNNER: (130, 80, 40),
        CrewSlot.SPOTTER: (90, 70, 120),
    }
    colour = palette[slot]
    draw.ellipse((x - 28, y - 85, x + 28, y - 29), outline="black", width=3, fill=(224, 205, 178))
    draw.rounded_rectangle((x - 42, y - 30, x + 42, y + 78), radius=18, outline="black", width=3, fill=colour)
    draw.line((x - 42, y - 5, x - 92, y + 45), fill="black", width=5)
    draw.line((x + 42, y - 5, x + 92, y + 45), fill="black", width=5)
    draw.line((x - 20, y + 78, x - 50, y + 145), fill="black", width=6)
    draw.line((x + 20, y + 78, x + 50, y + 145), fill="black", width=6)
    if slot == CrewSlot.TYRE_CHANGER:
        draw.ellipse((x + 70, y + 25, x + 135, y + 90), outline="black", width=5, fill=(35, 35, 35))
    elif slot == CrewSlot.FUEL_RUNNER:
        draw.rectangle((x - 125, y + 20, x - 80, y + 95), outline="black", width=3, fill=(170, 35, 35))
    elif slot == CrewSlot.SPOTTER:
        draw.line((x + 65, y - 90, x + 95, y - 140), fill="black", width=4)
        draw.rectangle((x + 82, y - 145, x + 120, y - 125), outline="black", width=3, fill=(60, 60, 60))


def _draw_slots(draw, fonts, team: Team) -> None:
    for slot, layout in SLOT_LAYOUT.items():
        box = layout["box"]
        line = layout["line"]
        member_key = team.crew.get(slot.value)
        member = CREW_MEMBERS.get(member_key) if member_key else None
        draw.line(line, fill="black", width=3)
        draw.ellipse((line[-1][0] - 6, line[-1][1] - 6, line[-1][0] + 6, line[-1][1] + 6), fill="black")
        draw.rounded_rectangle(box, radius=8, outline="black", width=3, fill=(255, 255, 253))
        draw.text((box[0] + 18, box[1] + 14), slot.value.replace("_", " ").title(), fill="black", font=fonts["slot"])
        if member:
            draw.text((box[0] + 18, box[1] + 52), member.name, fill=(20, 20, 20), font=fonts["body"])
            mods = [f"{key.title()} {value:+d}" for key, value in member.modifiers.as_dict().items() if value]
            for index, line_text in enumerate(mods[:3], start=1):
                draw.text((box[0] + 18, box[1] + 52 + index * 27), line_text, fill=(60, 60, 60), font=fonts["small"])
        else:
            draw.text((box[0] + 18, box[1] + 58), "No crew member assigned", fill=(95, 95, 95), font=fonts["body"])
            draw.line((box[0] + 18, box[1] + 104, box[2] - 18, box[1] + 104), fill=(190, 190, 190), width=1)


def _draw_totals(draw, fonts, team: Team) -> None:
    stats = BuildService.crew_stats(team)
    mods = [f"{key.replace('_', ' ').title()} {value:+d}" for key, value in stats.as_dict().items() if value]
    lines = [" | ".join(mods[index:index + 3]) for index in range(0, len(mods), 3)] if mods else ["No crew stat modifiers yet"]
    draw.rounded_rectangle((510, 810, 1025, 930), radius=8, outline="black", width=3, fill=(255, 255, 253))
    draw.text((535, 830), "Overall Crew Stats", fill="black", font=fonts["slot"])
    for index, line in enumerate(lines[:2]):
        draw.text((535, 875 + index * 26), line, fill=(55, 55, 55), font=fonts["small"])
