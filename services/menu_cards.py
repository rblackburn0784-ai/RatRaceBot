from io import BytesIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_MENU_BACKGROUND = PROJECT_ROOT / "assets" / "menu" / "main_menu_background.png"
ADMIN_PANEL_BACKGROUND = PROJECT_ROOT / "assets" / "admin" / "admin_panel_background.png"

INK = (28, 24, 19)
RED = (145, 29, 27)
MUTED = (80, 67, 52)


def render_main_menu_card(show_admin: bool) -> BytesIO | None:
    groups = [
        ((100, 348, 368, 500), "TEAM", ["Create Team", "Team Edit"]),
        ((100, 523, 368, 675), "GARAGE", ["Pit Crew", "My Team"]),
        ((100, 706, 370, 858), "PROGRESS", ["Team Progress", "Team Title"]),
        ((1077, 348, 1377, 500), "RACE", ["Race Wizard", "Scrutineering"]),
        ((1077, 523, 1377, 675), "OFFERS", ["Sponsor Offers", "Rivalries"]),
        ((1077, 706, 1377, 858), "LEGENDS", ["Hall Of Fame", "Season History"]),
    ]
    footer = "Admin Panel + Status" if show_admin else "Private Driver Menu"
    return _render_card(
        MAIN_MENU_BACKGROUND,
        groups,
        banner=((420, 894, 1018, 1048), footer, ["Status Dashboard", "Select the matching control to open a tool."]),
    )


def render_admin_panel_card() -> BytesIO | None:
    groups = [
        ((58, 370, 322, 465), "SETUP", ["Bot, media, parts"]),
        ((58, 476, 322, 572), "TEAMS", ["Create, list, sheets"]),
        ((58, 582, 322, 678), "BUILD", ["Parts and deletion"]),
        ((58, 690, 322, 792), "RACES", ["Quick, demo, next"]),
        ((58, 802, 322, 910), "SEASON", ["History and close"]),
        ((410, 258, 1372, 760), "ADMIN COMMAND BOARD", [
            "Ratbot Init",
            "Media List",
            "Parts Catalogue",
            "Personalize AI",
            "Team List",
            "Team Create",
            "Team Sheet",
            "Team Delete",
            "Team Add Part",
            "Team Remove Part",
            "Tournament Wizard",
            "Tournament Create",
            "Tournament Add Team",
            "Tournament Standings",
            "Tournament Stats",
            "Season History",
            "Tournament Start Race",
            "Tournament Next Race",
            "Tournament Schedule",
            "Tournament Close",
            "Race Quick",
            "Race Demo",
            "Race Replay",
            "Backup DB",
        ]),
    ]
    return _render_card(
        ADMIN_PANEL_BACKGROUND,
        groups,
        banner=((410, 818, 1370, 1008), "COMMANDS NEEDING DETAILS", [
            "Buttons that need IDs or track keys open private command helpers.",
            "Race and tournament run buttons may post results to the channel.",
        ]),
    )


def _render_card(
    background_path: Path,
    groups: list[tuple[tuple[int, int, int, int], str, list[str]]],
    banner: tuple[tuple[int, int, int, int], str, list[str]] | None = None,
) -> BytesIO | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    if not background_path.exists():
        return None

    try:
        image = Image.open(background_path).convert("RGB")
    except OSError:
        return None

    draw = ImageDraw.Draw(image)
    fonts = _fonts(ImageFont)

    for box, title, lines in groups:
        _draw_group(draw, box, title, lines, fonts)

    if banner:
        box, title, lines = banner
        _draw_group(draw, box, title, lines, fonts, title_colour=RED)

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def _fonts(ImageFont):
    def load(size: int, bold: bool = False):
        names = ("segoeprb.ttf", "arialbd.ttf", "arial.ttf") if bold else ("segoepr.ttf", "arial.ttf", "calibri.ttf")
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    return {
        "title": load(30, True),
        "large_title": load(38, True),
        "body": load(24, True),
        "small": load(20, True),
    }


def _draw_group(
    draw,
    box: tuple[int, int, int, int],
    title: str,
    lines: list[str],
    fonts,
    title_colour=INK,
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    title_font = fonts["large_title"] if width > 550 else fonts["title"]
    body_font = fonts["body"] if height > 115 else fonts["small"]

    _centered_text(draw, title, (left + 12, top + 12, right - 12, top + 50), title_font, title_colour)

    if not lines:
        return

    if width > 700 and len(lines) > 8:
        _draw_two_column_lines(draw, (left + 26, top + 66, right - 26, bottom - 20), lines, fonts["small"])
        return

    line_top = top + 58
    line_height = max(24, min(42, (bottom - line_top - 12) // max(1, len(lines))))
    for index, line in enumerate(lines):
        y1 = line_top + index * line_height
        y2 = y1 + line_height
        colour = RED if index == 0 and title in {"RACE", "SETUP"} else INK
        _centered_text(draw, line, (left + 14, y1, right - 14, y2), body_font, colour)


def _draw_two_column_lines(draw, box: tuple[int, int, int, int], lines: list[str], font) -> None:
    left, top, right, bottom = box
    midpoint = (left + right) // 2
    first_column_count = (len(lines) + 1) // 2
    columns = [
        (lines[:first_column_count], (left, top, midpoint - 18, bottom)),
        (lines[first_column_count:], (midpoint + 18, top, right, bottom)),
    ]

    for column_lines, column_box in columns:
        if not column_lines:
            continue
        c_left, c_top, c_right, c_bottom = column_box
        line_height = max(24, min(38, (c_bottom - c_top) // len(column_lines)))
        for index, line in enumerate(column_lines):
            y1 = c_top + index * line_height
            y2 = y1 + line_height
            _centered_text(draw, line, (c_left, y1, c_right, y2), font, INK)


def _centered_text(draw, text: str, box: tuple[int, int, int, int], font, fill=INK) -> None:
    left, top, right, bottom = box
    center = ((left + right) // 2, (top + bottom) // 2)
    try:
        draw.text(center, text, fill=fill, font=font, anchor="mm")
        return
    except TypeError:
        pass

    text_box = draw.textbbox((0, 0), text, font=font)
    width = text_box[2] - text_box[0]
    height = text_box[3] - text_box[1]
    x = left + ((right - left) - width) // 2
    y = top + ((bottom - top) - height) // 2
    draw.text((x, y), text, fill=fill, font=font)
