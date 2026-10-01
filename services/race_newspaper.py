from __future__ import annotations

from io import BytesIO
from pathlib import Path
import random
import re
from typing import Iterable

import discord

from models.domain import RaceEvent, RaceResult
from models.enums import EventType
from services.engagement import hype_score

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow is optional at runtime; callers fall back to embeds.
    Image = None
    ImageDraw = None
    ImageFont = None


WIDTH = 1450
HEIGHT = 1900
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "assets" / "newspaper" / "newspaper_template.png"
PAPER = (237, 222, 190)
INK = (30, 28, 23)
FADED = (88, 76, 58)
RED = (125, 40, 27)
BLUE = (30, 58, 77)
BOX = (51, 45, 35)


def render_race_newspaper(
    *,
    results: list[RaceResult],
    events: list[RaceEvent],
    title: str,
    track_name: str,
    weather_name: str,
    prediction_embed: discord.Embed | None = None,
    rivalry_embed: discord.Embed | None = None,
    reward_embeds: list[discord.Embed] | None = None,
) -> BytesIO | None:
    if Image is None or ImageDraw is None or ImageFont is None or not results:
        return None

    ordered = sorted(results, key=lambda result: result.position)
    winner = ordered[0]
    rewards = reward_embeds or []

    fonts = _fonts()
    image = _template_image()
    if image:
        _draw_template_report(
            image=image,
            fonts=fonts,
            ordered=ordered,
            events=events,
            title=title,
            track_name=track_name,
            weather_name=weather_name,
            prediction_embed=prediction_embed,
            rivalry_embed=rivalry_embed,
            reward_embeds=rewards,
        )
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output

    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    _paper_texture(image)
    draw = ImageDraw.Draw(image)

    _draw_masthead(draw, title, track_name, weather_name, winner, fonts)
    _draw_race_art(draw, (34, 360, WIDTH - 34, 790), winner, track_name, fonts)

    _section(
        draw,
        (34, 815, 465, 1145),
        "RACE RECAP",
        _race_recap_lines(ordered, title, track_name, weather_name),
        fonts,
        RED,
    )
    _section(
        draw,
        (490, 815, 915, 1145),
        "FINAL STANDINGS",
        _standings_lines(ordered),
        fonts,
        BLUE,
    )
    _section(
        draw,
        (940, 815, WIDTH - 34, 1145),
        "RACE AWARDS",
        _award_lines(ordered),
        fonts,
        RED,
    )

    _section(
        draw,
        (34, 1170, 410, 1395),
        _hype_title(results, events),
        _hype_lines(results, events, title),
        fonts,
        BLUE,
    )
    _section(
        draw,
        (435, 1170, 840, 1395),
        "TRACK RECORD BOARD",
        _embed_lines(_find_embed(rewards, "Track Record Board"), "No new records this time."),
        fonts,
        RED,
    )
    _section(
        draw,
        (865, 1170, WIDTH - 34, 1395),
        "WINNER'S QUOTE",
        _winner_quote_lines(rewards, winner),
        fonts,
        BLUE,
    )

    _section(
        draw,
        (34, 1420, 255, 1660),
        "SCANDAL NOTE",
        _scandal_lines(ordered),
        fonts,
        RED,
    )
    _section(
        draw,
        (280, 1420, 525, 1660),
        "RIVALRY WATCH",
        _embed_lines(rivalry_embed, "No grudges boiled over."),
        fonts,
        BLUE,
    )
    _section(
        draw,
        (550, 1420, 910, 1660),
        "NEW ACHIEVEMENTS",
        _embed_lines(_find_embed(rewards, "New Achievements"), "No new badges unlocked."),
        fonts,
        RED,
    )
    _section(
        draw,
        (935, 1420, WIDTH - 34, 1660),
        "SPONSOR OFFERS",
        _embed_lines(_find_embed(rewards, "Sponsor Offers"), "No fresh sponsor interest."),
        fonts,
        BLUE,
    )

    _section(
        draw,
        (34, 1685, 485, HEIGHT - 34),
        "PREDICTION RESULTS",
        _embed_lines(prediction_embed, "Nobody made a pick."),
        fonts,
        BLUE,
    )
    _section(
        draw,
        (510, 1685, WIDTH - 34, HEIGHT - 34),
        "BIG MOVE",
        _big_move_lines(ordered),
        fonts,
        RED,
        body_font=fonts["headline"],
    )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _template_image():
    if not TEMPLATE_PATH.exists():
        return None
    try:
        return Image.open(TEMPLATE_PATH).convert("RGB")
    except OSError:
        return None


