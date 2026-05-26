from models.domain import CarDefinition, Part, Track
from models.enums import CarArchetype, PartSlot
from models.stats import CarStats

CAR_DEFINITIONS: dict[str, CarDefinition] = {
    CarArchetype.COUPE_32.value: CarDefinition(
        CarArchetype.COUPE_32,
        "Classic chopped coupe. Balanced, stylish, and dangerous enough when pushed.",
        CarStats(speed=4, acceleration=3, handling=3, durability=3, braking=2, heat=2, intimidation=2, reliability=3, pit_friendliness=2),
    ),
    CarArchetype.ROADSTER_29.value: CarDefinition(
        CarArchetype.ROADSTER_29,
        "Lightweight open roadster. Fast off the line, twitchy in bad weather.",
        CarStats(speed=3, acceleration=5, handling=4, durability=1, braking=2, heat=2, intimidation=1, reliability=2, pit_friendliness=3),
    ),
    CarArchetype.TRUCK_50.value: CarDefinition(
        CarArchetype.TRUCK_50,
        "Heavy shop truck. Slow to launch but hard to bully and easy to patch up.",
        CarStats(speed=2, acceleration=2, handling=1, durability=6, braking=2, heat=1, intimidation=4, reliability=4, pit_friendliness=5),
    ),
    CarArchetype.LEADSLED.value: CarDefinition(
        CarArchetype.LEADSLED,
        "Low and mean leadsled. Stable and intimidating, but heavy through tight bends.",
        CarStats(speed=3, acceleration=2, handling=2, durability=5, braking=3, heat=1, intimidation=5, reliability=3, pit_friendliness=2),
    ),
    CarArchetype.GASSER.value: CarDefinition(
        CarArchetype.GASSER,
        "Nose-high strip brute. Explosive speed, questionable manners.",
        CarStats(speed=5, acceleration=5, handling=0, durability=2, braking=1, heat=4, intimidation=4, reliability=1, pit_friendliness=1),
    ),
    CarArchetype.LAKSTER.value: CarDefinition(
        CarArchetype.LAKSTER,
        "Salt-flat special. Blistering on straights, nervous in traffic.",
        CarStats(speed=6, acceleration=3, handling=1, durability=2, braking=1, heat=3, intimidation=2, reliability=2, pit_friendliness=1),
    ),
    CarArchetype.SEDAN.value: CarDefinition(
        CarArchetype.SEDAN,
        "Sleeper sedan. Not flashy, but dependable and sneaky quick when tuned.",
        CarStats(speed=3, acceleration=3, handling=3, durability=4, braking=3, heat=0, intimidation=1, reliability=5, pit_friendliness=4),
    ),
}

