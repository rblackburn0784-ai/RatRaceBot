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

START_LINES = (
    "Engines bark under diner neon. {count} rat rods roll out for {laps} laps at {track}.\n\n{colour_lines}",
    "The flagman steps back and {count} machines rattle onto {track} for {laps} laps.\n\n{colour_lines}",
    "Chrome shakes, pipes cough, and {count} crews line up for {laps} laps at {track}.\n\n{colour_lines}",
    "The crowd leans over the barriers as {count} rods take their marks at {track}.\n\n{colour_lines}",
    "{track} is open for business: {count} cars, {laps} laps, and no promises.\n\n{colour_lines}",
)

HAZARD_SAVE_LINES = (
    "{car} {driver} skates past a {hazard}, white-knuckled but still flying.",
    "{car} {driver} threads the gap around a {hazard} and comes out looking brave.",
    "{car} {driver} flicks past a {hazard}; that was a prayer with wheels.",
    "{car} {team} dodges a {hazard} by inches and somehow gains nerve from it.",
    "{car} {car_name} twitches at a {hazard}, catches grip, and stays in the hunt.",
)

DAMAGE_MINOR_LINES = (
    "{car} {car_name} clips trouble from a {hazard}. Sparks fly, but it keeps rolling.",
    "{car} {driver} gets kissed by a {hazard}; ugly noise, minor damage.",
    "{car} {team} bounces through a {hazard} and leaves a few bits behind.",
    "{car} {car_name} scrapes past a {hazard}. The crew will hear about that later.",
    "{car} {driver} rides out a {hazard}, losing paint and dignity but not pace.",
)

DAMAGE_MAJOR_LINES = (
    "Big trouble! {car} {driver} gets caught by a {hazard}. {car_name} takes {damage}% damage.",
    "{car} {car_name} gets hammered by a {hazard}. That is {damage}% damage and a very quiet pit wall.",
    "{car} {team} takes a savage hit from a {hazard}. The rod is carrying {damage}% damage now.",
    "{car} {driver} cannot dodge the {hazard}. Metal screams, damage jumps by {damage}%.",
    "{car} {car_name} meets the {hazard} the hard way: {damage}% damage and a long lap ahead.",
)

DESTROYED_LINES = (
    "{car} {car_name} gives up in a thunderclap of smoke and bad language. {team} is out!",
    "{car} {team} is done. {car_name} coughs once, shudders, and quits the race.",
    "{car} {car_name} has taken all it can take. {team} is parked for the day.",
    "{car} {driver} nurses {car_name} one corner too far. Race over for {team}.",
    "{car} {team} disappears behind smoke and waving arms. That is a DNF.",
)

ILLEGAL_MOVE_LINES = (
    "{car} {driver} leans the rust{rival_text}. The officials throw warning #{warnings} at {team}.",
    "{car} {driver} makes contact{rival_text} and pretends it was racing room. Warning #{warnings}.",
    "{car} {team} gets nasty{rival_text}; the flag stand does not miss it. Warning #{warnings}.",
    "{car} {driver} uses more bumper than bravery{rival_text}. Warning #{warnings} lands immediately.",
    "{car} {car_name} barges through{rival_text}. The officials mark warning #{warnings} beside {team}.",
)

DISQUALIFIED_LINES = (
    "That is three warnings. {car} {team} is disqualified for driving like a back-alley debt collector.",
    "{car} {team} has tested the officials one time too many. Disqualified.",
    "The clipboard comes out for {car} {team}. Three warnings, no more race.",
    "{car} {driver} is waved off the track. {team} is done on penalties.",
    "{car} {team} finally runs out of excuses. Black flag, disqualified.",
)

SCRUTINEERING_DSQ_LINES = (
    "Scrutineering catches {car} {team} before the flag. {illegal_count} illegal part(s), {risk}% risk, and the black flag wins.",
    "{car} {team} gets hauled aside in inspection. The hidden hardware is too hot: disqualified.",
    "Officials crawl over {car} {car_name} and find enough trouble to end {team}'s day before lap one.",
    "{car} {driver} gambled on illegal kit and lost the paperwork fight. {team} is disqualified.",
    "{car} {team} fails the pre-race inspection with {illegal_count} illegal part(s). Risk became reality.",
)