def _draw_template_report(
    *,
    image,
    fonts: dict[str, object],
    ordered: list[RaceResult],
    events: list[RaceEvent],
    title: str,
    track_name: str,
    weather_name: str,
    prediction_embed: discord.Embed | None,
    rivalry_embed: discord.Embed | None,
    reward_embeds: list[discord.Embed],
) -> None:
    draw = ImageDraw.Draw(image)
    winner = ordered[0]
    template_fonts = _template_fonts()

    _centered_fit_shrink(
        draw,
        _headline(winner, track_name).upper(),
        (22, 170, image.width - 22, 240),
        template_fonts["headline"],
        INK,
        min_size=30,
    )
    _centered_fit_shrink(
        draw,
        f"{winner.driver_name} brings {winner.team_name} home first in {weather_name} at {track_name}.",
        (64, 246, image.width - 64, 285),
        template_fonts["subhead"],
        INK,
        min_size=18,
    )
    _draw_stamp(draw, title, track_name, weather_name, template_fonts)

    _draw_lines(draw, (34, 646, 355, 850), _race_recap_lines(ordered, title, track_name, weather_name), template_fonts["body_bold"], line_height=19)
    _draw_lines(draw, (410, 646, 690, 850), _template_standings_lines(ordered), template_fonts["body_bold"], line_height=19)
    _draw_award_values(draw, ordered, template_fonts)

    hype_score_value, hype_label = hype_score(ordered, events)
    _draw_fit_text(draw, title, (115, 917, 220, 934), template_fonts["small_italic"], INK, min_size=9)
    _draw_fit_text(draw, str(hype_score_value), (242, 917, 272, 934), template_fonts["small_italic"], INK, min_size=10)
    _draw_fit_text(draw, str(sum(result.overtakes for result in ordered)), (104, 958, 140, 974), template_fonts["body_bold"], INK, min_size=10)
    _draw_fit_text(draw, str(sum(result.crashes for result in ordered)), (86, 979, 122, 995), template_fonts["body_bold"], INK, min_size=10)
    _draw_fit_text(draw, str(sum(result.illegal_moves for result in ordered)), (128, 999, 164, 1015), template_fonts["body_bold"], INK, min_size=10)
    _draw_fit_text(draw, str(sum(result.near_misses for result in ordered)), (112, 1020, 148, 1036), template_fonts["body_bold"], INK, min_size=10)

    _draw_template_records(draw, reward_embeds, template_fonts)
    _draw_template_quote(draw, reward_embeds, winner, template_fonts)
    _draw_lines(draw, (46, 1150, 184, 1212), _scandal_lines(ordered)[1:], template_fonts["small"], line_height=14, center=True)
    _draw_lines(draw, (238, 1118, 408, 1284), _embed_lines(rivalry_embed, "No grudges boiled over.")[:5], template_fonts["small_bold"], line_height=18)
    _draw_lines(draw, (472, 1115, 716, 1288), _embed_lines(_find_embed(reward_embeds, "New Achievements"), "No new badges unlocked.")[:8], template_fonts["small_bold"], line_height=18)
    _draw_lines(draw, (760, 1146, 1070, 1278), _embed_lines(_find_embed(reward_embeds, "Sponsor Offers"), "No fresh sponsor interest.")[:6], template_fonts["small_bold"], line_height=22)
    _draw_template_prediction(draw, prediction_embed, winner, template_fonts)
    _centered_fit_shrink(draw, _big_move_lines(ordered)[0], (465, 1348, 1025, 1396), template_fonts["big_move"], INK, min_size=24)