PARTS: dict[str, Part] = {
    "flathead_v8": Part("flathead_v8", "Warmed-Over Flathead V8", PartSlot.ENGINE, "Period-correct grunt with reliable pull.", CarStats(speed=1, acceleration=2, reliability=1, heat=1), 500),
    "nailhead_v8": Part("nailhead_v8", "Buick Nailhead Swap", PartSlot.ENGINE, "Big torque, big heat, big trouble if neglected.", CarStats(speed=2, acceleration=3, durability=-1, heat=3, reliability=-1), 800),
    "junkyard_blower": Part("junkyard_blower", "Junkyard Blower", PartSlot.ENGINE, "Mad acceleration, terrible manners.", CarStats(speed=2, acceleration=4, handling=-1, heat=4, reliability=-2, intimidation=2), 900, ("volatile",)),
    "triple_carbs": Part("triple_carbs", "Triple Carb Setup", PartSlot.FUEL, "Three carbs, three chances to go fast or catch fire.", CarStats(acceleration=2, heat=2, reliability=-1, intimidation=1), 450),
    "moonshine_mix": Part("moonshine_mix", "Moonshine Fuel Mix", PartSlot.FUEL, "Hot fuel that may anger the engine and the officials.", CarStats(speed=2, acceleration=2, heat=3, reliability=-2), 300, ("illegal_risk",)),
    "bias_ply": Part("bias_ply", "Skinny Bias-Ply Tyres", PartSlot.TYRES, "Authentic, light, poor grip when abused.", CarStats(speed=1, handling=-1), 250),
    "wide_whites": Part("wide_whites", "Wide Whitewalls", PartSlot.TYRES, "Stylish grip, heavier rolling mass.", CarStats(speed=-1, handling=2, braking=1), 350),
    "slicks": Part("slicks", "Rear Pie-Crust Slicks", PartSlot.TYRES, "Huge launch bite, lousy in rough corners.", CarStats(acceleration=3, handling=-1, braking=-1), 500),
    "cut_springs": Part("cut_springs", "Cut Springs", PartSlot.SUSPENSION, "Low and cool, but rough as a bar fight.", CarStats(handling=1, durability=-1, intimidation=1, reliability=-1), 200),
    "race_shocks": Part("race_shocks", "Rebuilt Race Shocks", PartSlot.SUSPENSION, "Better body control on ugly tracks.", CarStats(handling=2, durability=1, reliability=1), 500),
    "juice_brakes": Part("juice_brakes", "Hydraulic Juice Brakes", PartSlot.BRAKES, "Stops before the wall, mostly.", CarStats(braking=3, reliability=1), 400),
    "drum_brake_fade": Part("drum_brake_fade", "Lightened Drums", PartSlot.BRAKES, "Quicker car, weaker braking late on.", CarStats(speed=1, braking=-2, heat=1), 250),
    "chopped_roof": Part("chopped_roof", "Chopped Roof", PartSlot.BODY, "Lower profile, lower visibility.", CarStats(speed=1, handling=1, reliability=0, intimidation=1), 600),
    "channeled_body": Part("channeled_body", "Channelled Body", PartSlot.BODY, "Scrapes the deck; handles clean roads, hates rough ones.", CarStats(speed=1, handling=2, durability=-1, pit_friendliness=-1), 650),
    "bare_metal": Part("bare_metal", "Bare Metal & Primer", PartSlot.BODY, "Less weight, more menace, less protection.", CarStats(speed=1, durability=-1, intimidation=2, pit_friendliness=1), 150),
    "quick_change": Part("quick_change", "Quick-Change Rear End", PartSlot.TRANSMISSION, "Lets the rod suit the track better.", CarStats(acceleration=1, speed=1, reliability=1, pit_friendliness=1), 700),
    "long_throw_shifter": Part("long_throw_shifter", "Tall Long-Throw Shifter", PartSlot.TRANSMISSION, "Looks the part; costs time in traffic.", CarStats(acceleration=-1, intimidation=1), 250),
    "reinforced_frame": Part("reinforced_frame", "Reinforced Scrap Frame", PartSlot.BODY, "Heavy, strong, survives punishment.", CarStats(speed=-1, acceleration=-1, durability=4, pit_friendliness=1), 500),
    "dirty_bumper": Part("dirty_bumper", "Rusty Battering Bumper", PartSlot.TRICK, "Makes contact scarier, and officials suspicious.", CarStats(intimidation=3, durability=1, speed=-1, handling=-1), 350, ("illegal_risk",)),
}

