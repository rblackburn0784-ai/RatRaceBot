from data.defaults import CAR_DEFINITIONS, PARTS
from models.domain import Team
from models.stats import CarStats

class BuildService:
    @staticmethod
    def effective_car_stats(team: Team) -> CarStats:
        base = CAR_DEFINITIONS[team.archetype.value].base_stats
        total = base
        for key in team.parts:
            part = PARTS.get(key)
            if part:
                total = total + part.modifiers
        return total

    @staticmethod
    def part_summary(team: Team) -> str:
        if not team.parts:
            return "No custom parts fitted yet."
        return ", ".join(PARTS[p].name for p in team.parts if p in PARTS)

    @staticmethod
    def illegal_risk(team: Team) -> int:
        risk = 0
        for key in team.parts:
            part = PARTS.get(key)
            if part and "illegal_risk" in part.risk_tags:
                risk += 6
        return risk
