from __future__ import annotations

from dataclasses import dataclass

XP_BY_LEVEL = 100
MAX_LEVEL = 10


@dataclass(frozen=True, slots=True)
class IdentityOption:
    key: str
    name: str
    required_level: int


LIVERIES = (
    IdentityOption('bare_primer', 'Bare Primer', 1),
    IdentityOption('cream_scallops', 'Cream Scallops', 2),
    IdentityOption('flame_job', 'Hand-Painted Flames', 3),
    IdentityOption('checkerboard', 'Blacktop Checkerboard', 4),
    IdentityOption('moonlit_metalflake', 'Moonlit Metalflake', 6),
    IdentityOption('legend_pinstripe', 'Legend Pinstripe', 10),
)

EMBLEMS = (
    IdentityOption('rat_skull', 'Rat Skull', 1),
    IdentityOption('crossed_wrenches', 'Crossed Wrenches', 2),
    IdentityOption('lucky_13', 'Lucky 13', 3),
    IdentityOption('burning_whitewall', 'Burning Whitewall', 5),
    IdentityOption('blacktop_crown', 'Blacktop Crown', 8),
)

GARAGE_DECOR = (
    IdentityOption('oil_stained_bench', 'Oil-Stained Workbench', 1),
    IdentityOption('neon_clock', 'Neon Garage Clock', 3),
    IdentityOption('trophy_shelf', 'Handmade Trophy Shelf', 5),
    IdentityOption('newspaper_wall', 'Blacktop Gazette Wall', 7),
    IdentityOption('champions_banner', 'Champion Banner Rail', 10),
)


def level_for_xp(xp: int) -> int:
    return max(1, min(MAX_LEVEL, int(xp) // XP_BY_LEVEL + 1))


def setup_slot_count(level: int) -> int:
    if level >= 5:
        return 5
    if level >= 3:
        return 4
    return 3


def unlocked_setup_names(level: int) -> tuple[str, ...]:
    return ('Street', 'Dirt', 'Wet', 'High-Speed', 'Custom')[: setup_slot_count(level)]


def unlocked_options(options: tuple[IdentityOption, ...], level: int) -> list[IdentityOption]:
    return [option for option in options if level >= option.required_level]


def unlock_lines(level: int) -> list[str]:
    lines = [f'Garage presets: **{setup_slot_count(level)}/5**']
    if level >= 2:
        lines.append('Identity: extra livery/emblem choices')
    if level >= 3:
        lines.append('Custom team intro phrase + High-Speed setup')
    if level >= 4:
        lines.append('Specialist crew shortlist recognition')
    if level >= 5:
        lines.append('Custom setup slot + full sponsor pool + Gazette spotlight')
    if level >= 7:
        lines.append('Veteran identity cosmetics')
    if level >= 10:
        lines.append('Legend identity cosmetics')
    return lines


def next_unlock(level: int) -> str:
    milestones = {
        2: 'extra livery/emblem choices and Graveyard Wrench interest',
        3: 'High-Speed preset, custom intro phrase and Whitewall Radio interest',
        4: 'specialist crew recognition and Lucky 13 interest',
        5: 'Custom preset, full sponsor pool and Gazette spotlight',
        7: 'veteran identity cosmetics',
        10: 'legend identity cosmetics',
    }
    for required, text in milestones.items():
        if level < required:
            return f'Level {required}: {text}'
    return 'All current progression unlocks earned.'

SPECIALIST_CREW_KEYS = {
    'chief_mae_clipboard',
    'mechanic_grace_grease',
    'tyre_slick_mickey',
    'fuel_pops_stromberg',
    'spotter_sue_sideeye',
}


def crew_required_level(crew_key: str) -> int:
    return 4 if crew_key in SPECIALIST_CREW_KEYS else 1


def crew_unlocked(crew_key: str, level: int) -> bool:
    return level >= crew_required_level(crew_key)