def _template_fonts() -> dict[str, object]:
    font_dir = "C:/Windows/Fonts"
    return {
        "headline": _font((f"{font_dir}/impact.ttf", f"{font_dir}/arialbd.ttf"), 46),
        "subhead": _font((f"{font_dir}/georgiai.ttf", f"{font_dir}/ariali.ttf", f"{font_dir}/arial.ttf"), 26),
        "section": _font((f"{font_dir}/georgiab.ttf", f"{font_dir}/arialbd.ttf"), 23),
        "body_bold": _font((f"{font_dir}/arialbd.ttf",), 15),
        "body": _font((f"{font_dir}/arial.ttf",), 15),
        "small_bold": _font((f"{font_dir}/arialbd.ttf",), 13),
        "small": _font((f"{font_dir}/arial.ttf",), 13),
        "small_italic": _font((f"{font_dir}/georgiai.ttf", f"{font_dir}/ariali.ttf", f"{font_dir}/arial.ttf"), 14),
        "quote": _font((f"{font_dir}/georgiai.ttf", f"{font_dir}/ariali.ttf", f"{font_dir}/arial.ttf"), 25),
        "stamp": _font((f"{font_dir}/arialbd.ttf",), 14),
        "big_move": _font((f"{font_dir}/georgiai.ttf", f"{font_dir}/impact.ttf", f"{font_dir}/arialbd.ttf"), 38),
    }


def _headline(winner: RaceResult, track_name: str) -> str:
    return f"{winner.team_name} Take {track_name}"


def _draw_stamp(draw, title: str, track_name: str, weather_name: str, fonts: dict[str, object]) -> None:
    stamp_title = re.sub(r"\s+Results.*$", "", title, flags=re.IGNORECASE).strip()
    stamp_title = stamp_title.replace("Tournament Race", "Tourney Race")
    _centered_fit_shrink(draw, stamp_title.upper(), (960, 36, 1082, 66), fonts["stamp"], (236, 225, 198), min_size=10)
    _centered_fit_shrink(draw, track_name.upper(), (965, 96, 1078, 119), fonts["stamp"], INK, min_size=9)
    _centered_fit_shrink(draw, weather_name.upper(), (965, 122, 1078, 142), fonts["stamp"], INK, min_size=9)


def _draw_award_values(draw, ordered: list[RaceResult], fonts: dict[str, object]) -> None:
    awards = (
        ("overtakes", 660),
        ("crashes", 683),
        ("illegal_moves", 706),
        ("last_minute_wins", 729),
        ("near_misses", 752),
        ("pit_stops", 776),
        ("damage", 803),
        ("damage", 828),
    )
    for key, y in awards:
        leader = max(ordered, key=lambda result: (int(getattr(result, key, 0)), result.points))
        value = int(getattr(leader, key, 0))
        _draw_fit_text(draw, f"{leader.team_name} - {value}", (895, y, 1074, y + 18), fonts["body_bold"], INK, min_size=10)


def _draw_template_records(draw, reward_embeds: list[discord.Embed], fonts: dict[str, object]) -> None:
    record_lines = _embed_lines(_find_embed(reward_embeds, "Track Record Board"), "No new records this time.")[:5]
    if len(record_lines) == 1 and record_lines[0] == "No new records this time.":
        _draw_fit_text(draw, "No new records this time.", (518, 924, 685, 942), fonts["small_bold"], INK, min_size=9)
        return
    labels = ("Fastest Winner:", "Fastest Overall Time:", "Most Crashes In Race:", "Most Overtakes In Race:", "Most Chaotic Race:")
    y = 924
    for label, line in zip(labels, record_lines):
        value = _clean(line).replace(label, "").strip()
        _draw_fit_text(draw, value or _clean(line), (528, y, 684, y + 18), fonts["small_bold"], INK, min_size=9)
        y += 25


def _draw_template_quote(draw, reward_embeds: list[discord.Embed], winner: RaceResult, fonts: dict[str, object]) -> None:
    lines = _winner_quote_lines(reward_embeds, winner)
    quote = lines[0] if lines else '"We found another gear when it mattered."'
    quote_lines = _wrap(draw, _clean(quote), fonts["quote"], 320)
    y = 916
    for line in quote_lines[:2]:
        _centered_fit_shrink(draw, line, (742, y, 1070, y + 30), fonts["quote"], INK, min_size=17)
        y += 29

    detail_lines = [line for line in lines[1:] if ":" in line]
    details = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in detail_lines}
    _draw_fit_text(draw, details.get("Driver", winner.driver_name), (780, 994, 932, 1010), fonts["small_bold"], INK, min_size=9)
    _draw_fit_text(draw, f"P{winner.position}", (1032, 994, 1080, 1010), fonts["small_bold"], INK, min_size=9)
    _draw_fit_text(draw, details.get("Trait Flavor", "Race Winner"), (800, 1019, 1074, 1035), fonts["small_bold"], INK, min_size=9)
    _draw_fit_text(draw, details.get("Reputation", "Front Runner"), (817, 1040, 1074, 1056), fonts["small_bold"], INK, min_size=9)


