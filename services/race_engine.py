import random
import re
import time
from dataclasses import asdict

from data.defaults import POINTS_BY_POSITION, TRACKS
from models.domain import RaceEvent, RaceResult, RaceState, Team
from models.enums import EventType
from services.builds import BuildService

CAR_COLOURS = (
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "purple",
    "pink",
    "black",
    "white",
    "silver",
)

COLOUR_EMOJIS = {
    "red": "🔴",
    "blue": "🔵",
    "green": "🟢",
    "yellow": "🟡",
    "orange": "🟠",
    "purple": "🟣",
    "pink": "🌸",
    "black": "⚫",
    "white": "⚪",
    "silver": "⬜",
}

class RaceEngine:
    def __init__(self, track_key: str, teams: list[Team], seed: str | None = None):
        if track_key not in TRACKS:
            raise ValueError(f"Unknown track '{track_key}'.")
        if len(teams) < 2 or len(teams) > 10:
            raise ValueError("A race needs between 2 and 10 teams. Tournament races should use 10.")
        self.track = TRACKS[track_key]
        self.teams = teams
        self.seed = seed or f"ratrod-{int(time.time())}-{random.randint(1000,9999)}"
        self.rng = random.Random(self.seed)
        self.events: list[RaceEvent] = []
        self.states: list[RaceState] = []

    def _roll(self, sides: int = 20) -> int:
        return self.rng.randint(1, sides)

    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def _media_key(self, event_base: str, *parts: str | None) -> str:
        clean_parts = [self._safe(p) for p in parts if p]
        return "_".join([event_base, *clean_parts]) if clean_parts else event_base

    def _comment(self, event_type: EventType, lap: int, message: str, media_key: str | None = None) -> None:
        self.events.append(
            RaceEvent(
                event_type=event_type,
                lap=lap,
                message=message,
                media_key=media_key or event_type.value,
                audio_key=event_type.value,
            )
        )

    def _colour_label(self, state: RaceState) -> str:
        emoji = COLOUR_EMOJIS.get(state.car_colour, "🏎️")
        return f"{emoji} {state.car_colour.title()}"

    def _assign_colours(self) -> None:
        colours = list(CAR_COLOURS)
        self.rng.shuffle(colours)
        for state, colour in zip(self.states, colours):
            state.car_colour = colour

    def _rival_for(self, state: RaceState) -> RaceState | None:
        rivals = [s for s in self.states if s is not state and not s.dnf and not s.disqualified]
        if not rivals:
            return None
        return min(rivals, key=lambda s: abs(s.position - state.position))

    def _pace_score(self, state: RaceState) -> int:
        car = BuildService.effective_car_stats(state.team)
        drv = state.team.stats
        damage_penalty = state.damage // 12
        tyre_penalty = state.tyre_wear // 15
        return (
            self._roll(20)
            + car.speed * self.track.straight_bias
            + car.acceleration * 2
            + car.handling * self.track.corner_difficulty
            + car.braking
            + car.reliability
            + drv.handling * 2
            + drv.reflexes * 2
            + drv.nerve
            + state.momentum
            + self.track.modifiers.speed
            + self.track.modifiers.acceleration
            + self.track.modifiers.handling
            - damage_penalty
            - tyre_penalty
            - self.track.surface_roughness
        )

    def _lap_time(self, state: RaceState, pace: int) -> float:
        base = 78.0 + self.track.corner_difficulty * 2.5 - self.track.straight_bias * 2.0
        variance = self.rng.uniform(-2.5, 3.5)
        time_delta = max(48.0, base - pace * 0.42 + variance)
        if state.dnf or state.disqualified:
            return 9999.0
        return time_delta

    def _maybe_hazard(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified:
            return
        car = BuildService.effective_car_stats(state.team)
        drv = state.team.stats
        chance = self.track.hazard_rate + max(0, state.tyre_wear - 55) // 5 + max(0, state.damage - 45) // 5 - car.reliability - drv.reflexes
        if self._roll(100) <= chance:
            hazard = self.rng.choice(self.track.hazard_names)
            save = self._roll(20) + drv.handling + drv.reflexes + car.handling + car.braking - self.track.corner_difficulty
            if save >= 19:
                state.momentum += 1
                self._comment(
                    EventType.LAP,
                    lap,
                    f"{self._colour_label(state)} {state.team.driver_name} skates past a {hazard}, white-knuckled but still flying.",
                    self._media_key("lap_save", state.car_colour),
                )
            elif save >= 12:
                state.damage += self.rng.randint(3, 9)
                state.tyre_wear += self.rng.randint(2, 6)
                self._comment(
                    EventType.DAMAGE_MINOR,
                    lap,
                    f"{self._colour_label(state)} {state.team.car_name} clips trouble from a {hazard}. Sparks fly, but it keeps rolling.",
                    self._media_key("damage_minor", state.car_colour),
                )
            else:
                damage = self.rng.randint(12, 28)
                state.damage += damage
                state.tyre_wear += self.rng.randint(5, 12)
                self._comment(
                    EventType.DAMAGE_MAJOR,
                    lap,
                    f"Big trouble! {self._colour_label(state)} {state.team.driver_name} gets caught by a {hazard}. {state.team.car_name} takes {damage}% damage.",
                    self._media_key("damage_major", state.car_colour),
                )
                if state.damage >= 100:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        f"{self._colour_label(state)} {state.team.car_name} gives up in a thunderclap of smoke and bad language. {state.team.name} is out!",
                        self._media_key("destroyed", state.car_colour),
                    )

    def _maybe_illegal_move(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified:
            return
        car = BuildService.effective_car_stats(state.team)
        drv = state.team.stats
        dirty_chance = max(0, drv.aggression * 3 + car.intimidation + BuildService.illegal_risk(state.team) - drv.nerve)
        if self._roll(100) <= dirty_chance:
            rival = self._rival_for(state)
            rival_colour = rival.car_colour if rival else None
            rival_text = f" into the {rival.car_colour} car" if rival else " into a rival door"
            state.warnings += 1
            state.momentum += 1
            self._comment(
                EventType.ILLEGAL_MOVE,
                lap,
                f"{self._colour_label(state)} {state.team.driver_name} leans the rust{rival_text}. The officials throw warning #{state.warnings} at {state.team.name}.",
                self._media_key("illegal_move", state.car_colour, rival_colour),
            )
            if state.warnings >= 3:
                state.disqualified = True
                self._comment(
                    EventType.DISQUALIFIED,
                    lap,
                    f"That’s three warnings. {self._colour_label(state)} {state.team.name} is disqualified for driving like a back-alley debt collector.",
                    self._media_key("disqualified", state.car_colour),
                )

    def _maybe_pit(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified or lap == self.track.laps:
            return
        needs_pit = state.damage >= 45 or state.tyre_wear >= 60
        strategic = lap in {4, 6, 8} and (state.tyre_wear >= 38 or state.damage >= 28)
        if not (needs_pit or strategic):
            return
        car = BuildService.effective_car_stats(state.team)
        drv = state.team.stats
        state.pit_stops += 1
        pit_roll = self._roll(20) + drv.mechanics + car.pit_friendliness + car.reliability - self.track.pit_difficulty
        time_cost = 9.0 + self.track.pit_difficulty + self.rng.uniform(0, 6)
        media_key = self._media_key("pit_stop", state.car_colour)
        if pit_roll >= 22:
            fixed = self.rng.randint(22, 38)
            tyres = self.rng.randint(35, 55)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            state.total_time += time_cost
            self._comment(EventType.PIT_STOP, lap, f"Lightning pit stop! {self._colour_label(state)} {state.team.pit_crew_name} hammers {state.team.car_name} back into shape. Damage -{fixed}, tyres -{tyres}.", media_key)
        elif pit_roll >= 12:
            fixed = self.rng.randint(10, 24)
            tyres = self.rng.randint(20, 40)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            state.total_time += time_cost + 4
            self._comment(EventType.PIT_STOP, lap, f"Solid stop for {self._colour_label(state)} {state.team.name}. A few bolts, fresh rubber, and a prayer. Damage -{fixed}, tyres -{tyres}.", media_key)
        else:
            fixed = self.rng.randint(0, 10)
            state.damage = max(0, state.damage - fixed)
            state.total_time += time_cost + 12
            self._comment(EventType.PIT_STOP, lap, f"Botched pit stop! {self._colour_label(state)} {state.team.pit_crew_name} loses the rhythm. Only {fixed}% damage fixed and time bleeds away.", media_key)

    def _order_states(self) -> None:
        running = [s for s in self.states if not s.dnf and not s.disqualified]
        failed = [s for s in self.states if s.dnf or s.disqualified]
        running.sort(key=lambda s: (-s.lap, s.total_time))
        failed.sort(key=lambda s: (-s.lap, s.total_time))
        self.states = running + failed
        for idx, s in enumerate(self.states, start=1):
            s.position = idx

    def run(self) -> tuple[list[RaceEvent], list[RaceResult], str]:
        self.states = [RaceState(team=t, position=i + 1) for i, t in enumerate(self.teams)]
        self.rng.shuffle(self.states)
        for idx, s in enumerate(self.states, start=1):
            s.position = idx
        self._assign_colours()

        colour_lines = "\n".join(
            f"{self._colour_label(s)} — **{s.team.name}** ({s.team.driver_name}) in *{s.team.car_name}*"
            for s in self.states
        )
        self._comment(
            EventType.START,
            0,
            f"Engines bark under diner neon. {len(self.states)} rat rods roll out for {self.track.laps} laps at {self.track.name}.\n\n{colour_lines}",
            "start",
        )

        for lap in range(1, self.track.laps + 1):
            for state in list(self.states):
                if state.dnf or state.disqualified:
                    continue
                pace = self._pace_score(state)
                state.total_time += self._lap_time(state, pace)
                state.lap = lap
                car = BuildService.effective_car_stats(state.team)
                state.tyre_wear += max(1, self.track.surface_roughness + self.rng.randint(1, 5) - car.handling // 2)
                state.damage += max(0, self.track.surface_roughness // 2 + self.rng.randint(0, 2) - car.durability // 3)
                state.momentum = max(-3, min(4, state.momentum + self.rng.choice([-1, 0, 0, 1])))
                self._maybe_hazard(state, lap)
                self._maybe_illegal_move(state, lap)
                self._maybe_pit(state, lap)
                if state.tyre_wear >= 100 and not state.dnf:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        f"Tyres are gone on {self._colour_label(state)} {state.team.car_name}! Rubber turns to smoke and {state.team.name} is out.",
                        self._media_key("destroyed", state.car_colour),
                    )
                if state.damage >= 100 and not state.dnf:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        f"{self._colour_label(state)} {state.team.car_name} breaks apart like cheap furniture. {state.team.name} cannot continue.",
                        self._media_key("destroyed", state.car_colour),
                    )

            previous = {s.team.id: s.position for s in self.states}
            previous_order = list(self.states)
            self._order_states()
            for s in self.states:
                old = previous.get(s.team.id, s.position)
                if not s.dnf and not s.disqualified and s.position < old:
                    defender = previous_order[s.position - 1] if s.position - 1 < len(previous_order) else None
                    defender_colour = defender.car_colour if defender and defender is not s else None
                    defender_text = f" past the {defender_colour} car" if defender_colour else " through traffic"
                    self._comment(
                        EventType.OVERTAKE,
                        lap,
                        f"Overtake! {self._colour_label(s)} {s.team.driver_name} muscles {s.team.car_name}{defender_text} up to P{s.position}, all rust and nerve.",
                        self._media_key("overtake", s.car_colour, defender_colour),
                    )
            leader = self.states[0]
            self._comment(
                EventType.LAP,
                lap,
                f"Lap {lap}/{self.track.laps}: leader is {self._colour_label(leader)} {leader.team.name} in {leader.team.car_name}.",
                self._media_key("lap_leader", leader.car_colour),
            )

        self._order_states()
        results: list[RaceResult] = []
        for idx, s in enumerate(self.states, start=1):
            points = 0 if s.disqualified else POINTS_BY_POSITION.get(idx, 0)
            results.append(RaceResult(
                team_id=s.team.id or 0,
                team_name=s.team.name,
                driver_name=s.team.driver_name,
                position=idx,
                laps_completed=s.lap,
                total_time=s.total_time,
                points=points,
                warnings=s.warnings,
                dnf=s.dnf,
                disqualified=s.disqualified,
                damage=min(100, s.damage),
                tyre_wear=min(100, s.tyre_wear),
            ))

        podium_states = self.states[:3]
        podium = results[:3]
        winner = podium_states[0]
        second_colour = podium_states[1].car_colour if len(podium_states) > 1 else None
        third_colour = podium_states[2].car_colour if len(podium_states) > 2 else None
        self._comment(
            EventType.FINISH,
            self.track.laps,
            f"Chequered flag! {self._colour_label(winner)} {results[0].team_name} wins at {self.track.name}!",
            self._media_key("finish_line", winner.car_colour),
        )
        self._comment(
            EventType.PODIUM,
            self.track.laps,
            f"Podium: 1st {podium[0].team_name}, 2nd {podium[1].team_name if len(podium)>1 else '-'}, 3rd {podium[2].team_name if len(podium)>2 else '-'}.",
            self._media_key("podium", winner.car_colour, second_colour, third_colour),
        )
        return self.events, results, self.seed

    @staticmethod
    def events_to_dicts(events: list[RaceEvent]) -> list[dict]:
        return [asdict(e) for e in events]

    @staticmethod
    def results_to_dicts(results: list[RaceResult]) -> list[dict]:
        return [asdict(r) for r in results]
