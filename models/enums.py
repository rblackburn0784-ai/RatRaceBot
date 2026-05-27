from enum import Enum

class CarArchetype(str, Enum):
    COUPE_32 = "1932 Chopped Coupe"
    ROADSTER_29 = "1929 Barebones Roadster"
    TRUCK_50 = "1950 Shop Truck"
    LEADSLED = "Low-Slung Leadsled"
    GASSER = "Moonshine Gasser"
    LAKSTER = "Salt-Flat Lakester"
    SEDAN = "Four-Door Sleeper Sedan"

class PartSlot(str, Enum):
    ENGINE = "engine"
    TYRES = "tyres"
    SUSPENSION = "suspension"
    BRAKES = "brakes"
    BODY = "body"
    TRANSMISSION = "transmission"
    FUEL = "fuel"
    TRICK = "trick"

class CrewSlot(str, Enum):
    CREW_CHIEF = "crew_chief"
    LEAD_MECHANIC = "lead_mechanic"
    TYRE_CHANGER = "tyre_changer"
    FUEL_RUNNER = "fuel_runner"
    SPOTTER = "spotter"

class EventType(str, Enum):
    START = "start"
    LAP = "lap"
    OVERTAKE = "overtake"
    DAMAGE_MINOR = "damage_minor"
    DAMAGE_MAJOR = "damage_major"
    DESTROYED = "destroyed"
    PIT_STOP = "pit_stop"
    ILLEGAL_MOVE = "illegal_move"
    WARNING = "warning"
    DISQUALIFIED = "disqualified"
    LAST_MINUTE_WIN = "last_minute_win"
    FINISH = "finish_line"
    PODIUM = "podium"