def _draw_template_prediction(draw, prediction_embed: discord.Embed | None, winner: RaceResult, fonts: dict[str, object]) -> None:
    lines = _embed_lines(prediction_embed, "Nobody made a pick.")
    correct = lines[-1] if lines else "Nobody made a pick."
    _draw_fit_text(draw, winner.team_name, (96, 1366, 300, 1384), fonts["body_bold"], INK, min_size=11)
    _draw_fit_text(draw, _clean(correct), (126, 1390, 314, 1408), fonts["body_bold"], INK, min_size=11)


def _draw_lines(
    draw,
    box: tuple[int, int, int, int],
    lines: list[str],
    font,
    line_height: int,
    center: bool = False,
) -> None:
    left, top, right, bottom = box
    y = top
    for raw in lines:
        for line in _wrap(draw, _clean(raw), font, right - left):
            if y + line_height > bottom:
                return
            if center:
                _centered_fit_shrink(draw, line, (left, y, right, y + line_height), font, INK, min_size=9)
            else:
                draw.text((left, y), line, fill=INK, font=font)
            y += line_height
        y += 2


def _draw_fit_text(draw, text: str, box: tuple[int, int, int, int], font, fill, min_size: int = 8) -> None:
    left, top, right, _bottom = box
    value = _clean(text)
    active_font = _shrink_font(draw, value, font, right - left, min_size)
    while _text_width(draw, value, active_font) > right - left and len(value) > 6:
        value = value[:-2].rstrip() + "."
    draw.text((left, top), value, fill=fill, font=active_font)


def _centered_fit_shrink(draw, text: str, box: tuple[int, int, int, int], font, fill, min_size: int = 8) -> None:
    active_font = _shrink_font(draw, _clean(text), font, box[2] - box[0], min_size)
    _centered_fit(draw, _clean(text), box, active_font, fill)


def _shrink_font(draw, text: str, font, width: int, min_size: int):
    if not hasattr(font, "path") or not hasattr(font, "size"):
        return font
    size = int(font.size)
    while size > min_size and _text_width(draw, text, font) > width:
        size -= 1
        font = ImageFont.truetype(font.path, size)
    return font


def _paper_texture(image) -> None:
    pixels = image.load()
    rng = random.Random("blacktop-gazette-paper")
    for y in range(0, HEIGHT, 2):
        for x in range(0, WIDTH, 2):
            grain = rng.randint(-13, 11)
            r = max(0, min(255, PAPER[0] + grain))
            g = max(0, min(255, PAPER[1] + grain))
            b = max(0, min(255, PAPER[2] + grain))
            pixels[x, y] = (r, g, b)
            if x + 1 < WIDTH:
                pixels[x + 1, y] = (r, g, b)
            if y + 1 < HEIGHT:
                pixels[x, y + 1] = (r, g, b)
            if x + 1 < WIDTH and y + 1 < HEIGHT:
                pixels[x + 1, y + 1] = (r, g, b)


