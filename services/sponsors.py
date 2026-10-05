from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SponsorDefinition:
    key: str
    name: str
    min_level: int
    benefit_text: str
    drawback_text: str
    opening_pace_bonus: float = 0.0
    heat_pressure: float = 0.0
    illegal_scrutiny_bonus: int = 0
    pit_repair_bonus: int = 0
    pit_time_variance: float = 0.0
    momentum_chance_bonus: float = 0.0
    tyre_wear_pressure: float = 0.0
    hazard_save_bonus: float = 0.0
    pace_penalty: float = 0.0
    xp_multiplier: float = 1.0


SPONSORS: dict[str, SponsorDefinition] = {
    'county_line_diner': SponsorDefinition(
        key='county_line_diner',
        name='County Line Diner',
        min_level=1,
        benefit_text='+15% race XP from local-fan promotion.',
        drawback_text='Sponsor appearances cost a tiny amount of race focus.',
        pace_penalty=0.12,
        xp_multiplier=1.15,
    ),
    'graveyard_wrench': SponsorDefinition(
        key='graveyard_wrench',
        name='Graveyard Wrench Supply',
        min_level=2,
        benefit_text='Major pit repairs restore a little more damage.',
        drawback_text='Heavy workshop gear makes pit-stop timing less predictable.',
        pit_repair_bonus=4,
        pit_time_variance=2.2,
    ),
    'whitewall_radio': SponsorDefinition(
        key='whitewall_radio',
        name='Whitewall Radio Hour',
        min_level=3,
        benefit_text='Showmanship has a better chance to build race momentum.',
        drawback_text='Crowd-pleasing driving works the tyres harder.',
        momentum_chance_bonus=7.0,
        tyre_wear_pressure=0.20,
    ),
    'lucky_13_speed': SponsorDefinition(
        key='lucky_13_speed',
        name='Lucky 13 Speed Shop',
        min_level=4,
        benefit_text='Extra trackside support helps the driver save marginal hazards.',
        drawback_text='Sponsor obligations cost a sliver of outright pace; illegal hardware also gets closer scrutiny.',
        hazard_save_bonus=1.10,
        pace_penalty=0.06,
        illegal_scrutiny_bonus=2,
    ),
    'moonshine_fuel': SponsorDefinition(
        key='moonshine_fuel',
        name='Moonshine Fuel Co.',
        min_level=5,
        benefit_text='Sharper acceleration effect during the opening two laps.',
        drawback_text='The hotter fuel package increases heat pressure and illegal-part scrutiny.',
        opening_pace_bonus=0.85,
        heat_pressure=0.50,
        illegal_scrutiny_bonus=2,
    ),
}


def sponsor_by_key(key: str | None) -> SponsorDefinition | None:
    return SPONSORS.get(str(key or ''))


def sponsors_for_level(level: int) -> list[SponsorDefinition]:
    return [s for s in SPONSORS.values() if level >= s.min_level]


def sponsor_key_by_name(name: str) -> str | None:
    for key, sponsor in SPONSORS.items():
        if sponsor.name == name:
            return key
    return None
