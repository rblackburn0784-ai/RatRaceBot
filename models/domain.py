from dataclasses import dataclass, field
from models.enums import CarArchetype, PartSlot, EventType
from models.stats import DriverStats, CarStats

@dataclass(slots=True)
class Part:
    key: str
    name: str
    slot: PartSlot
    description: str
    modifiers: CarStats
    cost: int = 0
    risk_tags: tuple[str, ...] = ()

@dataclass(slots=True)
class CarDefinition:
    archetype: CarArchetype
    description: str
    base_stats: CarStats

@dataclass(slots=True)
class Track:
    key: str
    name: str
    description: str
    laps: int
    corner_difficulty: int
    straight_bias: int
    surface_roughness: int
    pit_difficulty: int
    hazard_rate: int
    modifiers: CarStats
    hazard_names: tuple[str, ...]

@dataclass(slots=True)
class Team:
    id: int | None
    name: str
    driver_name: str
    pit_crew_name: str
    car_name: str
    archetype: CarArchetype
    stats: DriverStats
    parts: list[str] = field(default_factory=list)

@dataclass(slots=True)
class RaceEvent:
    event_type: EventType
    lap: int
    message: str
    media_key: str | None = None
    audio_key: str | None = None

@dataclass(slots=True)
class RaceResult:
    team_id: int
    team_name: str
    driver_name: str
    position: int
    laps_completed: int
    total_time: float
    points: int
    warnings: int
    dnf: bool
    disqualified: bool
    damage: int
    tyre_wear: int
    overtakes: int = 0
    crashes: int = 0
    illegal_moves: int = 0
    last_minute_wins: int = 0
    pit_stops: int = 0
    near_misses: int = 0

@dataclass(slots=True)
class RaceState:
    team: Team
    position: int
    lap: int = 0
    total_time: float = 0.0
    damage: int = 0
    tyre_wear: int = 0
    warnings: int = 0
    disqualified: bool = False
    dnf: bool = False
    pit_stops: int = 0
    momentum: int = 0
    car_colour: str = ""
    overtakes: int = 0
    crashes: int = 0
    illegal_moves: int = 0
    last_minute_wins: int = 0
    near_misses: int = 0