def _font(candidates: Iterable[str], size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fonts() -> dict[str, object]:
    font_dir = "C:/Windows/Fonts"
    return {
        "masthead": _font((f"{font_dir}/impact.ttf", f"{font_dir}/arialbd.ttf"), 112),
        "headline": _font((f"{font_dir}/impact.ttf", f"{font_dir}/arialbd.ttf"), 54),
        "subhead": _font((f"{font_dir}/georgiai.ttf", f"{font_dir}/ariali.ttf", f"{font_dir}/arial.ttf"), 32),
        "section": _font((f"{font_dir}/georgiab.ttf", f"{font_dir}/arialbd.ttf"), 28),
        "body_bold": _font((f"{font_dir}/arialbd.ttf",), 24),
        "body": _font((f"{font_dir}/arial.ttf",), 23),
        "small": _font((f"{font_dir}/arial.ttf",), 20),
    }


def _draw_masthead(draw, title: str, track_name: str, weather_name: str, winner: RaceResult, fonts: dict[str, object]) -> None:
    _centered(draw, "BLACKTOP GAZETTE", (0, 20, WIDTH, 145), fonts["masthead"], INK)
    draw.line((34, 150, WIDTH - 34, 150), fill=INK, width=5)
    _centered(draw, "* ALL THE DIRT. NONE OF THE FILTER. *", (0, 154, WIDTH, 192), fonts["section"], INK)
    draw.line((34, 196, WIDTH - 34, 196), fill=INK, width=3)

    stamp_box = (WIDTH - 210, 38, WIDTH - 34, 142)
    draw.rectangle(stamp_box, outline=RED, width=4)
    _centered(draw, "RACE", (stamp_box[0], 48, stamp_box[2], 75), fonts["section"], RED)
    _centered(draw, "EDITION", (stamp_box[0], 80, stamp_box[2], 106), fonts["section"], RED)
    _centered(draw, weather_name.upper()[:18], (stamp_box[0], 112, stamp_box[2], 136), fonts["small"], INK)

    draw.rectangle((34, 38, 190, 142), outline=INK, width=3)
    _centered(draw, "SPECIAL", (34, 48, 190, 76), fonts["section"], RED)
    _centered(draw, "RACE", (34, 80, 190, 108), fonts["section"], RED)
    _centered(draw, "EDITION", (34, 112, 190, 138), fonts["section"], RED)

    headline = f"{winner.team_name} Take {track_name}"
    _centered_fit(draw, headline.upper(), (34, 220, WIDTH - 34, 292), fonts["headline"], INK)
    subtitle = f"{winner.driver_name} brings {winner.team_name} home first in {weather_name} at {track_name}."
    _centered_fit(draw, subtitle, (34, 300, WIDTH - 34, 345), fonts["subhead"], INK)


def _draw_race_art(draw, box: tuple[int, int, int, int], winner: RaceResult, track_name: str, fonts: dict[str, object]) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, fill=(43, 43, 38), outline=INK, width=4)
    rng = random.Random(f"{winner.team_name}:{track_name}")
    for y in range(top, bottom):
        shade = int(35 + (y - top) / max(1, bottom - top) * 45)
        draw.line((left + 2, y, right - 2, y), fill=(shade, shade, shade))
    for _ in range(90):
        x = rng.randint(left + 10, right - 10)
        y = rng.randint(top + 10, bottom - 10)
        value = rng.randint(80, 145)
        draw.point((x, y), fill=(value, value, value))

    horizon = bottom - 120
    draw.rectangle((left + 2, top + 2, right - 2, top + 95), fill=(24, 25, 24))
    for x in range(left + 25, right, 55):
        h = rng.randint(18, 70)
        draw.rectangle((x, top + 95 - h, x + 22, top + 95), fill=(50, 49, 44))
    for x in range(left + 90, right - 50, 180):
        draw.ellipse((x, top + 75, x + 18, top + 93), fill=(234, 216, 147))
        draw.line((x + 9, top + 93, x + 9, horizon), fill=(94, 85, 65), width=2)

    draw.line((left + 25, horizon, right - 25, horizon), fill=(202, 194, 170), width=4)
    for offset in range(0, 160, 24):
        draw.arc((left + 120 + offset, horizon - 80 + offset, right - 120 - offset, bottom + 90), 195, 345, fill=(196, 187, 160), width=3)

    car_y = bottom - int(185 * 1.5)
    _draw_car(draw, left + 160, car_y, 1.5, winner.team_name[:12].upper())
    for x, scale in ((right - 470, 0.95), (right - 285, 0.78), (left + 650, 0.68)):
        _draw_car(draw, x, bottom - int(150 * scale) - rng.randint(20, 75), scale, "")

    draw.rectangle((left + 20, bottom - 58, right - 20, bottom - 20), fill=(24, 24, 22))
    _centered(draw, f"{winner.team_name.upper()} OWN THE NIGHT AT {track_name.upper()}", (left + 24, bottom - 56, right - 24, bottom - 22), fonts["section"], (230, 220, 190))


