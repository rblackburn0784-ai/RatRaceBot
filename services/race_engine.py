import math
import random
import re
import time
from dataclasses import asdict

from data.defaults import POINTS_BY_POSITION, TRACKS, WEATHER_CONDITIONS
from models.domain import RaceEvent, RaceResult, RaceState, Team
from models.enums import EventType
from services.builds import BuildService
from services.balance import (
    centered_driver,
    crew_effects,
    driver_foundation,
    effective_strain,
    soft_stat,
    track_part_adjustment,
    trait_effects,
)
from services.race_presentation_core import leaderboard_snapshot, phase_for_lap
from services.garage import crew_contributors
from services.sponsors import sponsor_by_key

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
        weather_key: str | None = None,
        rng_state: tuple | None = None,
        rivalry_heat_by_pair: dict[tuple[int, int], int] | None = None,
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
        rolled_weather_key = self.rng.choice(list(WEATHER_CONDITIONS))
        self.weather_key = weather_key if weather_key in WEATHER_CONDITIONS else rolled_weather_key
        self.weather = WEATHER_CONDITIONS[self.weather_key]
        if rng_state is not None:
            self.rng.setstate(rng_state)
        self.initial_rng_state = self.rng.getstate()
        self.events: list[RaceEvent] = []
        self.states: list[RaceState] = []
        self._car_stats_cache: dict[int, object] = {}
        self._crew_cache: dict[int, object] = {}
        self._trait_cache: dict[int, object] = {}
        self._strain_cache: dict[int, float] = {}
        self._pending_pit_events: list[tuple[RaceState, RaceEvent, int]] = []
        self.rivalry_heat_by_pair = {
            (min(int(first), int(second)), max(int(first), int(second))): min(100, max(0, int(heat)))
            for (first, second), heat in (rivalry_heat_by_pair or {}).items()
        }

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

    def _car_key(self, state: RaceState) -> str:
        return self._safe(state.team.archetype.name)

    def _event_car(self, state: RaceState) -> dict:
        return {
            "team_id": state.team.id or 0,
            "team_name": state.team.name,
            "driver_name": state.team.driver_name,
            "car_name": state.team.car_name,
            "car_key": self._car_key(state),
            "colour": state.car_colour,
        }

    def _event_reason(self, event_type: EventType, actor: RaceState | None) -> str | None:
        if actor is None:
            return None
        purpose = None
        if event_type == EventType.START:
            reason = "Launch pace is shaped by acceleration and Reflexes while the field is tightly packed."
            purpose = "start"
        elif event_type == EventType.OVERTAKE:
            reason = "Traffic pace, Aggression, Reflexes and spotter support helped create this passing chance."
            purpose = "overtake"
        elif event_type in {EventType.DAMAGE_MINOR, EventType.DAMAGE_MAJOR, EventType.DESTROYED}:
            reason = "Track hazards test Handling and Reflexes; durability, tyre condition and mechanical strain decide how costly the hit becomes."
            purpose = "hazard"
        elif event_type == EventType.PIT_STOP:
            reason = "Damage or tyre wear triggered the stop; Mechanics, pit-friendliness and specialist crew quality shape the recovery time."
            purpose = "pit"
        elif event_type in {EventType.ILLEGAL_MOVE, EventType.WARNING, EventType.DISQUALIFIED}:
            reason = "Aggressive racing can create opportunities but attracts official attention; Nerve helps keep the driver under control."
            purpose = "penalty"
        elif event_type == EventType.LAST_MINUTE_WIN:
            reason = "Late-race Nerve, remaining grip and momentum matter most when the finish is close."
            purpose = "finish"
        elif event_type in {EventType.FINISH, EventType.PODIUM}:
            reason = "The final order reflects the whole run: pace, reliability, tyre life, pit work and late-race composure."
            purpose = "finish"
        else:
            return None

        contributors = crew_contributors(actor.team, purpose) if purpose else []
        if contributors:
            reason += " Crew contribution: " + ", ".join(contributors) + "."
        sponsor = self._sponsor(actor.team)
        if sponsor:
            reason += f" Sponsor influence: {sponsor.name} — {sponsor.benefit_text} Trade-off: {sponsor.drawback_text}"
        return reason

    def _comment(
        self,
        event_type: EventType,
        lap: int,
        message: str,
        media_key: str | None = None,
        actor: RaceState | None = None,
        target: RaceState | None = None,
        participants: list[RaceState] | None = None,
        context: dict | None = None,
    ) -> RaceEvent:
        event_context = dict(context or {})
        rivalry_heat = self._rivalry_heat(actor, target)
        if rivalry_heat:
            event_context.setdefault("rivalry_heat", rivalry_heat)
        if rivalry_heat >= 70 and event_type in {EventType.OVERTAKE, EventType.ILLEGAL_MOVE}:
            message = f"🔥 Rivalry boiling over ({rivalry_heat}): {message}"
        elif rivalry_heat >= 50 and event_type in {EventType.OVERTAKE, EventType.ILLEGAL_MOVE}:
            message = f"🔥 Rivalry watch ({rivalry_heat}): {message}"
        event_context.setdefault("phase", phase_for_lap(lap, self.laps))
        event_context.setdefault("laps", self.laps)
        if actor:
            sponsor = self._sponsor(actor.team)
            if sponsor:
                event_context.setdefault("sponsor", sponsor.name)
        reason = self._event_reason(event_type, actor)
        if reason:
            event_context.setdefault("why", reason)
        if actor:
            purpose_map = {
                EventType.START: "start",
                EventType.OVERTAKE: "overtake",
                EventType.DAMAGE_MINOR: "hazard",
                EventType.DAMAGE_MAJOR: "hazard",
                EventType.DESTROYED: "hazard",
                EventType.PIT_STOP: "pit",
                EventType.ILLEGAL_MOVE: "penalty",
                EventType.WARNING: "penalty",
                EventType.DISQUALIFIED: "penalty",
                EventType.LAST_MINUTE_WIN: "finish",
                EventType.FINISH: "finish",
                EventType.PODIUM: "finish",
            }
            purpose = purpose_map.get(event_type)
            if purpose:
                contributors = crew_contributors(actor.team, purpose)
                if contributors:
                    event_context.setdefault("crew_contributors", contributors)
        event = RaceEvent(
            event_type=event_type,
            lap=lap,
            message=message,
            media_key=media_key or event_type.value,
            audio_key=event_type.value,
            actor=self._event_car(actor) if actor else None,
            target=self._event_car(target) if target else None,
            participants=[self._event_car(state) for state in participants] if participants else [],
            context=event_context,
        )
        self.events.append(event)
        return event

    def _colour_label(self, state: RaceState) -> str:
        emoji = COLOUR_EMOJIS.get(state.car_colour, "🏎️")
        return f"{emoji} {state.car_colour.title()}"

    def _assign_colours(self) -> None:
        colours = list(CAR_COLOURS)
        self.rng.shuffle(colours)
        for state, colour in zip(self.states, colours):
            state.car_colour = colour

    def _rivalry_heat(self, first: RaceState | None, second: RaceState | None) -> int:
        if first is None or second is None or first.team.id is None or second.team.id is None:
            return 0
        key = (min(int(first.team.id), int(second.team.id)), max(int(first.team.id), int(second.team.id)))
        return min(100, max(0, int(self.rivalry_heat_by_pair.get(key, 0))))

    def _rival_for(self, state: RaceState) -> RaceState | None:
        rivals = [s for s in self.states if s is not state and not s.dnf and not s.disqualified]
        if not rivals:
            return None
        hot = [
            rival for rival in rivals
            if self._rivalry_heat(state, rival) >= 50 and abs(rival.position - state.position) <= 2
        ]
        if hot:
            return max(hot, key=lambda rival: (self._rivalry_heat(state, rival), -abs(rival.position - state.position)))
        return min(rivals, key=lambda s: abs(s.position - state.position))

    def _team_cache_key(self, team: Team) -> int:
        return id(team)

    def _crew_effects(self, team: Team):
        key = self._team_cache_key(team)
        if key not in self._crew_cache:
            self._crew_cache[key] = crew_effects(team)
        return self._crew_cache[key]

    def _trait_effects(self, team: Team):
        key = self._team_cache_key(team)
        if key not in self._trait_cache:
            self._trait_cache[key] = trait_effects(team, self.track, self.weather)
        return self._trait_cache[key]

    def _sponsor(self, team: Team):
        return sponsor_by_key(getattr(team, "active_sponsor_key", None))

    def _effective_strain(self, team: Team) -> float:
        key = self._team_cache_key(team)
        if key not in self._strain_cache:
            self._strain_cache[key] = effective_strain(team, self._crew_effects(team).repair)
        return self._strain_cache[key]

    def _track_adjusted_car_stats(self, team: Team):
        key = self._team_cache_key(team)
        if key not in self._car_stats_cache:
            self._car_stats_cache[key] = BuildService.clamp_car_stats(
                BuildService.effective_car_stats(team)
                + self.track.modifiers
                + self.weather.modifiers
                + track_part_adjustment(team, self.track, self.weather)
            )
        return self._car_stats_cache[key]

    def _surface_roughness(self) -> int:
        return max(0, self.track.surface_roughness + self.weather.surface_roughness_delta)

    def _hazard_rate(self) -> int:
        return max(1, self.track.hazard_rate + self.weather.hazard_rate_delta)

    def _pit_difficulty(self) -> int:
        return max(0, self.track.pit_difficulty + self.weather.pit_difficulty_delta)

    def _pace_score(self, state: RaceState) -> float:
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        crew = self._crew_effects(state.team)
        traits = self._trait_effects(state.team)
        strain = self._effective_strain(state.team)
        sponsor = self._sponsor(state.team)

        straight = self.track.straight_bias / 6.0
        corner = self.track.corner_difficulty / 6.0
        rough = self._surface_roughness() / 6.0

        # Diminishing returns keep extreme hardware useful without allowing a
        # fully stacked build to become an unbeatable stat wall.
        car_pace = (
            soft_stat(car.speed) * (0.90 + 0.80 * straight)
            + soft_stat(car.acceleration) * (0.82 + 0.25 * (1.0 - straight))
            + soft_stat(car.handling) * (0.72 + 0.75 * corner)
            + soft_stat(car.braking) * (0.28 + 0.48 * corner)
            + soft_stat(car.durability) * (0.10 + 0.35 * rough)
            + soft_stat(car.reliability) * 0.30
            + soft_stat(car.intimidation) * 0.08
        )

        # Every driver point contributes to a common concave skill foundation.
        # Role-specific bonuses are intentionally smaller so 24-point min/max
        # builds remain close to balanced drivers over a complete championship.
        driver_pace = driver_foundation(drv) * 0.92
        driver_pace += centered_driver(drv.handling) * (0.36 + 0.40 * corner)
        driver_pace += centered_driver(drv.reflexes) * 0.36
        driver_pace += centered_driver(drv.nerve) * 0.30
        driver_pace += centered_driver(drv.mechanics) * (0.10 + min(0.52, strain * 0.050))
        driver_pace += centered_driver(drv.aggression) * 0.27
        driver_pace += centered_driver(drv.showmanship) * 0.28

        # Aggression produces legal attacking pace as well as a separate chance
        # of attracting warnings; Showmanship can generate momentum but asks more
        # of the tyres. Neither is a free dump/stat.
        attack_chance = max(5.0, min(45.0, 9.0 + drv.aggression * 3.2 + max(0.0, car.intimidation) * 1.0 + crew.attack_support * 2.0 + traits.attack * 2.0))
        attack_bonus = 0.0
        if self._roll(100) <= attack_chance:
            attack_bonus = 0.65 + max(0.0, centered_driver(drv.aggression)) * 0.55 + max(0.0, car.intimidation - 2) * 0.10

        show_bonus = 0.0
        if self._roll(100) <= 7 + drv.showmanship * 2.8:
            show_bonus = 0.45 + max(0.0, centered_driver(drv.showmanship)) * 0.35

        late_bonus = traits.late_race if state.lap >= max(1, self.laps - 2) else 0.0
        sponsor_pace = 0.0
        if sponsor:
            sponsor_pace += sponsor.opening_pace_bonus if state.lap <= 2 else 0.0
            sponsor_pace -= sponsor.pace_penalty
        heat_after_crew = car.heat - crew.heat_control
        heat_penalty = max(0.0, soft_stat(heat_after_crew)) * 0.34
        strain_penalty = strain * 0.18
        damage_penalty = state.damage * 0.075
        tyre_penalty = state.tyre_wear * 0.055

        return (
            self._roll(20)
            + car_pace
            + driver_pace
            + crew.strategy * 0.42
            + crew.spotting * 0.16
            + traits.pace
            + late_bonus
            + attack_bonus
            + show_bonus
            + state.momentum * 0.55
            + sponsor_pace
            - heat_penalty
            - strain_penalty
            - damage_penalty
            - tyre_penalty
            - self._surface_roughness() * 0.22
        )

    def _lap_time(self, state: RaceState, pace: float) -> float:
        base = 82.0 + self.track.corner_difficulty * 2.1 - self.track.straight_bias * 1.55
        # High Nerve reduces inconsistency rather than simply adding raw pace.
        variance_span = max(1.25, 3.2 - state.team.stats.nerve * 0.18)
        variance = self.rng.uniform(-variance_span, variance_span + 0.7)
        raw = base - pace * 0.43 + variance

        # Smooth asymptotic floor: there is no hard 48-second cliff. Additional
        # performance always helps, but returns become progressively smaller.
        soft_floor = 42.0
        delta = raw - soft_floor
        if delta > 30:
            time_delta = raw
        elif delta < -30:
            time_delta = soft_floor + math.exp(delta)
        else:
            time_delta = soft_floor + math.log1p(math.exp(delta))
        if state.dnf or state.disqualified:
            return 9999.0
        return time_delta

    def _maybe_hazard(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified:
            return
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        crew = self._crew_effects(state.team)
        traits = self._trait_effects(state.team)
        strain = self._effective_strain(state.team)
        sponsor = self._sponsor(state.team)
        heat_after_crew = max(0.0, car.heat - crew.heat_control) + (sponsor.heat_pressure if sponsor else 0.0)
        chance = (
            self._hazard_rate()
            + max(0, state.tyre_wear - 50) * 0.10
            + max(0, state.damage - 40) * 0.08
            + heat_after_crew * 0.45
            + strain * 0.16
            - soft_stat(car.reliability) * 0.55
            - centered_driver(drv.reflexes) * 0.75
            - centered_driver(drv.nerve) * 0.35
            - crew.spotting * 0.55
            - crew.repair * 0.18
            - traits.hazard_save * 0.55
        )
        chance = max(3.0, min(55.0, chance))
        if self._roll(100) <= chance:
            hazard = self.rng.choice(self.track.hazard_names)
            save = (
                self._roll(20)
                + soft_stat(car.handling) * 0.62
                + soft_stat(car.braking) * 0.34
                + drv.handling * 0.45
                + drv.reflexes * 0.55
                + drv.nerve * 0.18
                + crew.spotting * 0.70
                + traits.hazard_save
                + (sponsor.hazard_save_bonus if sponsor else 0.0)
                - self.track.corner_difficulty * 0.55
            )
            if save >= 18.0:
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
                    actor=state,
                )
            elif save >= 11.0:
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
                    actor=state,
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
                    actor=state,
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
                        actor=state,
                    )

    def _maybe_illegal_move(self, state: RaceState, lap: int) -> None:
        if state.dnf or state.disqualified:
            return
        car = self._track_adjusted_car_stats(state.team)
        drv = state.team.stats
        crew = self._crew_effects(state.team)
        traits = self._trait_effects(state.team)
        rival = self._rival_for(state)
        rivalry_heat = self._rivalry_heat(state, rival)
        dirty_chance = (
            0.8
            + max(0, drv.aggression - 3) * 1.35
            + max(0.0, car.intimidation - 4) * 0.35
            + max(0.0, traits.illegal_risk)
            - drv.nerve * 0.28
            - max(0.0, crew.strategy) * 0.20
        )
        # Rivalries are flavour first. Even at 100 heat the extra illegal-contact
        # pressure is capped below one percentage point, so it cannot overwhelm build skill.
        if rivalry_heat >= 50:
            dirty_chance += min(0.8, rivalry_heat / 125.0)
        dirty_chance = max(0.2, min(18.8, dirty_chance))
        if self._roll(100) <= dirty_chance:
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
                actor=state,
                target=rival,
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
                    actor=state,
                )

    def _maybe_illegal_scrutineering(self, state: RaceState) -> None:
        risk = BuildService.illegal_disqualification_risk_percent(state.team)
        sponsor = self._sponsor(state.team)
        if risk > 0 and sponsor:
            risk += sponsor.illegal_scrutiny_bonus
        risk = min(95, risk)
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
                actor=state,
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
        crew = self._crew_effects(state.team)
        traits = self._trait_effects(state.team)
        strain = self._effective_strain(state.team)
        sponsor = self._sponsor(state.team)
        state.pit_stops += 1
        position_before = state.position
        damage_before = state.damage
        tyres_before = state.tyre_wear
        pit_bonus = (
            drv.mechanics * 0.72
            + soft_stat(car.pit_friendliness) * 0.58
            + soft_stat(car.reliability) * 0.20
            + crew.pit_bonus
            + crew.repair * 0.45
            + traits.pit_bonus
            - strain * 0.12
        )
        pit_bonus = max(-5.0, min(13.0, pit_bonus))
        pit_roll = self._roll(20) + pit_bonus - self._pit_difficulty()
        time_cost = 9.5 + self._pit_difficulty() + strain * 0.08 + self.rng.uniform(0, 5.5)
        if sponsor and sponsor.pit_time_variance:
            time_cost += self.rng.uniform(-sponsor.pit_time_variance, sponsor.pit_time_variance + 1.0)
        media_key = self._media_key("pit_stop", state.car_colour)
        if pit_roll >= 22:
            fixed = self.rng.randint(22, 38) + (sponsor.pit_repair_bonus if sponsor else 0)
            tyres = self.rng.randint(35, 55)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            actual_cost = time_cost
            state.total_time += actual_cost
            event = self._comment(
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
                actor=state,
                context={"pit_quality": "Fast", "time_cost": round(actual_cost, 2)},
            )
        elif pit_roll >= 12:
            fixed = self.rng.randint(10, 24) + (sponsor.pit_repair_bonus if sponsor else 0)
            tyres = self.rng.randint(20, 40)
            state.damage = max(0, state.damage - fixed)
            state.tyre_wear = max(0, state.tyre_wear - tyres)
            actual_cost = time_cost + 4
            state.total_time += actual_cost
            event = self._comment(
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
                actor=state,
                context={"pit_quality": "Solid", "time_cost": round(actual_cost, 2)},
            )
        else:
            fixed = self.rng.randint(0, 10) + ((sponsor.pit_repair_bonus // 2) if sponsor else 0)
            state.damage = max(0, state.damage - fixed)
            actual_cost = time_cost + 12
            state.total_time += actual_cost
            event = self._comment(
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
                actor=state,
                context={"pit_quality": "Botched", "time_cost": round(actual_cost, 2)},
            )
        event.context.update(
            {
                "position_before": position_before,
                "damage_before": damage_before,
                "damage_after": state.damage,
                "tyres_before": tyres_before,
                "tyres_after": state.tyre_wear,
                "strategic_stop": bool(strategic and not needs_pit),
            }
        )
        self._pending_pit_events.append((state, event, position_before))

    def _order_states(self) -> None:
        # Classification rule: finishers/running cars first, then DNFs, then DSQs.
        # A disqualification always outranks the DNF flag for classification purposes.
        running = [s for s in self.states if not s.dnf and not s.disqualified]
        dnfs = [s for s in self.states if s.dnf and not s.disqualified]
        disqualified = [s for s in self.states if s.disqualified]
        running.sort(key=lambda s: (-s.lap, s.total_time))
        dnfs.sort(key=lambda s: (-s.lap, s.total_time))
        disqualified.sort(key=lambda s: (-s.lap, s.total_time))
        self.states = running + dnfs + disqualified
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
            f"{f' — “{s.team.intro_phrase}”' if s.team.intro_phrase else ''}"
            for s in self.states
        )
        self._comment(
            EventType.START,
            0,
            self._line(
                START_LINES,
                count=len(self.states),
                laps=self.laps,
                track=f"{self.track.name} under {self.weather.name}",
                colour_lines=colour_lines,
            ),
            "start",
            participants=self.states,
        )

        for state in list(self.states):
            self._maybe_illegal_scrutineering(state)

        for lap in range(1, self.laps + 1):
            if not any(not s.dnf and not s.disqualified for s in self.states):
                break
            for state in list(self.states):
                if state.dnf or state.disqualified:
                    continue
                lap_start_time = state.total_time
                pace = self._pace_score(state)
                lap_time = self._lap_time(state, pace)
                state.total_time += lap_time
                state.lap = lap
                car = self._track_adjusted_car_stats(state.team)
                drv = state.team.stats
                crew = self._crew_effects(state.team)
                traits = self._trait_effects(state.team)
                strain = self._effective_strain(state.team)
                sponsor = self._sponsor(state.team)

                tyre_change = (
                    self._surface_roughness() * 0.62
                    + self.rng.randint(1, 4)
                    - soft_stat(car.handling) * 0.22
                    + strain * 0.10
                    + max(0, drv.aggression - 4) * 0.15
                    + max(0, drv.showmanship - 5) * 0.08
                    - crew.tyre_care * 0.35
                    - traits.tyre_care * 0.45
                    + (sponsor.tyre_wear_pressure if sponsor else 0.0)
                )
                state.tyre_wear += max(1, int(round(tyre_change)))

                heat_after_crew = max(0.0, car.heat - crew.heat_control) + (sponsor.heat_pressure if sponsor else 0.0)
                damage_change = (
                    self._surface_roughness() * 0.28
                    + self.rng.uniform(0.0, 1.7)
                    + heat_after_crew * 0.14
                    + strain * 0.075
                    - soft_stat(car.durability) * 0.16
                    - max(0, drv.mechanics - 4) * 0.08
                    - max(0.0, crew.repair) * 0.10
                )
                state.damage += max(0, int(round(damage_change)))

                momentum_delta = self.rng.choice([-1, 0, 0, 0, 1])
                if self._roll(100) <= 5 + drv.showmanship * 2.4 + (sponsor.momentum_chance_bonus if sponsor else 0.0):
                    momentum_delta += 1
                    state.tyre_wear += 1
                if lap >= self.laps - 1 and self._roll(100) <= 7 + drv.nerve * 2.0:
                    momentum_delta += 1
                state.momentum = max(-3, min(4, state.momentum + momentum_delta))
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
                        actor=state,
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
                        actor=state,
                    )

                # A fastest lap is the complete elapsed lap, including any pit-lane
                # time added during this lap. Failed cars are excluded from timing
                # records later, but keeping their state deterministic aids replay.
                completed_lap_time = state.total_time - lap_start_time
                state.fastest_lap = (
                    completed_lap_time
                    if state.fastest_lap is None
                    else min(state.fastest_lap, completed_lap_time)
                )

            previous = {s.team.id: s.position for s in self.states}
            previous_order = list(self.states)
            self._order_states()
            for pit_state, pit_event, position_before in list(self._pending_pit_events):
                if pit_event.lap != lap:
                    continue
                position_after = pit_state.position
                delta = position_before - position_after
                pit_event.context["position_after"] = position_after
                pit_event.context["position_delta"] = delta
                if delta > 0:
                    pit_event.context["pit_position_text"] = f"gained {delta} place(s) through the pit cycle"
                elif delta < 0:
                    pit_event.context["pit_position_text"] = f"lost {abs(delta)} place(s) through the pit cycle"
                else:
                    pit_event.context["pit_position_text"] = "held position through the pit cycle"
            self._pending_pit_events = [item for item in self._pending_pit_events if item[1].lap != lap]
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
                        actor=s,
                        target=defender if defender and defender is not s else None,
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
                            actor=s,
                        )
            running_leaders = [state for state in self.states if not state.dnf and not state.disqualified]
            if running_leaders:
                leader = running_leaders[0]
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
                    actor=leader,
                    context={"leaderboard": leaderboard_snapshot(self.states, self.laps)},
                )

        self._order_states()
        results: list[RaceResult] = []
        for idx, s in enumerate(self.states, start=1):
            official_finisher = not s.dnf and not s.disqualified and s.lap >= self.laps
            # v0.4.2: only official finishers score championship points. DNFs and DSQs score zero.
            points = POINTS_BY_POSITION.get(idx, 0) if official_finisher else 0
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
                last_minute_wins=s.last_minute_wins if official_finisher else 0,
                pit_stops=s.pit_stops,
                near_misses=s.near_misses,
                fastest_lap=s.fastest_lap,
            ))

        finisher_states = [s for s in self.states if not s.dnf and not s.disqualified and s.lap >= self.laps]
        finisher_results = [r for r in results if not r.dnf and not r.disqualified and r.laps_completed >= self.laps]
        if finisher_states:
            podium_states = finisher_states[:3]
            podium = finisher_results[:3]
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
                    team=podium[0].team_name,
                    car_name=winner.team.car_name,
                    track=self.track.name,
                ),
                self._media_key("finish_line", winner.car_colour),
                actor=winner,
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
                participants=podium_states,
            )
        else:
            self._comment(
                EventType.FINISH,
                self.laps,
                f"{self.track.name} ends without an official finisher. No winner or podium is awarded.",
                "finish_line",
            )
        return self.events, results, self.seed

    @staticmethod
    def events_to_dicts(events: list[RaceEvent]) -> list[dict]:
        return [asdict(e) for e in events]

    @staticmethod
    def results_to_dicts(results: list[RaceResult]) -> list[dict]:
        return [asdict(r) for r in results]