PIT_FAST_LINES = (
    "Lightning pit stop! {car} {pit_crew} hammers {car_name} back into shape. Damage -{fixed}, tyres -{tyres}.",
    "{car} {pit_crew} works like a dance hall knife act. {car_name} leaves with damage -{fixed}, tyres -{tyres}.",
    "Clean stop for {car} {team}. Tools flash, rubber changes, damage -{fixed}, tyres -{tyres}.",
    "{car} {pit_crew} nails the stop. {car_name} is patched fast: damage -{fixed}, tyres -{tyres}.",
    "{car} {car_name} dives in and bursts back out. Damage -{fixed}, tyres -{tyres}.",
)

PIT_SOLID_LINES = (
    "Solid stop for {car} {team}. A few bolts, fresh rubber, and a prayer. Damage -{fixed}, tyres -{tyres}.",
    "{car} {pit_crew} loses no sleep in the lane. Damage -{fixed}, tyres -{tyres}.",
    "{car} {car_name} gets the ordinary miracle: tools, tyres, and damage -{fixed}.",
    "Useful work from {car} {pit_crew}. Damage -{fixed}, tyres -{tyres}, back to the noise.",
    "{car} {team} gets a tidy service. Nothing fancy, but damage -{fixed} and tyres -{tyres}.",
)

PIT_BOTCHED_LINES = (
    "Botched pit stop! {car} {pit_crew} loses the rhythm. Only {fixed}% damage fixed and time bleeds away.",
    "{car} {pit_crew} turns the stop into a toolbox argument. Only {fixed}% damage fixed.",
    "Bad stop for {car} {team}. The clock runs mean and only {fixed}% damage comes off.",
    "{car} {car_name} sits too long in the lane. Only {fixed}% damage fixed.",
    "{car} {pit_crew} fumbles it. The rod leaves late with just {fixed}% damage repaired.",
)

TYRE_DNF_LINES = (
    "Tyres are gone on {car} {car_name}! Rubber turns to smoke and {team} is out.",
    "{car} {team} runs out of rubber and road at the same time. DNF.",
    "{car} {car_name} sheds its tyres in a long black streak. {team} cannot continue.",
    "{car} {driver} has nothing left under the rims. Race over for {team}.",
    "{car} {car_name} is skating on ghosts. The tyres are finished, and so is the race.",
)

DAMAGE_DNF_LINES = (
    "{car} {car_name} breaks apart like cheap furniture. {team} cannot continue.",
    "{car} {team} has more damage than car. That is the end of the run.",
    "{car} {driver} tries to keep {car_name} alive, but the machine says no.",
    "{car} {car_name} folds under the punishment. {team} is out.",
    "{car} {team} limps, coughs, and stops. Too much damage to go on.",
)

OVERTAKE_LINES = (
    "Overtake! {car} {driver} muscles {car_name}{defender_text} up to P{position}, all rust and nerve.",
    "{car} {driver} finds daylight{defender_text} and grabs P{position}.",
    "{car} {team} surges{defender_text}; that is P{position} now.",
    "{car} {car_name} punches through{defender_text} and climbs to P{position}.",
    "{car} {driver} times it beautifully{defender_text}. Move made, P{position}.",
    "{car} {team} takes the lane{defender_text} and refuses to give it back. P{position}.",
)

LAST_MINUTE_WIN_LINES = (
    "Last-lap steal! {car} {driver} snatches the lead at the death.",
    "{car} {team} waits until the final breath and steals first place.",
    "Right at the wire, {car} {driver} takes the lead and breaks hearts behind.",
    "{car} {car_name} launches one final attack and turns it into the lead.",
    "Final-lap robbery from {car} {team}. First place changes hands late.",
)

