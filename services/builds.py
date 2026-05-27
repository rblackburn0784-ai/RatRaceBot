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
    def effective_car_stats(team: Team) -> CarStats:
        base = CAR_DEFINITIONS[team.archetype.value].base_stats
        total = base
        for part in BuildService.equipped_parts_by_slot(team).values():
            total = total + part.modifiers
        for crew_member in BuildService.equipped_crew_by_slot(team).values():
            total = total + crew_member.modifiers
        return BuildService.clamp_car_stats(total)

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
            suffix = f" (+{ILLEGAL_PART_DISQUALIFICATION_RISK}% DSQ risk)" if "illegal_risk" in part.risk_tags else ""
            labels.append(f"{part.name}{suffix}")
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
