from models.domain import CarDefinition, CrewMember, Part, Track
from models.enums import CarArchetype, CrewSlot, PartSlot
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
    "junkyard_blower": Part("junkyard_blower", "Junkyard Blower", PartSlot.ENGINE, "Mad acceleration, terrible manners.", CarStats(speed=2, acceleration=4, handling=-1, heat=4, reliability=-2, intimidation=2), 900),
    "straight_six": Part("straight_six", "Balanced Straight-Six", PartSlot.ENGINE, "Smooth, light, and easy on tyres, but short on top-end fury.", CarStats(speed=-1, acceleration=1, handling=1, reliability=2, heat=-1), 450),
    "cadillac_331": Part("cadillac_331", "Cadillac 331 Swap", PartSlot.ENGINE, "Heavy luxury muscle with a fierce pull down the straights.", CarStats(speed=3, acceleration=2, handling=-1, braking=-1, heat=2), 850),
    "blueprinted_flathead": Part("blueprinted_flathead", "Blueprinted Flathead", PartSlot.ENGINE, "Careful machine work gives clean power without much drama.", CarStats(speed=2, acceleration=1, reliability=2, heat=1, pit_friendliness=-1), 950),
    "truck_torque_motor": Part("truck_torque_motor", "Stump-Puller Truck Motor", PartSlot.ENGINE, "Low-end shove for rough tracks, less happy at screaming speed.", CarStats(acceleration=3, speed=-1, durability=2, heat=1, handling=-1), 650),
    "illegal_nitro_blower": Part("illegal_nitro_blower", "ILLEGAL Nitro Blower", PartSlot.ENGINE, "Huge illegal shove. Adds disqualification scrutiny.", CarStats(speed=4, acceleration=5, handling=-2, durability=-2, heat=5, reliability=-3, intimidation=3), 1200, ("illegal_risk",)),

    "bias_ply": Part("bias_ply", "Skinny Bias-Ply Tyres", PartSlot.TYRES, "Authentic, light, poor grip when abused.", CarStats(speed=1, handling=-1), 250),
    "wide_whites": Part("wide_whites", "Wide Whitewalls", PartSlot.TYRES, "Stylish grip, heavier rolling mass.", CarStats(speed=-1, handling=2, braking=1), 350),
    "slicks": Part("slicks", "Rear Pie-Crust Slicks", PartSlot.TYRES, "Huge launch bite, lousy in rough corners.", CarStats(acceleration=3, handling=-1, braking=-1), 500),
    "dirt_track_treads": Part("dirt_track_treads", "Dirt Track Treads", PartSlot.TYRES, "Bites hard on rough surfaces, drags on fast clean straights.", CarStats(handling=2, durability=1, speed=-1, heat=1), 420),
    "steel_belted_blackwalls": Part("steel_belted_blackwalls", "Steel-Belted Blackwalls", PartSlot.TYRES, "Stable and tough, not flashy off the line.", CarStats(durability=2, braking=1, acceleration=-1, pit_friendliness=1), 460),
    "salt_flat_skins": Part("salt_flat_skins", "Salt-Flat Skins", PartSlot.TYRES, "Low rolling resistance for speed runs, poor in corners.", CarStats(speed=3, handling=-2, braking=-1, heat=1), 520),
    "rain_grooved_whites": Part("rain_grooved_whites", "Rain-Grooved Whites", PartSlot.TYRES, "Safer in slick conditions but heavier everywhere else.", CarStats(handling=1, braking=2, speed=-1, acceleration=-1, reliability=1), 480),
    "illegal_chemical_slicks": Part("illegal_chemical_slicks", "ILLEGAL Chemical Slicks", PartSlot.TYRES, "Sticky treated tyres. Adds disqualification scrutiny.", CarStats(acceleration=4, handling=2, braking=-2, heat=2, durability=-2, reliability=-2), 900, ("illegal_risk",)),

    "cut_springs": Part("cut_springs", "Cut Springs", PartSlot.SUSPENSION, "Low and cool, but rough as a bad handshake.", CarStats(handling=1, durability=-1, intimidation=1, reliability=-1), 200),
    "race_shocks": Part("race_shocks", "Rebuilt Race Shocks", PartSlot.SUSPENSION, "Better body control on ugly tracks.", CarStats(handling=2, durability=1, reliability=1), 500),
    "leaf_spring_pack": Part("leaf_spring_pack", "Heavy Leaf Spring Pack", PartSlot.SUSPENSION, "Tough under hits, slow to change direction.", CarStats(durability=3, handling=-1, pit_friendliness=1, speed=-1), 400),
    "dropped_axle": Part("dropped_axle", "Dropped Front Axle", PartSlot.SUSPENSION, "Lower stance and sharper turn-in, less room for punishment.", CarStats(handling=2, speed=1, durability=-2), 550),
    "coilover_conversion": Part("coilover_conversion", "Back-Alley Coilovers", PartSlot.SUSPENSION, "Adjustable grip with fiddly pit work.", CarStats(handling=3, braking=1, reliability=-1, pit_friendliness=-1), 750),
    "soft_dirt_setup": Part("soft_dirt_setup", "Soft Dirt Setup", PartSlot.SUSPENSION, "Soaks bumps and junk, wallows on clean tarmac.", CarStats(durability=2, reliability=1, handling=-1, speed=-1), 420),
    "stiff_street_setup": Part("stiff_street_setup", "Stiff Street Setup", PartSlot.SUSPENSION, "Fast response on smooth streets, harsh over debris.", CarStats(handling=2, speed=1, durability=-1, reliability=-1), 500),
    "illegal_hidden_hydraulics": Part("illegal_hidden_hydraulics", "ILLEGAL Hidden Hydraulics", PartSlot.SUSPENSION, "Secret height tricks for launches and corners. Adds disqualification scrutiny.", CarStats(acceleration=2, handling=4, durability=-2, reliability=-3, pit_friendliness=-2), 1000, ("illegal_risk",)),

    "juice_brakes": Part("juice_brakes", "Hydraulic Juice Brakes", PartSlot.BRAKES, "Stops before the wall, mostly.", CarStats(braking=3, reliability=1), 400),
    "drum_brake_fade": Part("drum_brake_fade", "Lightened Drums", PartSlot.BRAKES, "Quicker car, weaker braking late on.", CarStats(speed=1, braking=-2, heat=1), 250),
    "finned_aluminum_drums": Part("finned_aluminum_drums", "Finned Aluminum Drums", PartSlot.BRAKES, "Cooler drums and steady braking, not much bite.", CarStats(braking=2, heat=-1, reliability=1, speed=-1), 520),
    "oversized_master": Part("oversized_master", "Oversized Master Cylinder", PartSlot.BRAKES, "Strong pedal feel, extra weight over the nose.", CarStats(braking=3, handling=-1, pit_friendliness=-1), 480),
    "cooling_ducts": Part("cooling_ducts", "Brake Cooling Ducts", PartSlot.BRAKES, "Keeps brakes calm on hot tracks, adds clutter.", CarStats(braking=1, heat=-2, reliability=1, speed=-1), 420),
    "front_disc_conversion": Part("front_disc_conversion", "Front Disc Conversion", PartSlot.BRAKES, "Modern stopping power with suspicious parts-bin fitment.", CarStats(braking=4, handling=1, reliability=-1, pit_friendliness=-2), 850),
    "handbrake_turn_bar": Part("handbrake_turn_bar", "Handbrake Turn Bar", PartSlot.BRAKES, "Great for tight corners, costly if overused.", CarStats(handling=2, braking=1, reliability=-1, intimidation=1), 360),
    "illegal_line_lock": Part("illegal_line_lock", "ILLEGAL Line-Lock System", PartSlot.BRAKES, "Launch-control trickery. Adds disqualification scrutiny.", CarStats(acceleration=3, braking=2, heat=2, reliability=-2, pit_friendliness=-1), 900, ("illegal_risk",)),

    "chopped_roof": Part("chopped_roof", "Chopped Roof", PartSlot.BODY, "Lower profile, lower visibility.", CarStats(speed=1, handling=1, reliability=0, intimidation=1), 600),
    "channeled_body": Part("channeled_body", "Channelled Body", PartSlot.BODY, "Scrapes the deck; handles clean roads, hates rough ones.", CarStats(speed=1, handling=2, durability=-1, pit_friendliness=-1), 650),
    "bare_metal": Part("bare_metal", "Bare Metal & Primer", PartSlot.BODY, "Less weight, more menace, less protection.", CarStats(speed=1, durability=-1, intimidation=2, pit_friendliness=1), 150),
    "reinforced_frame": Part("reinforced_frame", "Reinforced Scrap Frame", PartSlot.BODY, "Heavy, strong, survives punishment.", CarStats(speed=-1, acceleration=-1, durability=4, pit_friendliness=1), 500),
    "sectioned_body": Part("sectioned_body", "Sectioned Body", PartSlot.BODY, "Lower and lighter, less forgiving in a hit.", CarStats(speed=2, handling=1, durability=-2, braking=-1), 700),
    "steel_belly_pan": Part("steel_belly_pan", "Steel Belly Pan", PartSlot.BODY, "Smooth underbody protection with extra weight.", CarStats(speed=1, durability=2, acceleration=-1, heat=1), 550),
    "lightweight_doors": Part("lightweight_doors", "Lightweight Door Skins", PartSlot.BODY, "Drops weight, drops protection.", CarStats(acceleration=2, speed=1, durability=-2, intimidation=-1), 420),
    "illegal_lead_ballast": Part("illegal_lead_ballast", "ILLEGAL Hidden Lead Ballast", PartSlot.BODY, "Secret balance weight for planted corners. Adds disqualification scrutiny.", CarStats(handling=4, braking=1, speed=-1, acceleration=-1, reliability=-2), 850, ("illegal_risk",)),

    "triple_carbs": Part("triple_carbs", "Triple Carb Setup", PartSlot.FUEL, "Three carbs, three chances to go fast or catch fire.", CarStats(acceleration=2, heat=2, reliability=-1, intimidation=1), 450),
    "moonshine_mix": Part("moonshine_mix", "Moonshine Fuel Mix", PartSlot.FUEL, "Hot fuel that may anger the engine and the officials.", CarStats(speed=2, acceleration=2, heat=3, reliability=-2), 300),
    "single_stromberg": Part("single_stromberg", "Single Stromberg Tune", PartSlot.FUEL, "Simple, dependable fuelling with modest pace.", CarStats(reliability=3, heat=-1, speed=-1, acceleration=-1), 250),
    "dual_carbs": Part("dual_carbs", "Dual Carb Setup", PartSlot.FUEL, "A useful power bump without triple-carb drama.", CarStats(acceleration=2, speed=1, heat=1, reliability=-1), 400),
    "big_jets": Part("big_jets", "Big Jet Carb Tune", PartSlot.FUEL, "More fuel, more pull, more heat.", CarStats(speed=2, acceleration=1, heat=2, reliability=-1), 300),
    "cool_can": Part("cool_can", "Fuel Cool Can", PartSlot.FUEL, "Cooler fuel steadies hot runs, but adds pit fuss.", CarStats(heat=-2, reliability=1, pit_friendliness=-1, acceleration=1), 320),
    "high_flow_pump": Part("high_flow_pump", "High-Flow Fuel Pump", PartSlot.FUEL, "Strong supply for big motors, risky when rattled.", CarStats(acceleration=2, speed=1, reliability=-2, pit_friendliness=-1), 500),
    "illegal_nitro_mix": Part("illegal_nitro_mix", "ILLEGAL Nitro Fuel Mix", PartSlot.FUEL, "Explosive illegal fuel. Adds disqualification scrutiny.", CarStats(speed=4, acceleration=4, heat=5, reliability=-4, intimidation=2), 1000, ("illegal_risk",)),

    "quick_change": Part("quick_change", "Quick-Change Rear End", PartSlot.TRANSMISSION, "Lets the rod suit the track better.", CarStats(acceleration=1, speed=1, reliability=1, pit_friendliness=1), 700),
    "long_throw_shifter": Part("long_throw_shifter", "Tall Long-Throw Shifter", PartSlot.TRANSMISSION, "Looks the part; costs time in traffic.", CarStats(acceleration=-1, intimidation=1), 250),
    "close_ratio_box": Part("close_ratio_box", "Close-Ratio Gearbox", PartSlot.TRANSMISSION, "Keeps the motor singing, punishes sloppy shifts.", CarStats(acceleration=3, speed=1, reliability=-2, heat=1), 750),
    "tall_rear_gears": Part("tall_rear_gears", "Tall Rear Gears", PartSlot.TRANSMISSION, "Great top speed, lazy launches.", CarStats(speed=3, acceleration=-2, reliability=1), 500),
    "short_rear_gears": Part("short_rear_gears", "Short Rear Gears", PartSlot.TRANSMISSION, "Punchy starts, runs out of breath.", CarStats(acceleration=3, speed=-2, heat=1), 500),
    "heavy_clutch": Part("heavy_clutch", "Heavy-Duty Clutch", PartSlot.TRANSMISSION, "Takes abuse, slows the left foot.", CarStats(durability=2, reliability=2, acceleration=-1, pit_friendliness=-1), 450),
    "lightened_flywheel": Part("lightened_flywheel", "Lightened Flywheel", PartSlot.TRANSMISSION, "Snappy revs and sharper starts, less smooth under load.", CarStats(acceleration=2, handling=1, reliability=-2), 520),
    "illegal_hidden_overdrive": Part("illegal_hidden_overdrive", "ILLEGAL Hidden Overdrive", PartSlot.TRANSMISSION, "Secret extra gearing for straights. Adds disqualification scrutiny.", CarStats(speed=4, acceleration=1, heat=2, reliability=-3, pit_friendliness=-2), 950, ("illegal_risk",)),

    "dirty_bumper": Part("dirty_bumper", "Rusty Battering Bumper", PartSlot.TRICK, "Makes contact scarier, and officials suspicious.", CarStats(intimidation=3, durability=1, speed=-1, handling=-1), 350),
    "smoke_screen": Part("smoke_screen", "Oil Smoke Screen", PartSlot.TRICK, "Rattles rivals and cooks the engine bay.", CarStats(intimidation=2, heat=2, reliability=-2, handling=-1), 450),
    "extra_spotlights": Part("extra_spotlights", "Blinding Spotlights", PartSlot.TRICK, "Useful at night, heavy on the nose.", CarStats(intimidation=2, braking=1, speed=-1, heat=1), 300),
    "pit_radio": Part("pit_radio", "Hidden Pit Radio", PartSlot.TRICK, "Better calls from the crew, but more cockpit clutter.", CarStats(pit_friendliness=3, reliability=1, handling=-1), 500),
    "fake_plate_swap": Part("fake_plate_swap", "Fake Plate Swap", PartSlot.TRICK, "Confuses officials briefly, annoys them later.", CarStats(intimidation=1, reliability=-1, pit_friendliness=1, heat=1), 250),
    "reinforced_push_bar": Part("reinforced_push_bar", "Reinforced Push Bar", PartSlot.TRICK, "Makes rivals think twice, costs speed.", CarStats(intimidation=3, durability=2, speed=-2, braking=-1), 420),
    "lucky_hula_girl": Part("lucky_hula_girl", "Lucky Dashboard Charm", PartSlot.TRICK, "No one can prove it helps, but the driver believes.", CarStats(reliability=1, intimidation=-1, pit_friendliness=1), 50),
    "illegal_road_spikes": Part("illegal_road_spikes", "ILLEGAL Drop-Spike Rig", PartSlot.TRICK, "Nasty hidden hardware. Adds disqualification scrutiny.", CarStats(intimidation=5, handling=-2, durability=-1, reliability=-4, speed=-1), 1100, ("illegal_risk",)),
}

