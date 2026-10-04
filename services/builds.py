from data.defaults import CAR_DEFINITIONS, CREW_MEMBERS, PARTS
from models.domain import CrewMember, Part, Team
from models.enums import CrewSlot, PartSlot
from models.stats import CarStats

ILLEGAL_PART_DISQUALIFICATION_RISK = 6

STAT_MIN = -6
STAT_MAX = 14
HEAT_MIN = -4
HEAT_MAX = 16
RELIABILITY_MAX = 12
PIT_FRIENDLINESS_MAX = 12


class BuildService:
    @staticmethod
    def equipped_parts_by_slot(team: Team) -> dict[PartSlot, Part]:
        equipped = {}
        for key in team.parts:
            part = PARTS.get(key)
            if part and part.slot not in equipped:
                equipped[part.slot] = part
        return equipped

    @staticmethod
    def equipped_crew_by_slot(team: Team) -> dict[CrewSlot, CrewMember]:
        equipped = {}
        for slot in CrewSlot:
            key = team.crew.get(slot.value)
            crew_member = CREW_MEMBERS.get(key)
            if crew_member:
                equipped[slot] = crew_member
        return equipped

    @staticmethod
    def tuning_efficiency(team: Team) -> float:
        # Every extra system makes the complete package harder to tune. A few
        # carefully chosen parts retain most of their value; an eight-slot
        # performance stack has strong diminishing returns instead of becoming
        # an automatic end-game super-car. Drawbacks are never scaled away.
        from services.balance import build_strain

        count = len(BuildService.equipped_parts_by_slot(team))
        if count == 0:
            return 1.0
        strain = build_strain(team)
        over_four = max(0, count - 4)
        return max(0.32, 1.0 / (1.0 + over_four * 0.20 + strain * 0.055))

    @staticmethod
    def effective_car_stats(team: Team) -> CarStats:
        # v0.4.3: crew are specialists, not a second stack of permanent car stats.
        # Only the rod and fitted hardware define the persistent car-stat line.
        base = CAR_DEFINITIONS[team.archetype.value].base_stats
        parts = BuildService.equipped_parts_by_slot(team).values()
        raw_delta = CarStats()
        for part in parts:
            raw_delta = raw_delta + part.modifiers

        efficiency = BuildService.tuning_efficiency(team)
        values = {}
        base_values = base.as_dict()
        delta_values = raw_delta.as_dict()
        for key, base_value in base_values.items():
            delta = delta_values[key]
            # Heat is inverted: negative heat is beneficial and therefore gets
            # diminishing returns; positive heat is a drawback and stays whole.
            beneficial = delta < 0 if key == "heat" else delta > 0
            adjusted = int(round(delta * efficiency)) if beneficial else delta
            values[key] = base_value + adjusted
        return BuildService.clamp_car_stats(CarStats(**values))

    @staticmethod
    def clamp_car_stats(stats: CarStats) -> CarStats:
        values = {}
        for key, value in stats.as_dict().items():
            low = HEAT_MIN if key == "heat" else STAT_MIN
            high = STAT_MAX
            if key == "heat":
                high = HEAT_MAX
            elif key == "reliability":
                high = RELIABILITY_MAX
            elif key == "pit_friendliness":
                high = PIT_FRIENDLINESS_MAX
            values[key] = max(low, min(high, value))
        return CarStats(**values)

    @staticmethod
    def part_summary(team: Team) -> str:
        if not team.parts:
            return "No custom parts fitted yet."
        labels = []
        for part in BuildService.equipped_parts_by_slot(team).values():
            from services.balance import part_strain
            risk = f" +{ILLEGAL_PART_DISQUALIFICATION_RISK}% DSQ" if "illegal_risk" in part.risk_tags else ""
            labels.append(f"{part.name} [strain {part_strain(part)}{risk}]")
        return ", ".join(labels) if labels else "No custom parts fitted yet."

    @staticmethod
    def is_illegal_part_key(key: str) -> bool:
        part = PARTS.get(key)
        return bool(part and "illegal_risk" in part.risk_tags)

    @staticmethod
    def illegal_part_count(team: Team) -> int:
        return sum(1 for part in BuildService.equipped_parts_by_slot(team).values() if "illegal_risk" in part.risk_tags)

    @staticmethod
    def illegal_disqualification_risk_percent(team: Team) -> int:
        return min(100, BuildService.illegal_part_count(team) * ILLEGAL_PART_DISQUALIFICATION_RISK)

    @staticmethod
    def illegal_risk(team: Team) -> int:
        return BuildService.illegal_disqualification_risk_percent(team)

    @staticmethod
    def build_strain(team: Team) -> int:
        from services.balance import build_strain
        return build_strain(team)

    @staticmethod
    def build_strain_label(team: Team) -> str:
        from services.balance import strain_label
        return strain_label(BuildService.build_strain(team))

    @staticmethod
    def crew_effect_summary(team: Team) -> str:
        from services.balance import crew_effect_summary
        return crew_effect_summary(team)

    @staticmethod
    def crew_stats(team: Team) -> CarStats:
        total = CarStats()
        for crew_member in BuildService.equipped_crew_by_slot(team).values():
            total = total + crew_member.modifiers
        return total

    @staticmethod
    def crew_summary(team: Team) -> str:
        if not team.crew:
            return "No custom pit crew assigned yet."
        labels = []
        for slot in CrewSlot:
            slot_value = slot.value
            key = team.crew.get(slot_value)
            crew_member = CREW_MEMBERS.get(key)
            if crew_member:
                labels.append(f"{slot_value.replace('_', ' ').title()}: {crew_member.name}")
        return "\n".join(labels) if labels else "No custom pit crew assigned yet."
