from __future__ import annotations

from dataclasses import dataclass
import math

from data.defaults import PARTS, TRACKS, WEATHER_CONDITIONS
from models.domain import CrewMember, Part, Team, Track, WeatherCondition
from models.enums import CrewSlot
from models.stats import CarStats, DriverStats

BALANCE_VERSION = "0.4.3"


@dataclass(frozen=True, slots=True)
class CrewEffects:
    strategy: float = 0.0
    repair: float = 0.0
    tyre_care: float = 0.0
    heat_control: float = 0.0
    spotting: float = 0.0
    attack_support: float = 0.0
    pit_bonus: float = 0.0

    def __add__(self, other: "CrewEffects") -> "CrewEffects":
        return CrewEffects(
            strategy=self.strategy + other.strategy,
            repair=self.repair + other.repair,
            tyre_care=self.tyre_care + other.tyre_care,
            heat_control=self.heat_control + other.heat_control,
            spotting=self.spotting + other.spotting,
            attack_support=self.attack_support + other.attack_support,
            pit_bonus=self.pit_bonus + other.pit_bonus,
        )


# Explicit specialisation hooks. These are deliberately modest: they are intended
# to change which build is best for a venue, not to create another must-have stack.
TRACK_SPECIALISATIONS: dict[str, dict[str, CarStats]] = {
    "salt_flat_skins": {
        "salt_ghost": CarStats(speed=2, handling=1, braking=1),
        "county_line": CarStats(speed=1),
    },
    "dirt_track_treads": {
        "junkyard_bowl": CarStats(durability=1),
        "foundry_run": CarStats(handling=1),
        "boardwalk_dash": CarStats(durability=1),
    },
    "rain_grooved_whites": {
        "rain": CarStats(handling=2, braking=2),
        "oil_mist": CarStats(handling=1, braking=2),
    },
    "soft_dirt_setup": {
        "junkyard_bowl": CarStats(handling=2, durability=1),
        "foundry_run": CarStats(handling=1, durability=1),
        "boardwalk_dash": CarStats(durability=1),
    },
    "leaf_spring_pack": {
        "junkyard_bowl": CarStats(handling=2, durability=1),
        "foundry_run": CarStats(handling=1, durability=1),
        "boardwalk_dash": CarStats(handling=1, durability=1),
    },
    "truck_torque_motor": {
        "junkyard_bowl": CarStats(speed=1, handling=2, durability=1),
        "foundry_run": CarStats(speed=1, handling=1),
        "boardwalk_dash": CarStats(acceleration=1),
    },
    "stiff_street_setup": {
        "neon_mile": CarStats(speed=1),
        "riverfront_sprint": CarStats(handling=1),
        "midnight_oval": CarStats(speed=1),
        "junkyard_bowl": CarStats(durability=-1, reliability=-1),
        "switchback_66": CarStats(durability=-1),
    },
    "tall_rear_gears": {
        "county_line": CarStats(speed=2),
        "salt_ghost": CarStats(speed=2),
        "riverfront_sprint": CarStats(speed=1),
        "switchback_66": CarStats(acceleration=-1),
    },
    "short_rear_gears": {
        "switchback_66": CarStats(acceleration=2, handling=1),
        "fairground_figure8": CarStats(acceleration=1, handling=1),
        "county_line": CarStats(speed=-1),
        "salt_ghost": CarStats(speed=-1),
    },
    "quick_change": {
        "county_line": CarStats(speed=1),
        "switchback_66": CarStats(handling=1),
    },
    "cooling_ducts": {
        "heatwave": CarStats(heat=-2, reliability=1),
        "foundry_run": CarStats(heat=-1),
    },
    "cool_can": {
        "heatwave": CarStats(heat=-2, reliability=1),
        "foundry_run": CarStats(heat=-1),
    },
    "steel_belly_pan": {
        "junkyard_bowl": CarStats(durability=2),
        "foundry_run": CarStats(durability=1),
        "boardwalk_dash": CarStats(durability=1),
    },
    "reinforced_frame": {
        "junkyard_bowl": CarStats(durability=2),
        "foundry_run": CarStats(durability=1),
        "boardwalk_dash": CarStats(durability=1),
    },
    "leaf_spring_pack": {
        "junkyard_bowl": CarStats(durability=2),
        "boardwalk_dash": CarStats(durability=1),
    },
    "handbrake_turn_bar": {
        "switchback_66": CarStats(handling=2),
        "fairground_figure8": CarStats(handling=1),
    },
    "front_disc_conversion": {
        "switchback_66": CarStats(braking=2),
        "neon_mile": CarStats(braking=1),
    },
}