CREW_MEMBERS: dict[str, CrewMember] = {
    "chief_mae_clipboard": CrewMember("chief_mae_clipboard", "Mae Clipboard", CrewSlot.CREW_CHIEF, "Calm calls and tidy pit timing, but conservative under pressure.", CarStats(pit_friendliness=3, reliability=2, acceleration=-1), 450),
    "chief_buzz_harper": CrewMember("chief_buzz_harper", "Buzz Harper", CrewSlot.CREW_CHIEF, "Aggressive strategy that finds speed and heat in equal measure.", CarStats(speed=1, acceleration=1, heat=2, pit_friendliness=1, reliability=-1), 520),
    "chief_dot_malloy": CrewMember("chief_dot_malloy", "Dot Malloy", CrewSlot.CREW_CHIEF, "Reads the race beautifully, but demands careful crew work.", CarStats(handling=1, braking=1, pit_friendliness=2, reliability=-1), 500),
    "chief_big_sal": CrewMember("chief_big_sal", "Big Sal DeMarco", CrewSlot.CREW_CHIEF, "Keeps everyone brave and loud, sometimes too loud.", CarStats(intimidation=2, durability=1, pit_friendliness=-1, heat=1), 380),
    "chief_lenora_lateflag": CrewMember("chief_lenora_lateflag", "Lenora Lateflag", CrewSlot.CREW_CHIEF, "Excellent late-race decisions with fussy early calls.", CarStats(reliability=1, handling=1, pit_friendliness=1, speed=-1), 430),

    "mechanic_wrench_wilma": CrewMember("mechanic_wrench_wilma", "Wrench Wilma", CrewSlot.LEAD_MECHANIC, "Fixes damage fast and keeps the rod alive, with extra weight in the toolkit.", CarStats(durability=2, reliability=2, speed=-1, pit_friendliness=1), 500),
    "mechanic_otto_sparks": CrewMember("mechanic_otto_sparks", "Otto Sparks", CrewSlot.LEAD_MECHANIC, "Hot tunes, hotter engine bay.", CarStats(speed=2, acceleration=1, heat=3, reliability=-2), 560),
    "mechanic_tiny_valves": CrewMember("mechanic_tiny_valves", "Tiny Valves", CrewSlot.LEAD_MECHANIC, "Precision engine work that hates rough hits.", CarStats(acceleration=2, reliability=1, durability=-1, pit_friendliness=-1), 480),
    "mechanic_grace_grease": CrewMember("mechanic_grace_grease", "Grace Grease", CrewSlot.LEAD_MECHANIC, "Keeps repairs smooth and predictable, but not spectacular.", CarStats(pit_friendliness=3, reliability=1, intimidation=-1), 420),
    "mechanic_rusty_nails": CrewMember("mechanic_rusty_nails", "Rusty Nails", CrewSlot.LEAD_MECHANIC, "Cheap fixes with surprising bite and questionable finish.", CarStats(intimidation=1, durability=1, reliability=-2, pit_friendliness=2), 300),

    "tyre_peggy_pneumatic": CrewMember("tyre_peggy_pneumatic", "Peggy Pneumatic", CrewSlot.TYRE_CHANGER, "Lightning rubber swaps, but she runs the tyres hard.", CarStats(pit_friendliness=4, acceleration=1, durability=-1, reliability=-1), 520),
    "tyre_slick_mickey": CrewMember("tyre_slick_mickey", "Slick Mickey", CrewSlot.TYRE_CHANGER, "Finds grip everywhere, at the cost of braking confidence.", CarStats(handling=2, acceleration=1, braking=-1, pit_friendliness=1), 480),
    "tyre_lou_whitewall": CrewMember("tyre_lou_whitewall", "Lou Whitewall", CrewSlot.TYRE_CHANGER, "Balanced tyre choices and steady pit work.", CarStats(handling=1, braking=1, reliability=1), 400),
    "tyre_rose_rimshot": CrewMember("tyre_rose_rimshot", "Rose Rimshot", CrewSlot.TYRE_CHANGER, "Tough wheels for rough tracks, slow swaps.", CarStats(durability=2, braking=1, pit_friendliness=-2), 380),
    "tyre_frankie_flatspot": CrewMember("tyre_frankie_flatspot", "Frankie Flatspot", CrewSlot.TYRE_CHANGER, "Cheap rubber tricks with wild launch bite.", CarStats(acceleration=2, handling=-1, reliability=-1, pit_friendliness=1), 320),

    "fuel_ivana_octane": CrewMember("fuel_ivana_octane", "Ivana Octane", CrewSlot.FUEL_RUNNER, "Hot fuel mixes and quick cans, but the gauges run angry.", CarStats(speed=1, acceleration=2, heat=3, reliability=-2), 560),
    "fuel_pops_stromberg": CrewMember("fuel_pops_stromberg", "Pops Stromberg", CrewSlot.FUEL_RUNNER, "Simple fuelling, fewer surprises.", CarStats(reliability=3, heat=-1, acceleration=-1), 420),
    "fuel_june_firecan": CrewMember("fuel_june_firecan", "June Firecan", CrewSlot.FUEL_RUNNER, "Fast refuels and fearless hands, with a little extra danger.", CarStats(pit_friendliness=3, heat=2, intimidation=1, reliability=-1), 470),
    "fuel_eddie_drip": CrewMember("fuel_eddie_drip", "Eddie Drip", CrewSlot.FUEL_RUNNER, "Squeezes range from scraps, but makes a mess under pressure.", CarStats(pit_friendliness=2, reliability=-2, speed=1), 280),
    "fuel_mabel_meter": CrewMember("fuel_mabel_meter", "Mabel Meter", CrewSlot.FUEL_RUNNER, "Careful fuel math that keeps heat down and pace modest.", CarStats(heat=-2, reliability=2, speed=-1), 390),

    "spotter_carla_corners": CrewMember("spotter_carla_corners", "Carla Corners", CrewSlot.SPOTTER, "Calls traffic early and helps the driver find clean lines.", CarStats(handling=2, braking=1, pit_friendliness=1), 500),
    "spotter_vince_vulture": CrewMember("spotter_vince_vulture", "Vince Vulture", CrewSlot.SPOTTER, "Spots weakness in rivals, not always the safest route.", CarStats(intimidation=2, speed=1, reliability=-1), 450),
    "spotter_nora_neon": CrewMember("spotter_nora_neon", "Nora Neon", CrewSlot.SPOTTER, "Brilliant night eyes and smooth calls, less help in heavy contact.", CarStats(handling=1, reliability=2, durability=-1), 430),
    "spotter_larry_loudspeaker": CrewMember("spotter_larry_loudspeaker", "Larry Loudspeaker", CrewSlot.SPOTTER, "Big energy on the radio, sometimes too much chatter.", CarStats(intimidation=1, acceleration=1, pit_friendliness=1, handling=-1), 360),
    "spotter_sue_sideeye": CrewMember("spotter_sue_sideeye", "Sue Side-Eye", CrewSlot.SPOTTER, "Keeps the driver out of trouble, but calls cautious overtakes.", CarStats(reliability=2, braking=1, speed=-1), 400),
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
