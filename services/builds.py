from data.defaults import CAR_DEFINITIONS, PARTS
from models.domain import Team
from models.stats import CarStats

ILLEGAL_PART_DISQUALIFICATION_RISK = 6


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
        labels = []
        for key in team.parts:
            part = PARTS.get(key)
            if not part:
                continue
            suffix = f" (+{ILLEGAL_PART_DISQUALIFICATION_RISK}% DSQ risk)" if BuildService.is_illegal_part_key(key) else ""
            labels.append(f"{part.name}{suffix}")
        return ", ".join(labels) if labels else "No custom parts fitted yet."

    @staticmethod
    def is_illegal_part_key(key: str) -> bool:
        part = PARTS.get(key)
        return bool(part and "illegal_risk" in part.risk_tags)

    @staticmethod
    def illegal_part_count(team: Team) -> int:
        return sum(1 for key in team.parts if BuildService.is_illegal_part_key(key))

    @staticmethod
    def illegal_disqualification_risk_percent(team: Team) -> int:
        return min(100, BuildService.illegal_part_count(team) * ILLEGAL_PART_DISQUALIFICATION_RISK)

    @staticmethod
    def illegal_risk(team: Team) -> int:
        return BuildService.illegal_disqualification_risk_percent(team)