def soft_stat(value: float, pivot: float = 5.0, excess_scale: float = 0.52) -> float:
    """Diminishing-return stat transform with linear negatives and no hard cap."""
    if value <= pivot:
        return value
    return pivot + (value - pivot) * excess_scale


def driver_foundation(stats: DriverStats) -> float:
    # Concavity keeps 24-point min/max allocations close to balanced allocations.
    values = (stats.nerve, stats.handling, stats.aggression, stats.mechanics, stats.reflexes, stats.showmanship)
    return sum(math.sqrt(max(1, value)) for value in values)


def centered_driver(value: int) -> float:
    # Small role-specific modifier around the neutral value of 4.
    return (value - 4) * 0.33


def part_strain(part: Part) -> int:
    m = part.modifiers
    performance = (
        max(0, m.speed) * 1.25
        + max(0, m.acceleration) * 1.15
        + max(0, m.handling) * 1.05
        + max(0, m.braking) * 0.85
        + max(0, m.intimidation) * 0.25
        + max(0, m.heat) * 0.65
    )
    support = (
        max(0, m.reliability) * 0.65
        + max(0, m.durability) * 0.40
        + max(0, m.pit_friendliness) * 0.35
        + max(0, -m.heat) * 0.50
    )
    base = max(0.0, performance - support)
    strain = int(math.ceil(base / 2.4))
    if "illegal_risk" in part.risk_tags:
        strain += 1
    return min(6, strain)


def build_strain(team: Team) -> int:
    equipped = []
    seen_slots = set()
    for key in team.parts:
        part = PARTS.get(key)
        if part and part.slot not in seen_slots:
            seen_slots.add(part.slot)
            equipped.append(part)
    strain = sum(part_strain(part) for part in equipped)
    illegal = sum(1 for part in equipped if "illegal_risk" in part.risk_tags)
    # Multiple illegal systems interact badly even though each still carries the
    # advertised +6% scrutineering risk separately.
    strain += max(0, illegal - 1) * illegal // 2
    return strain


def strain_label(strain: int) -> str:
    if strain <= 3:
        return "Low"
    if strain <= 7:
        return "Tuned"
    if strain <= 11:
        return "Stressed"
    return "Knife-Edge"


def effective_strain(team: Team, mechanic_support: float = 0.0) -> float:
    driver_relief = max(0.0, (team.stats.mechanics - 4) * 0.45)
    return max(0.0, build_strain(team) - driver_relief - max(0.0, mechanic_support) * 0.45)


def track_part_adjustment(team: Team, track: Track, weather: WeatherCondition) -> CarStats:
    total = CarStats()
    seen_slots = set()
    for key in team.parts:
        part = PARTS.get(key)
        if not part or part.slot in seen_slots:
            continue
        seen_slots.add(part.slot)
        mapping = TRACK_SPECIALISATIONS.get(key, {})
        if track.key in mapping:
            total = total + mapping[track.key]
        if weather.key in mapping:
            total = total + mapping[weather.key]

    return total


def _clamp_role(value: float) -> float:
    return max(-3.0, min(3.0, value))