def _draw_car(draw, x: int, y: int, scale: float, door_text: str) -> None:
    s = scale
    body = (x + int(40 * s), y + int(45 * s), x + int(250 * s), y + int(105 * s))
    roof = (x + int(95 * s), y + int(5 * s), x + int(205 * s), y + int(70 * s))
    hood = (x + int(10 * s), y + int(60 * s), x + int(72 * s), y + int(95 * s))
    wheel_1 = (x + int(35 * s), y + int(88 * s), x + int(95 * s), y + int(148 * s))
    wheel_2 = (x + int(190 * s), y + int(88 * s), x + int(260 * s), y + int(158 * s))
    fill = (24, 24, 22)
    edge = (210, 196, 160)
    draw.rounded_rectangle(body, radius=int(18 * s), fill=fill, outline=edge, width=max(2, int(3 * s)))
    draw.rounded_rectangle(roof, radius=int(16 * s), fill=fill, outline=edge, width=max(2, int(3 * s)))
    draw.rounded_rectangle(hood, radius=int(14 * s), fill=fill, outline=edge, width=max(2, int(3 * s)))
    draw.ellipse(wheel_1, fill=(8, 8, 8), outline=edge, width=max(2, int(3 * s)))
    draw.ellipse(wheel_2, fill=(8, 8, 8), outline=edge, width=max(2, int(3 * s)))
    draw.rectangle((x + int(110 * s), y + int(25 * s), x + int(190 * s), y + int(62 * s)), outline=edge, width=max(1, int(2 * s)))
    if door_text and s > 1:
        draw.text((x + int(105 * s), y + int(66 * s)), door_text, fill=(218, 207, 174), font=_fonts()["small"])


def _section(
    draw,
    box: tuple[int, int, int, int],
    title: str,
    lines: list[str],
    fonts: dict[str, object],
    header_color: tuple[int, int, int],
    body_font=None,
) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, outline=BOX, width=3)
    draw.rectangle((left + 3, top + 3, right - 3, top + 38), fill=header_color)
    header_font = fonts["section"]
    if _text_width(draw, title.upper(), header_font) > right - left - 16:
        header_font = fonts["body_bold"]
    if _text_width(draw, title.upper(), header_font) > right - left - 16:
        header_font = fonts["small"]
    _centered_fit(draw, title.upper(), (left + 5, top + 5, right - 5, top + 37), header_font, (236, 225, 198))
    y = top + 50
    font = body_font or fonts["body"]
    for raw in lines:
        chunks = _wrap(draw, _clean(raw), font, right - left - 28)
        for chunk in chunks:
            if y + 24 > bottom - 12:
                return
            draw.text((left + 14, y), chunk, fill=INK, font=font)
            y += 27 if body_font else 25
        y += 5


def _race_recap_lines(ordered: list[RaceResult], title: str, track_name: str, weather_name: str) -> list[str]:
    winner = ordered[0]
    mover = max(ordered, key=lambda result: (result.overtakes, result.points, -result.position))
    hardest_hit = max(ordered, key=lambda result: (result.damage, result.crashes, result.tyre_wear))
    trouble = max(ordered, key=lambda result: (result.illegal_moves + result.warnings * 2, result.illegal_moves))
    pit_hero = max(ordered, key=lambda result: (result.pit_stops, -result.damage))
    near_miss = max(ordered, key=lambda result: (result.near_misses, result.points))
    return [
        title,
        f"{track_name} | Weather: {weather_name}",
        f"Winner: {winner.team_name} - {winner.driver_name}",
        f"Biggest Mover: {mover.team_name} - {mover.overtakes} overtakes",
        f"Hardest Hit: {hardest_hit.team_name} - {hardest_hit.damage}% damage",
        f"Most Questionable: {trouble.team_name} - {trouble.illegal_moves} illegal, {trouble.warnings} warnings",
        f"Pit Lane Hero: {pit_hero.team_name} - {pit_hero.pit_stops} stops",
        f"Near Miss Nerves: {near_miss.team_name} - {near_miss.near_misses} near misses",
    ]


def _standings_lines(ordered: list[RaceResult]) -> list[str]:
    lines = []
    for result in ordered[:10]:
        status = "DSQ" if result.disqualified else "DNF" if result.dnf else f"{result.points} pts"
        lines.append(f"{result.position}. {result.team_name} ({result.driver_name}) - {status}")
    return lines


def _template_standings_lines(ordered: list[RaceResult]) -> list[str]:
    lines = []
    for result in ordered[:10]:
        status = "DSQ" if result.disqualified else "DNF" if result.dnf else f"{result.points} pts"
        lines.append(f"{result.team_name} ({result.driver_name}) - {status}")
    return lines


