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
        archetype = rng.choice(list(CarArchetype))
        parts = _ai_parts(rng)
        crew = _ai_crew(rng)
        teams.append(
            Team(
                id=-(index + 1),
                name=team_names[index % len(team_names)],
                driver_name=driver_names[index % len(driver_names)],
                pit_crew_name=rng.choice(AI_CREW_NAMES),
                car_name=car_names[index % len(car_names)],
                archetype=archetype,
                stats=_ai_driver_stats(rng),
                parts=parts,
                crew=crew,
            )
        )
    return teams


def _ai_driver_stats(rng: random.Random) -> DriverStats:
    stats = [3, 4, 4, 4, 4, 5]
    rng.shuffle(stats)
    return DriverStats(*stats)


def _ai_parts(rng: random.Random) -> list[str]:
    legal_by_slot = {
        slot: [key for key, part in PARTS.items() if part.slot == slot and "illegal_risk" not in part.risk_tags]
        for slot in PartSlot
    }
    slot_count = rng.randint(3, 6)
    slots = rng.sample(list(PartSlot), slot_count)
    return [rng.choice(legal_by_slot[slot]) for slot in slots if legal_by_slot[slot]]


def _ai_crew(rng: random.Random) -> dict[str, str]:
    crew = {}
    for slot in CrewSlot:
        choices = [key for key, member in CREW_MEMBERS.items() if member.slot == slot]
        if choices and rng.random() < 0.8:
            crew[slot.value] = rng.choice(choices)
    return crew