TRACKS: dict[str, Track] = {
    "neon_mile": Track(
        "neon_mile", "The Neon Mile", "Downtown street circuit under diner signs and police sirens.", 10,
        corner_difficulty=4, straight_bias=2, surface_roughness=3, pit_difficulty=3, hazard_rate=13,
        modifiers=CarStats(speed=-1, acceleration=1, handling=2, braking=1, durability=-1, heat=1, intimidation=1, reliability=-1),
        hazard_names=("loose manhole cover", "oil patch outside the diner", "crowd spill near the kerb"),
    ),
    "county_line": Track(
        "county_line", "County Line Drag Loop", "Long straights, dusty returns, and too much speed for good sense.", 10,
        corner_difficulty=2, straight_bias=5, surface_roughness=2, pit_difficulty=2, hazard_rate=10,
        modifiers=CarStats(speed=3, acceleration=2, handling=-2, braking=-1, heat=2, reliability=-1, pit_friendliness=1),
        hazard_names=("dust cloud", "stray farm truck", "crosswind over the fields"),
    ),
    "junkyard_bowl": Track(
        "junkyard_bowl", "Junkyard Bowl", "A brutal oval built around scrap piles and bad decisions.", 10,
        corner_difficulty=5, straight_bias=1, surface_roughness=5, pit_difficulty=4, hazard_rate=19,
        modifiers=CarStats(speed=-3, acceleration=-1, handling=-1, durability=3, braking=1, intimidation=2, reliability=-2, pit_friendliness=2),
        hazard_names=("loose hubcap", "scrap metal shard", "falling stack of tyres"),
    ),
    "salt_ghost": Track(
        "salt_ghost", "Salt Ghost Flats", "Wide open salt-flat speed with glare, heat, and almost no forgiveness.", 10,
        corner_difficulty=1, straight_bias=6, surface_roughness=1, pit_difficulty=2, hazard_rate=9,
        modifiers=CarStats(speed=4, acceleration=1, handling=-2, braking=-2, durability=-1, heat=3, reliability=-2),
        hazard_names=("blinding salt glare", "engine-cooking heat shimmer", "sudden sidewind"),
    ),
    "switchback_66": Track(
        "switchback_66", "Switchback 66", "Mountain road, diner stop, hairpins, cliffs, and prayer.", 10,
        corner_difficulty=6, straight_bias=1, surface_roughness=4, pit_difficulty=5, hazard_rate=17,
        modifiers=CarStats(speed=-3, acceleration=-1, handling=3, braking=3, durability=-1, heat=1, reliability=-1, pit_friendliness=-1),
        hazard_names=("falling gravel", "blind hairpin", "smoke across the road"),
    ),
    "fairground_figure8": Track(
        "fairground_figure8", "Fairground Figure-8", "A crossing-track carnival trap lit by bulbs, banners, and bad timing.", 10,
        corner_difficulty=5, straight_bias=2, surface_roughness=3, pit_difficulty=4, hazard_rate=20,
        modifiers=CarStats(speed=-1, acceleration=2, handling=2, braking=-1, durability=-2, intimidation=3, reliability=-1, pit_friendliness=-1),
        hazard_names=("cross-traffic near miss", "fallen bunting", "spilled soda slick"),
    ),
    "riverfront_sprint": Track(
        "riverfront_sprint", "Riverfront Sprint", "Fast riverside avenues with damp cobbles, fog, and nowhere graceful to stop.", 10,
        corner_difficulty=3, straight_bias=4, surface_roughness=2, pit_difficulty=3, hazard_rate=12,
        modifiers=CarStats(speed=2, acceleration=1, handling=-2, braking=-2, durability=1, heat=-1, reliability=1, pit_friendliness=1),
        hazard_names=("wet cobbles", "fog bank off the river", "loose dock rope"),
    ),
    "foundry_run": Track(
        "foundry_run", "Foundry Run", "Industrial lanes around furnace heat, rail spurs, and metal dust.", 10,
        corner_difficulty=4, straight_bias=3, surface_roughness=4, pit_difficulty=4, hazard_rate=16,
        modifiers=CarStats(speed=1, acceleration=-1, handling=-1, braking=1, durability=2, heat=3, intimidation=2, reliability=-3, pit_friendliness=-1),
        hazard_names=("rail crossing kick", "cinder spray", "steam burst from the foundry wall"),
    ),
    "boardwalk_dash": Track(
        "boardwalk_dash", "Boardwalk Dash", "A seaside blast over flexing planks, salt air, and too many spectators.", 10,
        corner_difficulty=3, straight_bias=4, surface_roughness=5, pit_difficulty=3, hazard_rate=15,
        modifiers=CarStats(speed=2, acceleration=2, handling=-1, braking=-1, durability=-3, heat=-1, intimidation=1, reliability=-1),
        hazard_names=("splintered board", "sand drift", "startled crowd surge"),
    ),
    "midnight_oval": Track(
        "midnight_oval", "Midnight Moonshine Oval", "A blacktop oval behind the warehouses, built for nerve, noise, and contact.", 10,
        corner_difficulty=4, straight_bias=3, surface_roughness=2, pit_difficulty=2, hazard_rate=14,
        modifiers=CarStats(speed=1, acceleration=2, handling=1, braking=-1, durability=1, heat=2, intimidation=3, reliability=-1, pit_friendliness=2),
        hazard_names=("oil drum marker", "hidden pothole", "officials' flashlight sweep"),
    ),
}

POINTS_BY_POSITION = {position: 11 - position for position in range(1, 11)}