def _award_lines(ordered: list[RaceResult]) -> list[str]:
    awards = (
        ("overtakes", "Overtakes"),
        ("crashes", "Crashes"),
        ("illegal_moves", "Illegal Moves"),
        ("last_minute_wins", "Last-Minute Wins"),
        ("near_misses", "Near Misses"),
        ("pit_stops", "Pit Stops"),
        ("damage", "Carryover Damage"),
        ("damage", "Peak Damage"),
    )
    lines = []
    for key, label in awards:
        leader = max(ordered, key=lambda result: (int(getattr(result, key, 0)), result.points))
        value = int(getattr(leader, key, 0))
        lines.append(f"{label}: {leader.team_name} - {value}")
    return lines


def _hype_title(results: list[RaceResult], events: list[RaceEvent]) -> str:
    _score, label = hype_score(results, events)
    return f"CROWD HYPE: {label}"


def _hype_lines(results: list[RaceResult], events: list[RaceEvent], title: str) -> list[str]:
    score, _label = hype_score(results, events)
    return [
        f"{title} scored {score} hype.",
        f"Overtakes: {sum(result.overtakes for result in results)}",
        f"Crashes: {sum(result.crashes for result in results)}",
        f"Illegal moves: {sum(result.illegal_moves for result in results)}",
        f"Near misses: {sum(result.near_misses for result in results)}",
        f"DNF/DSQ chaos: {sum(1 for event in events if event.event_type in {EventType.DESTROYED, EventType.DISQUALIFIED})}",
    ]


def _winner_quote_lines(rewards: list[discord.Embed], winner: RaceResult) -> list[str]:
    interview = _find_embed(rewards, "Post-Race Interview")
    if interview and interview.description:
        lines = [interview.description.strip()]
        for field in interview.fields:
            lines.append(f"{field.name}: {field.value}")
        return lines[:5]
    return [
        '"The crew earned that one. I mostly held on and looked busy."',
        f"Driver: {winner.driver_name}",
        f"Finish: P{winner.position}",
    ]


def _scandal_lines(ordered: list[RaceResult]) -> list[str]:
    trouble = max(ordered, key=lambda result: (result.warnings + result.illegal_moves * 2, result.crashes))
    if trouble.warnings <= 0 and trouble.illegal_moves <= 0:
        return ["Clean enough for the officials, which is suspicious in its own way."]
    return [
        "WARNING!",
        f"{trouble.team_name} drew {trouble.warnings} warning(s)",
        f"and {trouble.illegal_moves} illegal move(s).",
        f"Damage report: {trouble.damage}%",
    ]


def _big_move_lines(ordered: list[RaceResult]) -> list[str]:
    mover = max(ordered, key=lambda result: (result.overtakes, result.near_misses, result.points))
    if mover.overtakes:
        return [f"{mover.team_name} made {mover.overtakes} overtakes!"]
    return [f"{ordered[0].team_name} held firm when it mattered!"]


def _find_embed(embeds: list[discord.Embed], title: str) -> discord.Embed | None:
    for embed in embeds:
        if embed.title and embed.title.startswith(title):
            return embed
    return None


def _embed_lines(embed: discord.Embed | None, empty: str) -> list[str]:
    if not embed:
        return [empty]
    lines = []
    if embed.description:
        lines.extend(str(embed.description).splitlines())
    for field in embed.fields:
        if str(field.name).lower() not in {"unlocked", "fresh interest", "new records", "heating up", "correct picks"}:
            lines.append(str(field.name))
        lines.extend(str(field.value).splitlines())
    return lines[:12] if lines else [empty]


def _clean(text: str) -> str:
    return re.sub(r"\*\*|`", "", str(text)).replace("\n", " ").strip()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(draw, text: str, font) -> int:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left


def _centered(draw, text: str, box: tuple[int, int, int, int], font, fill) -> None:
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), text, font=font)
    width = text_box[2] - text_box[0]
    height = text_box[3] - text_box[1]
    draw.text((left + (right - left - width) / 2, top + (bottom - top - height) / 2 - 2), text, fill=fill, font=font)


def _centered_fit(draw, text: str, box: tuple[int, int, int, int], font, fill) -> None:
    left, top, right, bottom = box
    max_width = right - left
    value = text
    while _text_width(draw, value, font) > max_width and len(value) > 10:
        value = value[:-2].rstrip() + "."
    _centered(draw, value, box, font, fill)
