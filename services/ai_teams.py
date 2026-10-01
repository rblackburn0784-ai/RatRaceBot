import random

from data.defaults import CREW_MEMBERS, PARTS
from models.domain import Team
from models.enums import CarArchetype, CrewSlot, PartSlot
from models.stats import DriverStats

AI_TEAM_NAMES = (
    "Rust Valley Saints",
    "Chrome Night Howlers",
    "Backroad Buzzards",
    "Primer Alley Kings",
    "Midnight Carb Club",
    "Switchback Vandals",
    "Moonshine Motor Union",
    "County Line Comets",
    "Blacktop Bruisers",
    "Neon Socket Syndicate",
    "Junkyard Jacks",
    "Salt Ghost Runners",
)

AI_DRIVER_NAMES = (
    "Benny Burnout",
    "Rita Redline",
    "Mack Axle",
    "Joanie Jet",
    "Vince Voltage",
    "Elsie Overdrive",
    "Hank Hammerdown",
    "Nora Nitro",
    "Cal Clutch",
    "Mabel Manifold",
    "Tommy Torque",
    "Sadie Sparks",
)

AI_CREW_NAMES = (
    "The Socket Set",
    "Grease Choir",
    "Alley Wrenches",
    "The Pit Saints",
    "Chrome Nurses",
    "The Oil Hands",
)

AI_CAR_NAMES = (
    "Tin Halo",
    "Red Worry",
    "Gravel Prayer",
    "Black Spark",
    "Mean Streak",
    "Loose Tooth",
    "Night Needle",
    "Bad Penny",
    "Static Wagon",
    "Rust Hymn",
)

AI_PERSONALITIES = (
    {
        "label": "Reckless",
        "stats": (5, 3, 6, 3, 4, 3),
        "parts": (5, 7),
        "prefer": (PartSlot.ENGINE, PartSlot.TRICK, PartSlot.FUEL),
    },
    {
        "label": "Defensive",
        "stats": (5, 5, 2, 4, 5, 3),
        "parts": (4, 6),
        "prefer": (PartSlot.BRAKES, PartSlot.SUSPENSION, PartSlot.BODY),
    },
    {
        "label": "Pit-Focused",
        "stats": (4, 4, 3, 6, 4, 3),
        "parts": (4, 6),
        "prefer": (PartSlot.FUEL, PartSlot.TRANSMISSION, PartSlot.BODY),
    },
    {
        "label": "Showboat",
        "stats": (5, 4, 5, 2, 3, 5),
        "parts": (5, 7),
        "prefer": (PartSlot.TRICK, PartSlot.ENGINE, PartSlot.TYRES),
    },
    {
        "label": "Reliable",
        "stats": (4, 4, 2, 5, 4, 5),
        "parts": (3, 5),
        "prefer": (PartSlot.BODY, PartSlot.BRAKES, PartSlot.SUSPENSION),
    },
    {
        "label": "Glass Cannon",
        "stats": (4, 3, 5, 2, 6, 4),
        "parts": (5, 7),
        "prefer": (PartSlot.ENGINE, PartSlot.FUEL, PartSlot.TRANSMISSION),
    },
)


def ai_teams(count: int, seed: str) -> list[Team]:
    rng = random.Random(seed)
    team_names = list(AI_TEAM_NAMES)
    driver_names = list(AI_DRIVER_NAMES)
    car_names = list(AI_CAR_NAMES)
    rng.shuffle(team_names)
    rng.shuffle(driver_names)
    rng.shuffle(car_names)

    teams = []
    for index in range(count):
        personality = rng.choice(AI_PERSONALITIES)
        archetype = rng.choice(list(CarArchetype))
        parts = _ai_parts(rng, personality)
        crew = _ai_crew(rng)
        teams.append(
            Team(
                id=-(index + 1),
                name=team_names[index % len(team_names)],
                driver_name=driver_names[index % len(driver_names)],
                pit_crew_name=f"{rng.choice(AI_CREW_NAMES)} [{personality['label']}]",
                car_name=car_names[index % len(car_names)],
                archetype=archetype,
                stats=_ai_driver_stats(rng, personality),
                parts=parts,
                crew=crew,
            )
        )
    return teams


def _ai_driver_stats(rng: random.Random, personality: dict) -> DriverStats:
    stats = list(personality["stats"])
    if rng.random() < 0.35:
        high = rng.randrange(len(stats))
        low = rng.randrange(len(stats))
        if high != low and stats[low] > 1 and stats[high] < 8:
            stats[high] += 1
            stats[low] -= 1
    return DriverStats(*stats)


def _ai_parts(rng: random.Random, personality: dict) -> list[str]:
    legal_by_slot = {
        slot: [key for key, part in PARTS.items() if part.slot == slot and "illegal_risk" not in part.risk_tags]
        for slot in PartSlot
    }
    min_parts, max_parts = personality["parts"]
    slot_count = rng.randint(min_parts, max_parts)
    preferred = list(personality["prefer"])
    other_slots = [slot for slot in PartSlot if slot not in preferred]
    rng.shuffle(preferred)
    rng.shuffle(other_slots)
    slots = (preferred + other_slots)[:slot_count]
    return [rng.choice(legal_by_slot[slot]) for slot in slots if legal_by_slot[slot]]


def _ai_crew(rng: random.Random) -> dict[str, str]:
    crew = {}
    for slot in CrewSlot:
        choices = [key for key, member in CREW_MEMBERS.items() if member.slot == slot]
        if choices and rng.random() < 0.8:
            crew[slot.value] = rng.choice(choices)
    return crew