def crew_effect_for_member(member: CrewMember) -> CrewEffects:
    m = member.modifiers
    if member.slot == CrewSlot.CREW_CHIEF:
        return CrewEffects(
            strategy=_clamp_role((m.speed + m.acceleration + m.handling + m.braking + m.reliability - max(0, m.heat)) / 3.0),
            pit_bonus=_clamp_role(m.pit_friendliness / 2.0),
            attack_support=_clamp_role(m.intimidation / 2.0),
        )
    if member.slot == CrewSlot.LEAD_MECHANIC:
        return CrewEffects(
            repair=_clamp_role((m.durability + m.reliability + m.pit_friendliness - max(0, m.heat)) / 2.4),
            heat_control=_clamp_role((m.reliability - m.heat) / 2.5),
            pit_bonus=_clamp_role(m.pit_friendliness / 2.0),
        )
    if member.slot == CrewSlot.TYRE_CHANGER:
        return CrewEffects(
            tyre_care=_clamp_role((m.handling + m.braking + m.durability + m.reliability - max(0, m.acceleration - 1)) / 2.5),
            pit_bonus=_clamp_role(m.pit_friendliness / 2.0),
            attack_support=_clamp_role(max(0, m.acceleration) / 3.0),
        )
    if member.slot == CrewSlot.FUEL_RUNNER:
        return CrewEffects(
            heat_control=_clamp_role((m.reliability - m.heat) / 2.2),
            strategy=_clamp_role((m.speed + m.acceleration - max(0, m.heat)) / 3.0),
            pit_bonus=_clamp_role(m.pit_friendliness / 2.0),
        )
    if member.slot == CrewSlot.SPOTTER:
        return CrewEffects(
            spotting=_clamp_role((m.handling + m.braking + m.reliability + max(0, m.intimidation) * 0.5) / 2.4),
            attack_support=_clamp_role((m.speed + m.acceleration + m.intimidation - max(0, -m.handling)) / 2.5),
        )
    return CrewEffects()


def crew_effects(team: Team) -> CrewEffects:
    from data.defaults import CREW_MEMBERS

    total = CrewEffects()
    for slot in CrewSlot:
        key = team.crew.get(slot.value)
        member = CREW_MEMBERS.get(key)
        if member:
            total = total + crew_effect_for_member(member)
    return total


def crew_effect_summary(team: Team) -> str:
    e = crew_effects(team)
    pairs = [
        ("Strategy", e.strategy),
        ("Repair", e.repair),
        ("Tyre care", e.tyre_care),
        ("Heat control", e.heat_control),
        ("Spotting", e.spotting),
        ("Attack support", e.attack_support),
        ("Pit bonus", e.pit_bonus),
    ]
    shown = [f"{name} {value:+.1f}" for name, value in pairs if abs(value) >= 0.05]
    return " | ".join(shown) if shown else "No specialist crew effects"

@dataclass(frozen=True, slots=True)
class TraitEffects:
    pace: float = 0.0
    hazard_save: float = 0.0
    tyre_care: float = 0.0
    pit_bonus: float = 0.0
    attack: float = 0.0
    illegal_risk: float = 0.0
    late_race: float = 0.0

    def __add__(self, other: "TraitEffects") -> "TraitEffects":
        return TraitEffects(
            pace=self.pace + other.pace,
            hazard_save=self.hazard_save + other.hazard_save,
            tyre_care=self.tyre_care + other.tyre_care,
            pit_bonus=self.pit_bonus + other.pit_bonus,
            attack=self.attack + other.attack,
            illegal_risk=self.illegal_risk + other.illegal_risk,
            late_race=self.late_race + other.late_race,
        )


def trait_effects(team: Team, track: Track, weather: WeatherCondition) -> TraitEffects:
    # Lazy import avoids engagement.py <-> balance.py import cycles.
    from services.engagement import team_traits

    total = TraitEffects()
    for trait in team_traits(team):
        key = trait.key
        if key == "late_braker":
            total = total + TraitEffects(pace=0.35 + track.corner_difficulty * 0.07, hazard_save=0.25, tyre_care=-0.20)
        elif key == "smooth_operator":
            total = total + TraitEffects(pace=0.25, hazard_save=0.45, tyre_care=0.65, attack=-0.20)
        elif key == "hothead":
            total = total + TraitEffects(pace=0.20, attack=0.85, illegal_risk=1.8, tyre_care=-0.35)
        elif key == "rain_specialist":
            if weather.key in {"rain", "oil_mist"}:
                total = total + TraitEffects(pace=1.10, hazard_save=1.00)
            else:
                total = total + TraitEffects(pace=-0.15)
        elif key == "clutch_nerves":
            total = total + TraitEffects(pace=0.15, late_race=1.10)
        elif key == "tyre_shredder":
            total = total + TraitEffects(pace=0.65, attack=0.35, tyre_care=-0.95)
        elif key == "pit_whisperer":
            total = total + TraitEffects(pace=-0.15, pit_bonus=1.60, tyre_care=0.15)
        elif key == "showboat":
            total = total + TraitEffects(pace=0.25, attack=0.45, illegal_risk=0.8, late_race=0.35)
    return total