LAP_LEADER_LINES = (
    "Lap {lap}/{laps}: leader is {car} {team} in {car_name}.",
    "Lap {lap}/{laps}: {car} {team} controls the road in {car_name}.",
    "Lap {lap}/{laps}: {car} {driver} has the field chasing {car_name}.",
    "Lap {lap}/{laps}: {car} {team} is showing the way.",
    "Lap {lap}/{laps}: {car} {car_name} leads, but nobody looks comfortable.",
)

FINISH_LINES = (
    "Chequered flag! {car} {team} wins at {track}!",
    "{car} {team} reaches the line first at {track}. What a run.",
    "It is over at {track}: {car} {team} takes the win.",
    "{car} {driver} brings {team} home first at {track}.",
    "Flag down, noise up: {car} {team} wins {track}.",
)

PODIUM_LINES = (
    "Podium: 1st {first}, 2nd {second}, 3rd {third}.",
    "Top three at the stripe: {first}, {second}, {third}.",
    "The boxes belong to {first}, {second}, and {third}.",
    "Champagne if anyone can afford it: {first}, {second}, {third}.",
    "Final podium order: {first} over {second} and {third}.",
)

class RaceEngine:
    def __init__(
        self,
        track_key: str,
        teams: list[Team],
        seed: str | None = None,
        initial_damage_by_team_id: dict[int, int] | None = None,
        laps: int | None = None,
    ):
        if track_key not in TRACKS:
            raise ValueError(f"Unknown track '{track_key}'.")
        if len(teams) < 2 or len(teams) > 10:
            raise ValueError("A race needs between 2 and 10 teams. Tournament races should use 10.")
        self.track = TRACKS[track_key]
        self.laps = laps or self.track.laps
        if self.laps not in {5, 7, 10}:
            raise ValueError("Race laps must be 5, 7, or 10.")
        self.teams = teams
        self.initial_damage_by_team_id = initial_damage_by_team_id or {}
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

    def _line(self, templates: tuple[str, ...], **values) -> str:
        return self.rng.choice(templates).format(**values)

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

    def _track_adjusted_car_stats(self, team: Team):
        return BuildService.clamp_car_stats(BuildService.effective_car_stats(team) + self.track.modifiers)

    def _pace_score(self, state: RaceState) -> int:
        car = self._track_adjusted_car_stats(state.team)
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
            - car.heat
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
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        chance = (
            self.track.hazard_rate
            + max(0, state.tyre_wear - 55) // 5
            + max(0, state.damage - 45) // 5
            + max(0, car.heat)
            - car.reliability
            - drv.reflexes
        )
        chance = max(5, min(65, chance))
        if self._roll(100) <= chance:
            hazard = self.rng.choice(self.track.hazard_names)
            save = self._roll(20) + drv.handling + drv.reflexes + car.handling + car.braking - self.track.corner_difficulty
            if save >= 19:
                state.near_misses += 1
                state.momentum += 1
                self._comment(
                    EventType.LAP,
                    lap,
                    self._line(
                        HAZARD_SAVE_LINES,
                        car=self._colour_label(state),
                        driver=state.team.driver_name,
                        team=state.team.name,
                        car_name=state.team.car_name,
                        hazard=hazard,
                    ),
                    self._media_key("lap_save", state.car_colour),
                )
            elif save >= 12:
                state.crashes += 1
                state.damage += self.rng.randint(3, 9)
                state.tyre_wear += self.rng.randint(2, 6)
                self._comment(
                    EventType.DAMAGE_MINOR,
                    lap,
                    self._line(
                        DAMAGE_MINOR_LINES,
                        car=self._colour_label(state),
                        driver=state.team.driver_name,
                        team=state.team.name,
                        car_name=state.team.car_name,
                        hazard=hazard,
                    ),
                    self._media_key("damage_minor", state.car_colour),
                )
            else:
                state.crashes += 1
                damage = self.rng.randint(12, 28)
                state.damage += damage
                state.tyre_wear += self.rng.randint(5, 12)
                self._comment(
                    EventType.DAMAGE_MAJOR,
                    lap,
                    self._line(
                        DAMAGE_MAJOR_LINES,
                        car=self._colour_label(state),
                        driver=state.team.driver_name,
                        team=state.team.name,
                        car_name=state.team.car_name,
                        hazard=hazard,
                        damage=damage,
                    ),
                    self._media_key("damage_major", state.car_colour),
                )
                if state.damage >= 100:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        self._line(
                            DESTROYED_LINES,
                            car=self._colour_label(state),
                            driver=state.team.driver_name,
                            team=state.team.name,
                            car_name=state.team.car_name,
                        ),
                        self._media_key("destroyed", state.car_colour),
                    )

    def _maybe_illegal_move(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified:
            return
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        dirty_chance = max(0, drv.aggression * 3 + car.intimidation + BuildService.illegal_risk(state.team) - drv.nerve)
        if self._roll(100) <= dirty_chance:
            rival = self._rival_for(state)
            rival_colour = rival.car_colour if rival else None
            rival_text = f" into the {rival.car_colour} car" if rival else " into a rival door"
            state.illegal_moves += 1
            state.warnings += 1
            state.momentum += 1
            self._comment(
                EventType.ILLEGAL_MOVE,
                lap,
                self._line(
                    ILLEGAL_MOVE_LINES,
                    car=self._colour_label(state),
                    driver=state.team.driver_name,
                    team=state.team.name,
                    car_name=state.team.car_name,
                    rival_text=rival_text,
                    warnings=state.warnings,
                ),
                self._media_key("illegal_move", state.car_colour, rival_colour),
            )
            if state.warnings >= 3:
                state.disqualified = True
                self._comment(
                    EventType.DISQUALIFIED,
                    lap,
                    self._line(
                        DISQUALIFIED_LINES,
                        car=self._colour_label(state),
                        driver=state.team.driver_name,
                        team=state.team.name,
                        car_name=state.team.car_name,
                    ),
                    self._media_key("disqualified", state.car_colour),
                )

    def _maybe_illegal_scrutineering(self, state: RaceState) -> None:
        risk = BuildService.illegal_disqualification_risk_percent(state.team)
        if state.dnf or state.disqualified or risk <= 0:
            return
        if self._roll(100) <= risk:
            state.disqualified = True
            self._comment(
                EventType.DISQUALIFIED,
                0,
                self._line(
                    SCRUTINEERING_DSQ_LINES,
                    car=self._colour_label(state),
                    driver=state.team.driver_name,
                    team=state.team.name,
                    car_name=state.team.car_name,
                    illegal_count=BuildService.illegal_part_count(state.team),
                    risk=risk,
                ),
                self._media_key("disqualified", state.car_colour),
            )

    def _maybe_pit(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified or lap == self.laps:
            return
        needs_pit = state.damage >= 45 or state.tyre_wear >= 60
        strategic_laps = {max(2, self.laps // 2), max(3, self.laps - 2)}
        strategic = lap in strategic_laps and (state.tyre_wear >= 38 or state.damage >= 28)
        if not (needs_pit or strategic):
            return
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        state.pit_stops += 1
        pit_bonus = max(-6, min(14, (drv.mechanics + car.pit_friendliness + car.reliability) // 2))
        pit_roll = self._roll(20) + pit_bonus - self.track.pit_difficulty
        time_cost = 9.0 + self.track.pit_difficulty + self.rng.uniform(0, 6)
        media_key = self._media_key("pit_stop", state.car_colour)
        if pit_roll >= 22:
            fixed = self.rng.randint(22, 38)
            tyres = self.rng.randint(35, 55)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            state.total_time += time_cost
            self._comment(
                EventType.PIT_STOP,
                lap,
                self._line(
                    PIT_FAST_LINES,
                    car=self._colour_label(state),
                    driver=state.team.driver_name,
                    team=state.team.name,
                    pit_crew=state.team.pit_crew_name,
                    car_name=state.team.car_name,
                    fixed=fixed,
                    tyres=tyres,
                ),
                media_key,
            )
        elif pit_roll >= 12:
            fixed = self.rng.randint(10, 24)
            tyres = self.rng.randint(20, 40)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            state.total_time += time_cost + 4
            self._comment(
                EventType.PIT_STOP,
                lap,
                self._line(
                    PIT_SOLID_LINES,
                    car=self._colour_label(state),
                    driver=state.team.driver_name,
                    team=state.team.name,
                    pit_crew=state.team.pit_crew_name,
                    car_name=state.team.car_name,
                    fixed=fixed,
                    tyres=tyres,
                ),
                media_key,
            )
        else:
            fixed = self.rng.randint(0, 10)
            state.damage = max(0, state.damage - fixed)
            state.total_time += time_cost + 12
            self._comment(
                EventType.PIT_STOP,
                lap,
                self._line(
                    PIT_BOTCHED_LINES,
                    car=self._colour_label(state),
                    driver=state.team.driver_name,
                    team=state.team.name,
                    pit_crew=state.team.pit_crew_name,
                    car_name=state.team.car_name,
                    fixed=fixed,
                ),
                media_key,
            )

    def _order_states(self) -> None:
        running = [s for s in self.states if not s.dnf and not s.disqualified]
        failed = [s for s in self.states if s.dnf or s.disqualified]
        running.sort(key=lambda s: (-s.lap, s.total_time))
        failed.sort(key=lambda s: (-s.lap, s.total_time))
        self.states = running + failed
        for idx, s in enumerate(self.states, start=1):
            s.position = idx

    def run(self) -> tuple[list[RaceEvent], list[RaceResult], str]:
        self.states = []
        for i, team in enumerate(self.teams):
            starting_damage = max(0, min(30, self.initial_damage_by_team_id.get(team.id or 0, 0)))
            self.states.append(
                RaceState(
                    team=team,
                    position=i + 1,
                    damage=starting_damage,
                    starting_damage=starting_damage,
                )
            )
        self.rng.shuffle(self.states)
        for idx, s in enumerate(self.states, start=1):
            s.position = idx
        self._assign_colours()

        colour_lines = "\n".join(
            f"{self._colour_label(s)} — **{s.team.name}** ({s.team.driver_name}) in *{s.team.car_name}*"
            f"{f' — {s.starting_damage}% carryover damage' if s.starting_damage else ''}"
            for s in self.states
        )
        self._comment(
            EventType.START,
            0,
            self._line(
                START_LINES,
                count=len(self.states),
                laps=self.laps,
                track=self.track.name,
                colour_lines=colour_lines,
            ),
            "start",
        )

        for state in list(self.states):
            self._maybe_illegal_scrutineering(state)

        for lap in range(1, self.laps + 1):
            if not any(not s.dnf and not s.disqualified for s in self.states):
                break
            for state in list(self.states):
                if state.dnf or state.disqualified:
                    continue
                pace = self._pace_score(state)
                state.total_time += self._lap_time(state, pace)
                state.lap = lap
                car = self._track_adjusted_car_stats(state.team)
                state.tyre_wear += max(1, self.track.surface_roughness + self.rng.randint(1, 5) - car.handling // 2)
                state.damage += max(
                    0,
                    self.track.surface_roughness // 2
                    + self.rng.randint(0, 2)
                    + max(0, car.heat) // 4
                    - car.durability // 3,
                )
                state.momentum = max(-3, min(4, state.momentum + self.rng.choice([-1, 0, 0, 1])))
                self._maybe_hazard(state, lap)
                self._maybe_illegal_move(state, lap)
                self._maybe_pit(state, lap)
                if state.tyre_wear >= 100 and not state.dnf:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        self._line(
                            TYRE_DNF_LINES,
                            car=self._colour_label(state),
                            driver=state.team.driver_name,
                            team=state.team.name,
                            car_name=state.team.car_name,
                        ),
                        self._media_key("destroyed", state.car_colour),
                    )
                if state.damage >= 100 and not state.dnf:
                    state.dnf = True
                    self._comment(
                        EventType.DESTROYED,
                        lap,
                        self._line(
                            DAMAGE_DNF_LINES,
                            car=self._colour_label(state),
                            driver=state.team.driver_name,
                            team=state.team.name,
                            car_name=state.team.car_name,
                        ),
                        self._media_key("destroyed", state.car_colour),
                    )

            previous = {s.team.id: s.position for s in self.states}
            previous_order = list(self.states)
            self._order_states()
            for s in self.states:
                old = previous.get(s.team.id, s.position)
                if not s.dnf and not s.disqualified and s.position < old:
                    places_gained = old - s.position
                    s.overtakes += places_gained
                    defender = previous_order[s.position - 1] if s.position - 1 < len(previous_order) else None
                    defender_colour = defender.car_colour if defender and defender is not s else None
                    defender_text = f" past the {defender_colour} car" if defender_colour else " through traffic"
                    self._comment(
                        EventType.OVERTAKE,
                        lap,
                        self._line(
                            OVERTAKE_LINES,
                            car=self._colour_label(s),
                            driver=s.team.driver_name,
                            team=s.team.name,
                            car_name=s.team.car_name,
                            defender_text=defender_text,
                            position=s.position,
                        ),
                        self._media_key("overtake", s.car_colour, defender_colour),
                    )
                    if lap == self.laps and s.position == 1 and old > 1:
                        s.last_minute_wins += 1
                        self._comment(
                            EventType.LAST_MINUTE_WIN,
                            lap,
                            self._line(
                                LAST_MINUTE_WIN_LINES,
                                car=self._colour_label(s),
                                driver=s.team.driver_name,
                                team=s.team.name,
                                car_name=s.team.car_name,
                            ),
                            self._media_key("finish_line", s.car_colour),
                        )
            leader = self.states[0]
            self._comment(
                EventType.LAP,
                lap,
                self._line(
                    LAP_LEADER_LINES,
                    lap=lap,
                    laps=self.laps,
                    car=self._colour_label(leader),
                    driver=leader.team.driver_name,
                    team=leader.team.name,
                    car_name=leader.team.car_name,
                ),
                self._media_key("lap_leader", leader.car_colour),
            )

        self._order_states()
        results: list[RaceResult] = []
        for idx, s in enumerate(self.states, start=1):
            points = POINTS_BY_POSITION.get(idx, 0)
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
                starting_damage=s.starting_damage,
                overtakes=s.overtakes,
                crashes=s.crashes,
                illegal_moves=s.illegal_moves,
                last_minute_wins=s.last_minute_wins,
                pit_stops=s.pit_stops,
                near_misses=s.near_misses,
            ))

        podium_states = self.states[:3]
        podium = results[:3]
        winner = podium_states[0]
        second_colour = podium_states[1].car_colour if len(podium_states) > 1 else None
        third_colour = podium_states[2].car_colour if len(podium_states) > 2 else None
        self._comment(
            EventType.FINISH,
            self.laps,
            self._line(
                FINISH_LINES,
                car=self._colour_label(winner),
                driver=winner.team.driver_name,
                team=results[0].team_name,
                car_name=winner.team.car_name,
                track=self.track.name,
            ),
            self._media_key("finish_line", winner.car_colour),
        )
        self._comment(
            EventType.PODIUM,
            self.laps,
            self._line(
                PODIUM_LINES,
                first=podium[0].team_name,
                second=podium[1].team_name if len(podium) > 1 else "-",
                third=podium[2].team_name if len(podium) > 2 else "-",
            ),
            self._media_key("podium", winner.car_colour, second_colour, third_colour),
        )
        return self.events, results, self.seed

    @staticmethod
    def events_to_dicts(events: list[RaceEvent]) -> list[dict]:
        return [asdict(e) for e in events]

    @staticmethod
    def results_to_dicts(results: list[RaceResult]) -> list[dict]:
        return [asdict(r) for r in results]
