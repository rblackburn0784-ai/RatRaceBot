from dataclasses import dataclass
import json

import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import CAR_DEFINITIONS, CREW_MEMBERS, PARTS, TRACKS
from models.domain import Team
from models.enums import CarArchetype, CrewSlot, PartSlot
from models.stats import DriverStats
from services.access import deny_admin_only, is_admin
from services.audit import audit_log
from services.builds import BuildService, ILLEGAL_PART_DISQUALIFICATION_RISK
from services.garage import (
    SETUP_PRESETS,
    compare_part,
    comparison_rating_lines,
    crew_chief_advice,
    crew_role_summary,
    crew_roster_lines,
    equipped_part_rows,
    normalized_parts,
    saved_setup_summary,
    setup_rating_lines,
    stars,
)
from services.crew_sheet import render_crew_sheet
from services.engagement import available_titles_for_level, level_for_xp, progress_embed, sponsor_offers_embed, track_records_embed
from services.progression import LIVERIES, EMBLEMS, GARAGE_DECOR, unlocked_options, unlocked_setup_names, crew_unlocked, crew_required_level
from services.sponsors import sponsor_by_key
from services.formatting import Embeds
from services.garage_sheet import render_parts_sheet
from services.scrutineering import scrutineering_embed
from services.story import hall_of_fame_embed, reputation_embed, rivalries_embed
from services.team_sheet import render_team_sheet
from services.views import ConfirmView, PaginatedTextView
from services.ui_safety import ReliableModal, ReliableView


STAT_CHOICES = [app_commands.Choice(name=str(i), value=i) for i in range(1, 9)]
TRACK_CHOICES = [
    app_commands.Choice(name=f"{track.name} ({key})", value=key)
    for key, track in list(TRACKS.items())[:25]
]

DRIVER_STAT_LABELS = (
    ("Nerve", "nerve"),
    ("Handling", "handling"),
    ("Aggression", "aggression"),
    ("Mechanics", "mechanics"),
    ("Reflexes", "reflexes"),
    ("Showmanship", "showmanship"),
)


def _shorten(value: str, limit: int = 100) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _part_label(key: str) -> str:
    part = PARTS[key]
    if BuildService.is_illegal_part_key(key):
        clean_name = part.name.removeprefix("ILLEGAL ").strip()
        return f"ILLEGAL (+{ILLEGAL_PART_DISQUALIFICATION_RISK}% DSQ) - {clean_name}"
    return part.name


def _part_description(key: str) -> str:
    prefix = f"Warning: +{ILLEGAL_PART_DISQUALIFICATION_RISK}% disqualification risk. " if BuildService.is_illegal_part_key(key) else ""
    return _shorten(f"{prefix}{PARTS[key].description}")


def _crew_label(key: str) -> str:
    return CREW_MEMBERS[key].name


def _crew_description(key: str) -> str:
    return _shorten(CREW_MEMBERS[key].description)


def _garage_embed(team: Team, setup_rows=(), level: int = 1) -> discord.Embed:
    saved = saved_setup_summary(setup_rows)
    part_lines = []
    for slot, key in equipped_part_rows(team):
        label = PARTS[key].name if key in PARTS else "Empty"
        part_lines.append(f"**{slot.value.title()}:** {label}")
    unlocked_presets = set(unlocked_setup_names(level))
    preset_lines = []
    for name in SETUP_PRESETS:
        if name in unlocked_presets:
            state = 'Saved' if name in saved else 'Empty'
        elif name in saved:
            state = 'Saved (legacy unlock)'
        else:
            state = 'Locked'
        preset_lines.append(f"**{name}:** {state}")
    illegal = BuildService.illegal_disqualification_risk_percent(team)
    embed = discord.Embed(
        title=f"🔧 THE GARAGE — {team.name}",
        description=f"**Car:** {team.car_name} · {team.archetype.value}\n**Driver:** {team.driver_name}",
        color=discord.Color.dark_gold(),
    )
    embed.add_field(
        name="Build Condition",
        value=(
            f"Team Level: **{level}**\n"
            f"Tuning Efficiency: **{BuildService.tuning_efficiency(team) * 100:.0f}%**\n"
            f"Mechanical Strain: **{BuildService.build_strain(team)} — {BuildService.build_strain_label(team)}**\n"
            f"Illegal Hardware Risk: **{illegal}%**"
        ),
        inline=False,
    )
    embed.add_field(name="Installed Hardware", value="\n".join(part_lines)[:1024], inline=True)
    embed.add_field(name="Estimated Setup", value="\n".join(setup_rating_lines(team)), inline=True)
    embed.add_field(name="Pit Crew", value="\n".join(crew_roster_lines(team))[:1024], inline=False)
    sponsor = sponsor_by_key(team.active_sponsor_key)
    embed.add_field(
        name="Team Identity",
        value=(
            f"Livery: **{_identity_name(LIVERIES, team.livery_key, team.livery_key)}**\n"
            f"Emblem: **{_identity_name(EMBLEMS, team.emblem_key, team.emblem_key)}**\n"
            f"Garage: **{_identity_name(GARAGE_DECOR, team.garage_decor_key, team.garage_decor_key)}**\n"
            f"Sponsor: **{sponsor.name if sponsor else 'Independent'}**"
        ),
        inline=False,
    )
    embed.add_field(name="Saved Setups", value=" · ".join(preset_lines)[:1024], inline=False)
    embed.set_footer(text="Parts are strategic trade-offs. Saved setups change hardware only; your crew stays with the team.")
    return embed


def _part_comparison_embed(team: Team, candidate_key: str) -> discord.Embed:
    comparison = compare_part(team, candidate_key)
    candidate = PARTS[candidate_key]
    current = PARTS.get(comparison.current_key) if comparison.current_key else None
    mods = [f"{key.replace('_', ' ').title()} {value:+d}" for key, value in candidate.modifiers.as_dict().items() if value]
    embed = discord.Embed(
        title=f"🔩 Part Comparison — {comparison.slot.value.title()}",
        description=f"**{current.name if current else 'Empty slot'}** → **{candidate.name}**",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Candidate Trade-off", value=f"{candidate.description}\n" + (", ".join(mods) or "No raw stat change"), inline=False)
    embed.add_field(name="Estimated Setup Change", value="\n".join(comparison_rating_lines(comparison)), inline=False)
    embed.add_field(
        name="Build Cost",
        value=(
            f"Strain: **{comparison.before_strain} → {comparison.after_strain}**\n"
            f"Tuning: **{comparison.before_tuning}% → {comparison.after_tuning}%**\n"
            f"DSQ risk: **{comparison.before_illegal_risk}% → {comparison.after_illegal_risk}%**"
        ),
        inline=False,
    )
    return embed


def _crew_chief_advice_embed(team: Team) -> discord.Embed:
    advice = crew_chief_advice(team)
    chief_key = team.crew.get(CrewSlot.CREW_CHIEF.value)
    chief = CREW_MEMBERS.get(chief_key)
    chief_name = chief.name if chief else "Unassigned Pit Wall"
    embed = discord.Embed(
        title=f"🧢 {chief_name} — {team.name}",
        description="Setup advice based on the car you have now. No hidden formulas—just what the crew sees in the garage.",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Current Read", value="\n".join(setup_rating_lines(team)), inline=False)
    embed.add_field(name="Pit Wall Notes", value="\n".join(advice)[:1024], inline=False)
    return embed


def _setup_manager_embed(team: Team, setup_rows, selected: str, mode: str) -> discord.Embed:
    saved = saved_setup_summary(setup_rows)
    lines = []
    for name in SETUP_PRESETS:
        parts = saved.get(name)
        if parts is None:
            lines.append(f"**{name}:** Empty")
        else:
            lines.append(f"**{name}:** {len(parts)} part(s) saved")
    action = "Save the car's current hardware into a preset." if mode == "save" else "Load a preset and replace the car's current hardware."
    embed = discord.Embed(title=f"Garage Setups — {team.name}", description=action, color=discord.Color.dark_teal())
    embed.add_field(name="Preset Bays", value="\n".join(lines), inline=False)
    embed.add_field(name="Selected", value=f"**{selected}**", inline=True)
    embed.add_field(name="Current Car", value=f"{len(BuildService.equipped_parts_by_slot(team))}/8 parts · {BuildService.build_strain(team)} strain", inline=True)
    return embed


def _ready_marker(value: object) -> str:
    return "Ready" if value else "Needed"


def _driver_stats_text(stats: DriverStats | None) -> str:
    if not stats:
        return (
            "Not set yet.\n"
            "Use the six dropdowns for Nerve, Handling, Aggression, Mechanics, Reflexes and Showmanship.\n"
            "Each stat can be 1-8. Total budget: 24."
        )

    lines = [
        f"**{label}:** {getattr(stats, attr)}"
        for label, attr in DRIVER_STAT_LABELS
    ]
    return "\n".join(lines[:3]) + "\n" + "\n".join(lines[3:]) + f"\n**Total:** {stats.total}/24"


def _team_identity_text(state: "TeamWizardState") -> str:
    return (
        f"**Team:** {state.name or 'Not set'}\n"
        f"**Driver:** {state.driver or 'Not set'}\n"
        f"**Pit Crew:** {state.pit_crew or 'Not set'}\n"
        f"**Rod:** {state.car_name or 'Not set'}"
    )


def _car_type_text(car_type: CarArchetype | None) -> str:
    if not car_type:
        return "Not selected yet."
    definition = CAR_DEFINITIONS[car_type.value]
    return f"**{car_type.value}**\n{definition.description}"


def _setup_progress_text(state: "TeamWizardState") -> str:
    details_ready = all((state.name, state.driver, state.pit_crew, state.car_name))
    return (
        f"Team details: **{_ready_marker(details_ready)}**\n"
        f"Car type: **{_ready_marker(state.car_type)}**\n"
        f"Driver stats: **{_ready_marker(state.stats)}**"
    )


@dataclass
class TeamWizardState:
    name: str | None = None
    driver: str | None = None
    pit_crew: str | None = None
    car_name: str | None = None
    car_type: CarArchetype | None = None
    stats: DriverStats | None = None

    @property
    def ready(self) -> bool:
        return all((self.name, self.driver, self.pit_crew, self.car_name, self.car_type, self.stats))


class CarTypeSelect(discord.ui.Select):
    def __init__(self, wizard: "TeamWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(
                label=car.value,
                value=car.value,
                description=CAR_DEFINITIONS[car.value].description[:100],
                default=wizard.state.car_type == car,
            )
            for car in CarArchetype
        ]
        super().__init__(placeholder="Choose a car archetype", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.state.car_type = CarArchetype(self.values[0])
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.wizard.refresh(interaction)


class TeamDetailsModal(ReliableModal):
    def __init__(self, wizard: "TeamWizardView"):
        super().__init__(title="Team Details")
        self.wizard = wizard
        self.name_input = discord.ui.TextInput(
            label="Team name",
            default=wizard.state.name or "",
            max_length=60,
        )
        self.driver_input = discord.ui.TextInput(
            label="Driver name",
            default=wizard.state.driver or "",
            max_length=60,
        )
        self.pit_crew_input = discord.ui.TextInput(
            label="Pit crew name",
            default=wizard.state.pit_crew or "",
            max_length=60,
        )
        self.car_name_input = discord.ui.TextInput(
            label="Rod name",
            default=wizard.state.car_name or "",
            max_length=60,
        )
        self.add_item(self.name_input)
        self.add_item(self.driver_input)
        self.add_item(self.pit_crew_input)
        self.add_item(self.car_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        values = [
            str(self.name_input.value).strip(),
            str(self.driver_input.value).strip(),
            str(self.pit_crew_input.value).strip(),
            str(self.car_name_input.value).strip(),
        ]
        if not all(values):
            await interaction.response.send_message("Every team detail needs a value.", ephemeral=True)
            return

        self.wizard.state.name, self.wizard.state.driver, self.wizard.state.pit_crew, self.wizard.state.car_name = values
        await self.wizard.refresh(interaction)


class DriverStatSelect(discord.ui.Select):
    def __init__(self, view: "DriverStatsView", label: str, attr: str, row: int):
        self.stats_view = view
        self.attr = attr
        current = int(view.values[attr])
        other_total = view.total - current
        max_allowed = max(1, min(8, 24 - other_total))
        options = [
            discord.SelectOption(
                label=str(value),
                value=str(value),
                default=value == current,
            )
            for value in range(1, max_allowed + 1)
        ]
        super().__init__(
            placeholder=f"{label}: {current}",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        self.stats_view.values[self.attr] = int(self.values[0])
        self.stats_view.rebuild_items()
        await interaction.response.edit_message(embed=self.stats_view.embed(), view=self.stats_view)


class DriverStatsView(ReliableView):
    PAGE_STATS = (
        DRIVER_STAT_LABELS[:3],
        DRIVER_STAT_LABELS[3:],
    )

    def __init__(self, wizard: "TeamWizardView"):
        super().__init__(timeout=600)
        self.wizard = wizard
        self.page = 0
        if wizard.state.stats:
            self.values = {
                attr: int(getattr(wizard.state.stats, attr))
                for _label, attr in DRIVER_STAT_LABELS
            }
        else:
            self.values = {attr: 4 for _label, attr in DRIVER_STAT_LABELS}
        self.rebuild_items()

    @property
    def total(self) -> int:
        return sum(int(self.values[attr]) for _label, attr in DRIVER_STAT_LABELS)

    @property
    def remaining(self) -> int:
        return max(0, 24 - self.total)

    def embed(self) -> discord.Embed:
        page_title = "Driving Style" if self.page == 0 else "Technical & Flair"
        embed = discord.Embed(
            title=f"Driver Stats — {page_title}",
            description=(
                "Choose each stat from the dropdowns. Values are limited to **1–8** and "
                "choices that would push the driver over the **24-point budget** are not offered."
            ),
            color=discord.Color.blurple(),
        )
        lines = [
            f"**{label}:** {self.values[attr]}"
            for label, attr in DRIVER_STAT_LABELS
        ]
        embed.add_field(
            name="Current Driver",
            value="\n".join(lines),
            inline=True,
        )
        embed.add_field(
            name="Budget",
            value=(
                f"Used: **{self.total}/24**\n"
                f"Remaining: **{self.remaining}**\n"
                f"Page: **{self.page + 1}/2**"
            ),
            inline=True,
        )
        embed.set_footer(
            text="At 24/24, lower one stat before increasing another. Balanced resets everything to 4."
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.wizard.owner_id:
            return True
        await interaction.response.send_message("This driver-stat builder belongs to another driver.", ephemeral=True)
        return False

    def rebuild_items(self) -> None:
        self.clear_items()
        for row, (label, attr) in enumerate(self.PAGE_STATS[self.page]):
            self.add_item(DriverStatSelect(self, label, attr, row))

        previous = discord.ui.Button(
            label="Previous",
            style=discord.ButtonStyle.secondary,
            row=3,
            disabled=self.page == 0,
        )
        previous.callback = self.previous_page
        self.add_item(previous)

        next_button = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.primary,
            row=3,
            disabled=self.page == 1,
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

        balanced = discord.ui.Button(
            label="Balanced 4s",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        balanced.callback = self.reset_balanced
        self.add_item(balanced)

        save = discord.ui.Button(
            label="Save Stats",
            style=discord.ButtonStyle.success,
            row=3,
        )
        save.callback = self.save_stats
        self.add_item(save)

        cancel = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            row=3,
        )
        cancel.callback = self.cancel
        self.add_item(cancel)

    async def previous_page(self, interaction: discord.Interaction):
        self.page = 0
        self.rebuild_items()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page = 1
        self.rebuild_items()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def reset_balanced(self, interaction: discord.Interaction):
        self.values = {attr: 4 for _label, attr in DRIVER_STAT_LABELS}
        self.rebuild_items()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def save_stats(self, interaction: discord.Interaction):
        stats = DriverStats(
            *(int(self.values[attr]) for _label, attr in DRIVER_STAT_LABELS)
        )
        stats.validate()
        self.wizard.state.stats = stats
        self.wizard.update_controls()
        await interaction.response.edit_message(embed=self.wizard.embed(), view=self.wizard)

    async def cancel(self, interaction: discord.Interaction):
        self.wizard.update_controls()
        await interaction.response.edit_message(embed=self.wizard.embed(), view=self.wizard)


class TeamWizardView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.state = TeamWizardState()
        self.car_select = CarTypeSelect(self)
        self.add_item(self.car_select)
        self.update_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This team wizard belongs to someone else.", ephemeral=True)
        return False

    def update_controls(self) -> None:
        self.create_team.disabled = not self.state.ready

    def embed(self) -> discord.Embed:
        state = self.state
        embed = discord.Embed(
            title="Create Racing Team",
            description="Build the team card your driver will take to the starting line.",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Setup Progress", value=_setup_progress_text(state), inline=False)
        embed.add_field(name="Team Identity", value=_team_identity_text(state), inline=True)
        embed.add_field(name="Car Type", value=_car_type_text(state.car_type), inline=True)
        embed.add_field(name="Driver Stats", value=_driver_stats_text(state.stats), inline=False)
        embed.set_footer(text="Driver stats use a 24 point budget across six full-name stats.")
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.update_controls()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Team Details", style=discord.ButtonStyle.primary)
    async def team_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TeamDetailsModal(self))

    @discord.ui.button(label="Driver Stats", style=discord.ButtonStyle.primary)
    async def driver_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = DriverStatsView(self)
        await interaction.response.edit_message(embed=view.embed(), view=view)

    @discord.ui.button(label="Create Team", style=discord.ButtonStyle.success)
    async def create_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.state.ready:
            await interaction.response.send_message("Finish the wizard before creating the team.", ephemeral=True)
            return
        if not is_admin(interaction) and await self.cog.bot.db.get_team_by_owner(interaction.user.id):
            await interaction.response.send_message("You already have a team. Use `/team_edit_wizard` or `/parts_wizard` to change it.", ephemeral=True)
            return

        team = Team(
            None,
            self.state.name or "",
            self.state.driver or "",
            self.state.pit_crew or "",
            self.state.car_name or "",
            self.state.car_type or CarArchetype.COUPE_32,
            self.state.stats or DriverStats(4, 4, 4, 4, 4, 4),
            [],
            None if is_admin(interaction) else interaction.user.id,
        )
        try:
            team_id = await self.cog.bot.db.create_team(team)
            team.id = team_id
        except Exception as exc:
            await interaction.response.send_message(f"Team not created: {exc}", ephemeral=True)
            return
        await audit_log(self.cog.bot, "Team Created", f"#{team_id} {team.name}", interaction.user)

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Created team **{team.name}** as ID `{team_id}`. Next: open `/world` to enter the Blacktop Racing World.",
            embed=Embeds.team_sheet(team),
            view=self,
        )


class EditTeamWizardView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.state = TeamWizardState(
            name=team.name,
            driver=team.driver_name,
            pit_crew=team.pit_crew_name,
            car_name=team.car_name,
            car_type=team.archetype,
            stats=team.stats,
        )
        self.car_select = CarTypeSelect(self)
        self.add_item(self.car_select)
        self.update_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This team edit wizard belongs to someone else.", ephemeral=True)
        return False

    def update_controls(self) -> None:
        self.save_changes.disabled = not self.state.ready

    def embed(self, locked: bool = False) -> discord.Embed:
        state = self.state
        embed = discord.Embed(
            title=f"Edit Racing Team: #{self.team.id} {self.team.name}",
            description="Tune the team card for future races.",
            color=discord.Color.dark_teal(),
        )
        if locked:
            embed.description = "Team details are locked while this team is in an open tournament. Parts can still be changed."
        embed.add_field(name="Setup Progress", value=_setup_progress_text(state), inline=False)
        embed.add_field(name="Team Identity", value=_team_identity_text(state), inline=True)
        embed.add_field(name="Car Type", value=_car_type_text(state.car_type), inline=True)
        embed.add_field(name="Driver Stats", value=_driver_stats_text(state.stats), inline=False)
        embed.set_footer(text="Driver stats use a 24 point budget across six full-name stats.")
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.update_controls()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Team Details", style=discord.ButtonStyle.primary)
    async def team_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TeamDetailsModal(self))

    @discord.ui.button(label="Driver Stats", style=discord.ButtonStyle.primary)
    async def driver_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DriverStatsModal(self))

    @discord.ui.button(label="Save Changes", style=discord.ButtonStyle.success)
    async def save_changes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.state.ready or self.team.id is None:
            await interaction.response.send_message("Finish the wizard before saving changes.", ephemeral=True)
            return
        if await self.cog.bot.db.team_in_open_tournament(self.team.id):
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=self.embed(locked=True), view=self)
            return

        updated = Team(
            self.team.id,
            self.state.name or self.team.name,
            self.state.driver or self.team.driver_name,
            self.state.pit_crew or self.team.pit_crew_name,
            self.state.car_name or self.team.car_name,
            self.state.car_type or self.team.archetype,
            self.state.stats or self.team.stats,
            self.team.parts,
            self.team.owner_user_id,
            self.team.crew,
        )
        try:
            await self.cog.bot.db.update_team_profile(updated)
            self.team = updated
        except Exception as exc:
            await interaction.response.send_message(f"Team not updated: {exc}", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Updated team **{updated.name}**.",
            embed=Embeds.team_sheet(updated),
            view=self,
        )


class PartSlotSelect(discord.ui.Select):
    def __init__(self, wizard: "PartsWizardView"):
        self.wizard = wizard
        options = []
        installed_slots = wizard.installed_slots()
        for slot in PartSlot:
            status = "installed" if slot in installed_slots else "empty"
            options.append(
                discord.SelectOption(
                    label=f"{slot.value.title()} - {status}",
                    value=slot.value,
                    default=wizard.selected_slot == slot,
                )
            )
        super().__init__(placeholder="Choose a part slot", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.selected_slot = PartSlot(self.values[0])
        self.wizard.selected_part_key = self.wizard.first_available_part_key()
        await self.wizard.refresh(interaction)


class PartChoiceSelect(discord.ui.Select):
    def __init__(self, wizard: "PartsWizardView"):
        self.wizard = wizard
        part_keys = wizard.available_part_keys_for_slot(wizard.selected_slot)
        if not part_keys:
            options = [discord.SelectOption(label="No alternative parts available for this slot", value="none")]
            disabled = True
        else:
            if wizard.selected_part_key not in part_keys:
                wizard.selected_part_key = part_keys[0]
            options = [
                discord.SelectOption(
                    label=_part_label(key),
                    value=key,
                    description=_part_description(key),
                    default=wizard.selected_part_key == key,
                )
                for key in part_keys[:25]
            ]
            disabled = False
        super().__init__(
            placeholder="Choose a part to compare / fit",
            min_values=1,
            max_values=1,
            options=options,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        self.wizard.selected_part_key = self.values[0]
        await self.wizard.refresh(interaction)


class PartsWizardView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.selected_slot = PartSlot.ENGINE
        self.selected_part_key: str | None = self.first_available_part_key()
        self.rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This parts wizard belongs to someone else.", ephemeral=True)
        return False

    def installed_slots(self) -> set[PartSlot]:
        return {PARTS[key].slot for key in self.team.parts if key in PARTS}

    def installed_part_key_for_slot(self, slot: PartSlot) -> str | None:
        return next((key for key in self.team.parts if key in PARTS and PARTS[key].slot == slot), None)

    def available_part_keys_for_slot(self, slot: PartSlot) -> list[str]:
        return [key for key, part in PARTS.items() if part.slot == slot and key not in self.team.parts]

    def first_available_part_key(self) -> str | None:
        parts = self.available_part_keys_for_slot(self.selected_slot)
        return parts[0] if parts else None

    def rebuild_items(self) -> None:
        self.clear_items()
        current = self.installed_part_key_for_slot(self.selected_slot)
        can_fit = bool(self.selected_part_key) and self.selected_part_key in PARTS
        self.add_item(PartSlotSelect(self))
        self.add_item(PartChoiceSelect(self))

        install_button = discord.ui.Button(
            label="Fit / Replace Part",
            style=discord.ButtonStyle.success,
            disabled=not can_fit,
        )
        install_button.callback = self.install_selected_part
        self.add_item(install_button)

        remove_button = discord.ui.Button(label="Remove Slot Part", style=discord.ButtonStyle.danger, disabled=not current)
        remove_button.callback = self.remove_slot_part
        self.add_item(remove_button)

        compare_button = discord.ui.Button(label="Compare Part", style=discord.ButtonStyle.primary, disabled=not can_fit)
        compare_button.callback = self.compare_selected_part
        self.add_item(compare_button)

        refresh_button = discord.ui.Button(label="Refresh Sheet", style=discord.ButtonStyle.secondary)
        refresh_button.callback = self.refresh_sheet
        self.add_item(refresh_button)

    def embed(self, has_sheet: bool) -> discord.Embed:
        current_key = self.installed_part_key_for_slot(self.selected_slot)
        current = PARTS[current_key] if current_key else None
        selected = PARTS[self.selected_part_key] if self.selected_part_key in PARTS else None
        embed = discord.Embed(
            title=f"Parts Wizard: #{self.team.id} {self.team.name}",
            description=f"{self.team.car_name} - {self.team.archetype.value}",
        )
        embed.add_field(name="Selected Slot", value=self.selected_slot.value.title(), inline=True)
        embed.add_field(name="Installed", value=_part_label(current_key) if current_key else "Empty", inline=True)
        embed.add_field(name="Selected Part", value=_part_label(self.selected_part_key) if selected else "None", inline=True)
        current_risk = BuildService.illegal_disqualification_risk_percent(self.team)
        if current_risk:
            illegal_count = BuildService.illegal_part_count(self.team)
            embed.add_field(
                name="Current Illegal Parts Risk",
                value=f"{illegal_count} illegal part(s): {current_risk}% disqualification risk per race.",
                inline=False,
            )
        if selected:
            mods = ", ".join(f"{key.title()} {value:+d}" for key, value in selected.modifiers.as_dict().items() if value)
            embed.add_field(name="Selected Part Effects", value=mods or "No stat modifiers", inline=False)
            if self.selected_part_key and BuildService.is_illegal_part_key(self.selected_part_key):
                projected = compare_part(self.team, self.selected_part_key).after_illegal_risk
                embed.add_field(
                    name="Illegal Part Warning",
                    value=(
                        f"Each fitted illegal part contributes +{ILLEGAL_PART_DISQUALIFICATION_RISK}% disqualification risk. "
                        f"With this replacement fitted, the team would have {projected}% risk per race."
                    ),
                    inline=False,
                )
        if has_sheet:
            embed.set_image(url="attachment://parts_wizard.png")
        else:
            embed.add_field(
                name="Image Sheet",
                value="Install `Pillow` from requirements.txt to render the garage sheet image.",
                inline=False,
            )
        return embed

    def garage_file(self) -> discord.File | None:
        sheet = render_parts_sheet(self.team)
        if not sheet:
            return None
        return discord.File(sheet, filename="parts_wizard.png")

    async def reload_team(self) -> None:
        if self.team.id is None:
            return
        team = await self.cog.bot.db.get_team(self.team.id)
        if team:
            self.team = team

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.rebuild_items()
        file = self.garage_file()
        await interaction.response.edit_message(
            embed=self.embed(has_sheet=bool(file)),
            attachments=[file] if file else [],
            view=self,
        )

    async def install_selected_part(self, interaction: discord.Interaction):
        if self.team.id is None or not self.selected_part_key or self.selected_part_key not in PARTS:
            await interaction.response.send_message("Choose a valid part first.", ephemeral=True)
            return
        part = PARTS[self.selected_part_key]
        if part.slot != self.selected_slot:
            await interaction.response.send_message("That part does not fit the selected slot.", ephemeral=True)
            return
        # v0.4.5 garage gameplay: fitting an alternative replaces the current
        # part in that slot atomically instead of forcing a remove-then-install dance.
        parts = [
            key for key in self.team.parts
            if key in PARTS and PARTS[key].slot != self.selected_slot
        ]
        parts = normalized_parts([*parts, self.selected_part_key])
        await self.cog.bot.db.update_team_parts(self.team.id, parts)
        await self.reload_team()
        self.selected_part_key = self.first_available_part_key()
        await self.refresh(interaction)

    async def compare_selected_part(self, interaction: discord.Interaction):
        if not self.selected_part_key or self.selected_part_key not in PARTS:
            await interaction.response.send_message("Choose a valid part first.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_part_comparison_embed(self.team, self.selected_part_key),
            ephemeral=True,
        )

    async def remove_slot_part(self, interaction: discord.Interaction):
        if self.team.id is None:
            await interaction.response.send_message("Team is missing an ID.", ephemeral=True)
            return
        current = self.installed_part_key_for_slot(self.selected_slot)
        if not current:
            await interaction.response.send_message("That slot is already empty.", ephemeral=True)
            return
        parts = [key for key in self.team.parts if key != current]
        await self.cog.bot.db.update_team_parts(self.team.id, parts)
        await self.reload_team()
        self.selected_part_key = self.first_available_part_key()
        await self.refresh(interaction)

    async def refresh_sheet(self, interaction: discord.Interaction):
        await self.reload_team()
        await self.refresh(interaction)


class CrewSlotSelect(discord.ui.Select):
    def __init__(self, wizard: "PitCrewWizardView"):
        self.wizard = wizard
        options = []
        for slot in CrewSlot:
            member_key = wizard.team.crew.get(slot.value)
            status = CREW_MEMBERS[member_key].name if member_key in CREW_MEMBERS else "empty"
            options.append(
                discord.SelectOption(
                    label=f"{slot.value.replace('_', ' ').title()} - {status}"[:100],
                    value=slot.value,
                    default=wizard.selected_slot == slot,
                )
            )
        super().__init__(placeholder="Choose a pit crew position", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.selected_slot = CrewSlot(self.values[0])
        self.wizard.selected_member_key = self.wizard.current_member_key_for_slot(self.wizard.selected_slot) or self.wizard.first_member_key()
        await self.wizard.refresh(interaction)


class CrewMemberSelect(discord.ui.Select):
    def __init__(self, wizard: "PitCrewWizardView"):
        self.wizard = wizard
        member_keys = wizard.member_keys_for_slot(wizard.selected_slot)
        if wizard.selected_member_key not in member_keys:
            wizard.selected_member_key = member_keys[0] if member_keys else None
        options = [
            discord.SelectOption(
                label=_crew_label(key),
                value=key,
                description=_crew_description(key),
                default=wizard.selected_member_key == key,
            )
            for key in member_keys[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No crew members available", value="none")]
        super().__init__(
            placeholder="Choose a crew member",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not bool(member_keys),
        )

    async def callback(self, interaction: discord.Interaction):
        self.wizard.selected_member_key = self.values[0]
        await self.wizard.refresh(interaction)


class PitCrewWizardView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, level: int = 1):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.level = level
        self.selected_slot = CrewSlot.CREW_CHIEF
        self.selected_member_key: str | None = self.current_member_key_for_slot(self.selected_slot) or self.first_member_key()
        self.rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This pit crew wizard belongs to someone else.", ephemeral=True)
        return False

    def member_keys_for_slot(self, slot: CrewSlot) -> list[str]:
        current = self.current_member_key_for_slot(slot)
        return [
            key for key, member in CREW_MEMBERS.items()
            if member.slot == slot and (crew_unlocked(key, self.level) or key == current)
        ]

    def first_member_key(self) -> str | None:
        members = self.member_keys_for_slot(self.selected_slot)
        return members[0] if members else None

    def current_member_key_for_slot(self, slot: CrewSlot) -> str | None:
        key = self.team.crew.get(slot.value)
        return key if key in CREW_MEMBERS else None

    def rebuild_items(self) -> None:
        self.clear_items()
        self.add_item(CrewSlotSelect(self))
        self.add_item(CrewMemberSelect(self))

        assign_button = discord.ui.Button(label="Assign Member", style=discord.ButtonStyle.success, disabled=not self.selected_member_key)
        assign_button.callback = self.assign_member
        self.add_item(assign_button)

        clear_button = discord.ui.Button(
            label="Clear Position",
            style=discord.ButtonStyle.danger,
            disabled=not self.current_member_key_for_slot(self.selected_slot),
        )
        clear_button.callback = self.clear_position
        self.add_item(clear_button)

        refresh_button = discord.ui.Button(label="Refresh Sheet", style=discord.ButtonStyle.secondary)
        refresh_button.callback = self.refresh_sheet
        self.add_item(refresh_button)

    def embed(self, has_sheet: bool) -> discord.Embed:
        current_key = self.current_member_key_for_slot(self.selected_slot)
        selected = CREW_MEMBERS[self.selected_member_key] if self.selected_member_key in CREW_MEMBERS else None
        embed = discord.Embed(
            title=f"Pit Crew Wizard: #{self.team.id} {self.team.name}",
            description=f"{self.team.pit_crew_name} - {self.team.car_name}",
        )
        embed.add_field(name="Selected Position", value=self.selected_slot.value.replace("_", " ").title(), inline=True)
        embed.add_field(name="Assigned", value=_crew_label(current_key) if current_key else "Empty", inline=True)
        embed.add_field(name="Selected Member", value=selected.name if selected else "None", inline=True)
        if selected:
            embed.add_field(name="What They Actually Do", value=crew_role_summary(selected), inline=False)
            embed.add_field(name="Crew Note", value=selected.description, inline=False)
            required = crew_required_level(self.selected_member_key)
            if required > 1:
                embed.add_field(name="Specialist Access", value=f"Unlocked at **Level {required}** · team level **{self.level}**", inline=False)
        embed.add_field(name="Current Crew Roles", value="\n".join(crew_roster_lines(self.team))[:1024], inline=False)
        if has_sheet:
            embed.set_image(url="attachment://pit_crew_wizard.png")
        else:
            embed.add_field(
                name="Image Sheet",
                value="Install `Pillow` from requirements.txt to render the pit crew sheet image.",
                inline=False,
            )
        return embed

    def crew_file(self) -> discord.File | None:
        sheet = render_crew_sheet(self.team)
        if not sheet:
            return None
        return discord.File(sheet, filename="pit_crew_wizard.png")

    async def reload_team(self) -> None:
        if self.team.id is None:
            return
        team = await self.cog.bot.db.get_team(self.team.id)
        if team:
            self.team = team

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.rebuild_items()
        file = self.crew_file()
        await interaction.response.edit_message(
            embed=self.embed(has_sheet=bool(file)),
            attachments=[file] if file else [],
            view=self,
        )

    async def assign_member(self, interaction: discord.Interaction):
        if self.team.id is None or not self.selected_member_key or self.selected_member_key not in CREW_MEMBERS:
            await interaction.response.send_message("Choose a valid crew member first.", ephemeral=True)
            return
        member = CREW_MEMBERS[self.selected_member_key]
        if not crew_unlocked(self.selected_member_key, self.level):
            await interaction.response.send_message(
                f"**{member.name}** is a specialist candidate and unlocks at Level {crew_required_level(self.selected_member_key)}.",
                ephemeral=True,
            )
            return
        if member.slot != self.selected_slot:
            await interaction.response.send_message("That crew member does not fit the selected position.", ephemeral=True)
            return
        crew = {**self.team.crew, self.selected_slot.value: self.selected_member_key}
        await self.cog.bot.db.update_team_crew(self.team.id, crew)
        await self.reload_team()
        await self.refresh(interaction)

    async def clear_position(self, interaction: discord.Interaction):
        if self.team.id is None:
            await interaction.response.send_message("Team is missing an ID.", ephemeral=True)
            return
        crew = {key: value for key, value in self.team.crew.items() if key != self.selected_slot.value}
        await self.cog.bot.db.update_team_crew(self.team.id, crew)
        await self.reload_team()
        await self.refresh(interaction)

    async def refresh_sheet(self, interaction: discord.Interaction):
        await self.reload_team()
        await self.refresh(interaction)


class SetupPresetSelect(discord.ui.Select):
    def __init__(self, manager: "SetupManagerView"):
        self.manager = manager
        options = [
            discord.SelectOption(
                label=name,
                value=name,
                description=("Saved setup" if name in saved_setup_summary(manager.setup_rows) else "Empty preset"),
                default=manager.selected == name,
            )
            for name in manager.available_names
        ]
        super().__init__(placeholder="Choose a garage preset", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.manager.selected = self.values[0]
        await self.manager.refresh(interaction)


class SetupManagerView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, setup_rows, mode: str, level: int = 1):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.setup_rows = list(setup_rows or [])
        self.mode = mode if mode in {"save", "load"} else "save"
        self.level = level
        unlocked = list(unlocked_setup_names(level))
        saved_names = [str(row["setup_name"]) for row in self.setup_rows if str(row["setup_name"]) in SETUP_PRESETS]
        self.available_names = tuple(dict.fromkeys([*unlocked, *saved_names]))
        self.selected = self.available_names[0] if self.available_names else SETUP_PRESETS[0]
        self.rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("This setup panel belongs to another driver.", ephemeral=True)
        return False

    def rebuild_items(self) -> None:
        self.clear_items()
        self.add_item(SetupPresetSelect(self))
        save = discord.ui.Button(label="Save Current", style=discord.ButtonStyle.success, row=1)
        save.callback = self.save_current
        self.add_item(save)
        saved = saved_setup_summary(self.setup_rows)
        load = discord.ui.Button(
            label="Load Selected",
            style=discord.ButtonStyle.primary,
            disabled=self.selected not in saved,
            row=1,
        )
        load.callback = self.load_selected
        self.add_item(load)
        garage = discord.ui.Button(label="Back to Garage", style=discord.ButtonStyle.secondary, row=1)
        garage.callback = self.back_to_garage
        self.add_item(garage)

    async def reload(self) -> None:
        if self.team.id is None:
            return
        team = await self.cog.bot.db.get_team(self.team.id)
        if team:
            self.team = team
        self.setup_rows = list(await self.cog.bot.db.team_setups(self.team.id))

    async def refresh(self, interaction: discord.Interaction, content: str | None = None) -> None:
        await self.reload()
        self.rebuild_items()
        await interaction.response.edit_message(
            content=content,
            embed=_setup_manager_embed(self.team, self.setup_rows, self.selected, self.mode),
            view=self,
        )

    async def save_current(self, interaction: discord.Interaction):
        if self.team.id is None:
            await interaction.response.send_message("Team is missing an ID.", ephemeral=True)
            return
        if self.selected not in unlocked_setup_names(self.level):
            await interaction.response.send_message(
                f"**{self.selected}** is not unlocked for new saves yet. Keep racing to raise the team level.",
                ephemeral=True,
            )
            return
        parts = normalized_parts(self.team.parts)
        await self.cog.bot.db.save_team_setup(self.team.id, self.selected, parts)
        await audit_log(
            self.cog.bot,
            "Garage Setup Saved",
            f"#{self.team.id} {self.team.name}: {self.selected} ({len(parts)} parts)",
            interaction.user,
        )
        await self.refresh(interaction, f"✅ Saved the current hardware as **{self.selected}**.")

    async def load_selected(self, interaction: discord.Interaction):
        if self.team.id is None:
            await interaction.response.send_message("Team is missing an ID.", ephemeral=True)
            return
        row = await self.cog.bot.db.team_setup(self.team.id, self.selected)
        if not row:
            await interaction.response.send_message("That preset is empty.", ephemeral=True)
            return
        try:
            stored = json.loads(row["parts_json"])
        except Exception:
            await interaction.response.send_message("That preset is damaged and could not be loaded.", ephemeral=True)
            return
        if not isinstance(stored, list):
            await interaction.response.send_message("That preset has invalid part data.", ephemeral=True)
            return
        missing = [str(key) for key in stored if str(key) not in PARTS]
        parts = normalized_parts([str(key) for key in stored])
        await self.cog.bot.db.update_team_parts(self.team.id, parts)
        await audit_log(
            self.cog.bot,
            "Garage Setup Loaded",
            f"#{self.team.id} {self.team.name}: {self.selected} ({len(parts)} parts)",
            interaction.user,
        )
        note = f"✅ Loaded **{self.selected}** — {len(parts)} part(s) fitted."
        if missing:
            note += f" Ignored {len(missing)} retired/unknown part(s)."
        await self.refresh(interaction, note)

    async def back_to_garage(self, interaction: discord.Interaction):
        await self.reload()
        view = GarageView(self.cog, self.owner_id, self.team, self.setup_rows)
        await interaction.response.edit_message(content=None, embed=view.embed(), view=view)


class GarageView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, setup_rows=(), level: int = 1):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.setup_rows = list(setup_rows or [])
        self.level = level

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("This garage belongs to another driver.", ephemeral=True)
        return False

    def embed(self) -> discord.Embed:
        return _garage_embed(self.team, self.setup_rows, self.level)

    async def _reload(self) -> None:
        if self.team.id is None:
            return
        team = await self.cog.bot.db.get_team(self.team.id)
        if team:
            self.team = team
        self.setup_rows = list(await self.cog.bot.db.team_setups(self.team.id))
        progress = await self.cog.bot.db.team_progress(self.team.id)
        self.level = level_for_xp(int(progress["xp"]) if progress else 0)

    async def _open_parts(self, interaction: discord.Interaction, instruction: str) -> None:
        await self._reload()
        view = PartsWizardView(self.cog, self.owner_id, self.team)
        file = view.garage_file()
        if file:
            await interaction.response.send_message(content=instruction, embed=view.embed(True), file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(content=instruction, embed=view.embed(False), view=view, ephemeral=True)

    @discord.ui.button(label="Fit Part", style=discord.ButtonStyle.success, row=0)
    async def fit_part(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_parts(interaction, "Choose a slot and alternative part, then use **Fit / Replace Part**.")

    @discord.ui.button(label="Remove Part", style=discord.ButtonStyle.danger, row=0)
    async def remove_part(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_parts(interaction, "Choose the fitted slot you want to strip, then use **Remove Slot Part**.")

    @discord.ui.button(label="Compare Part", style=discord.ButtonStyle.primary, row=0)
    async def compare_part_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_parts(interaction, "Choose an alternative and use **Compare Part** before fitting it.")

    @discord.ui.button(label="Save Setup", style=discord.ButtonStyle.secondary, row=0)
    async def save_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._reload()
        view = SetupManagerView(self.cog, self.owner_id, self.team, self.setup_rows, "save", self.level)
        await interaction.response.send_message(embed=_setup_manager_embed(self.team, self.setup_rows, view.selected, "save"), view=view, ephemeral=True)

    @discord.ui.button(label="Load Setup", style=discord.ButtonStyle.secondary, row=0)
    async def load_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._reload()
        view = SetupManagerView(self.cog, self.owner_id, self.team, self.setup_rows, "load", self.level)
        await interaction.response.send_message(embed=_setup_manager_embed(self.team, self.setup_rows, view.selected, "load"), view=view, ephemeral=True)

    @discord.ui.button(label="Ask Crew Chief", style=discord.ButtonStyle.primary, row=1)
    async def ask_crew_chief(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._reload()
        await interaction.response.send_message(embed=_crew_chief_advice_embed(self.team), ephemeral=True)

    @discord.ui.button(label="Pit Crew", style=discord.ButtonStyle.primary, row=1)
    async def pit_crew(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._reload()
        view = PitCrewWizardView(self.cog, self.owner_id, self.team, self.level)
        file = view.crew_file()
        if file:
            await interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

    @discord.ui.button(label="Refresh Garage", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_garage(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._reload()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class MyTeamActionsView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("This garage panel belongs to another driver.", ephemeral=True)
        return False

    @discord.ui.button(label="Edit Team", style=discord.ButtonStyle.primary)
    async def edit_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.team.id is not None and await self.cog.bot.db.team_in_open_tournament(self.team.id):
            await interaction.response.send_message("That team is locked while it is in an open tournament.", ephemeral=True)
            return
        view = EditTeamWizardView(self.cog, interaction.user.id, self.team)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @discord.ui.button(label="Parts Wizard", style=discord.ButtonStyle.primary)
    async def parts_wizard(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = PartsWizardView(self.cog, interaction.user.id, self.team)
        file = view.garage_file()
        if file:
            await interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

    @discord.ui.button(label="Pit Crew Wizard", style=discord.ButtonStyle.primary)
    async def pit_crew_wizard(self, interaction: discord.Interaction, button: discord.ui.Button):
        progress = await self.cog.bot.db.team_progress(self.team.id) if self.team.id is not None else None
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        view = PitCrewWizardView(self.cog, interaction.user.id, self.team, level)
        file = view.crew_file()
        if file:
            await interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

    @discord.ui.button(label="Scrutineering", style=discord.ButtonStyle.secondary)
    async def scrutineering(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=scrutineering_embed([self.team], title=f"Scrutineering Report: {self.team.name}"),
            ephemeral=True,
        )


class SponsorOfferActionView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, offers):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.offer = next((offer for offer in offers if offer["status"] == "offered"), None)
        self.accept.disabled = self.offer is None or bool(team.active_sponsor_key)
        self.reject.disabled = self.offer is None
        self.end_contract.disabled = not bool(team.active_sponsor_key)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("These sponsor controls belong to another driver.", ephemeral=True)
        return False

    @discord.ui.button(label="Accept Latest Offer", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.offer or self.team.id is None:
            await interaction.response.send_message("No active sponsor offer to accept.", ephemeral=True)
            return
        try:
            key = await self.cog.bot.db.accept_sponsor_offer(self.team.id, int(self.offer["id"]))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        sponsor = sponsor_by_key(key)
        await audit_log(self.cog.bot, "Sponsor Contract Accepted", f"#{self.team.id} {self.team.name}: {sponsor.name if sponsor else key}", interaction.user)
        team = await self.cog.bot.db.get_team(self.team.id)
        offers = await self.cog.bot.db.team_sponsor_offers(self.team.id, limit=8)
        await interaction.response.edit_message(
            embed=sponsor_offers_embed(team or self.team, offers),
            view=SponsorOfferActionView(self.cog, self.owner_id, team or self.team, offers),
        )

    @discord.ui.button(label="Reject Latest Offer", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.offer:
            await interaction.response.send_message("No active sponsor offer to reject.", ephemeral=True)
            return
        await self.cog.bot.db.update_sponsor_offer_status(int(self.offer["id"]), "rejected")
        await audit_log(self.cog.bot, "Sponsor Offer Rejected", f"#{self.team.id} {self.team.name}: {self.offer['sponsor_name']}", interaction.user)
        offers = await self.cog.bot.db.team_sponsor_offers(self.team.id, limit=8)
        await interaction.response.edit_message(embed=sponsor_offers_embed(self.team, offers), view=SponsorOfferActionView(self.cog, self.owner_id, self.team, offers))

    @discord.ui.button(label="End Current Contract", style=discord.ButtonStyle.secondary)
    async def end_contract(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.team.id is None or not self.team.active_sponsor_key:
            await interaction.response.send_message("This team is already independent.", ephemeral=True)
            return
        sponsor = sponsor_by_key(self.team.active_sponsor_key)
        await self.cog.bot.db.end_sponsor_contract(self.team.id)
        await audit_log(self.cog.bot, "Sponsor Contract Ended", f"#{self.team.id} {self.team.name}: {sponsor.name if sponsor else self.team.active_sponsor_key}", interaction.user)
        team = await self.cog.bot.db.get_team(self.team.id)
        offers = await self.cog.bot.db.team_sponsor_offers(self.team.id, limit=8)
        await interaction.response.edit_message(embed=sponsor_offers_embed(team or self.team, offers), view=SponsorOfferActionView(self.cog, self.owner_id, team or self.team, offers))


def _identity_name(options, key: str, fallback: str) -> str:
    return next((item.name for item in options if item.key == key), fallback)


def team_identity_embed(team: Team, identity, level: int) -> discord.Embed:
    livery = identity["livery_key"] if identity else "bare_primer"
    emblem = identity["emblem_key"] if identity else "rat_skull"
    decor = identity["garage_decor_key"] if identity else "oil_stained_bench"
    intro = identity["intro_phrase"] if identity else ""
    embed = discord.Embed(title=f"🏁 Team Identity — {team.name}", color=discord.Color.purple())
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="Livery", value=_identity_name(LIVERIES, livery, livery), inline=True)
    embed.add_field(name="Emblem", value=_identity_name(EMBLEMS, emblem, emblem), inline=True)
    embed.add_field(name="Garage", value=_identity_name(GARAGE_DECOR, decor, decor), inline=True)
    embed.add_field(name="Intro Phrase", value=intro or "Standard race introduction", inline=False)
    embed.set_footer(text="Identity unlocks are cosmetic. They never add raw speed, handling or reliability.")
    return embed


class IdentitySelect(discord.ui.Select):
    def __init__(self, view: "TeamIdentityView", kind: str, options):
        self.identity_view = view
        self.kind = kind
        choices = [discord.SelectOption(label=o.name, value=o.key, description=f"Unlocked at Level {o.required_level}") for o in unlocked_options(options, view.level)]
        super().__init__(placeholder=f"Choose {kind.replace('_', ' ')}", min_values=1, max_values=1, options=choices[:25], row={"livery_key":0,"emblem_key":1,"garage_decor_key":2}[kind])

    async def callback(self, interaction: discord.Interaction):
        await self.identity_view.cog.bot.db.update_team_identity(self.identity_view.team.id, **{self.kind: self.values[0]})
        await self.identity_view.refresh(interaction)


class IntroPhraseModal(ReliableModal, title="Custom Team Intro"): 
    phrase = discord.ui.TextInput(label="Intro phrase", max_length=160, required=False, placeholder="e.g. The Rust Kings roll out under a cloud of bad decisions...")
    def __init__(self, view: "TeamIdentityView"):
        super().__init__()
        self.identity_view = view

    async def on_submit(self, interaction: discord.Interaction):
        if self.identity_view.level < 3:
            await interaction.response.send_message("Custom intros unlock at Level 3.", ephemeral=True)
            return
        await self.identity_view.cog.bot.db.update_team_identity(self.identity_view.team.id, intro_phrase=str(self.phrase.value).strip())
        await self.identity_view.refresh(interaction)


class TeamIdentityView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, identity, level: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.identity = identity
        self.level = level
        self.add_item(IdentitySelect(self, "livery_key", LIVERIES))
        self.add_item(IdentitySelect(self, "emblem_key", EMBLEMS))
        self.add_item(IdentitySelect(self, "garage_decor_key", GARAGE_DECOR))
        intro = discord.ui.Button(label="Set Intro Phrase", style=discord.ButtonStyle.primary, row=3, disabled=level < 3)
        intro.callback = self.set_intro
        self.add_item(intro)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("This identity panel belongs to another driver.", ephemeral=True)
        return False

    async def set_intro(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IntroPhraseModal(self))

    async def refresh(self, interaction: discord.Interaction):
        self.identity = await self.cog.bot.db.team_identity(self.team.id)
        await interaction.response.edit_message(embed=team_identity_embed(self.team, self.identity, self.level), view=self)


class AdminTeamCommandSelect(discord.ui.Select):
    def __init__(self, parent: "AdminTeamCommandSelectView", teams):
        self.parent = parent
        options = [
            discord.SelectOption(
                label=f"#{team.id} {team.name}"[:100],
                value=str(team.id),
                description=f"{team.driver_name} - {team.car_name}"[:100],
            )
            for team in teams[:25]
            if team.id is not None
        ]
        super().__init__(placeholder="Choose a team", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        team = await self.parent.cog.bot.db.get_team(int(self.values[0]))
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
        await self.parent.on_team(interaction, team)


class AdminTeamCommandSelectView(ReliableView):
    def __init__(self, cog: "TeamsCog", owner_id: int, teams, on_team):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.on_team = on_team
        self.add_item(AdminTeamCommandSelect(self, teams))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This team selector belongs to another admin.", ephemeral=True)
        return False


class TeamsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_ephemeral(self, interaction: discord.Interaction, message: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    async def _owned_or_admin_team(self, interaction: discord.Interaction, team_id: int | None = None) -> Team | None:
        if is_admin(interaction):
            if team_id is None:
                await self._send_ephemeral(interaction, "Pick a team ID for that admin action.")
                return None
            team = await self.bot.db.get_team(team_id)
            if not team:
                await self._send_ephemeral(interaction, "Team not found.")
                return None
            return team

        own_team = await self.bot.db.get_team_by_owner(interaction.user.id)
        if not own_team:
            await self._send_ephemeral(interaction, "You do not have a team yet. Use `/team_wizard` to create one.")
            return None
        if team_id is not None and own_team.id != team_id:
            await self._send_ephemeral(interaction, "You can only change your own team.")
            return None
        return own_team

    async def _prompt_admin_team(self, interaction: discord.Interaction, on_team, message: str = "Choose a team.") -> None:
        teams = await self.bot.db.list_teams()
        if not teams:
            await self._send_ephemeral(interaction, "No teams found.")
            return
        view = AdminTeamCommandSelectView(self, interaction.user.id, teams, on_team)
        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    # ----------------------------
    # AUTOCOMPLETE HELPERS
    # ----------------------------

    async def team_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[int]]:
        """Autocomplete teams as: #1 Team Name — Driver — Car."""
        if is_admin(interaction):
            teams = await self.bot.db.list_teams()
        else:
            team = await self.bot.db.get_team_by_owner(interaction.user.id)
            teams = [team] if team else []
        current_lower = str(current).lower()

        choices: list[app_commands.Choice[int]] = []
        for team in teams:
            label = f"#{team.id} {team.name} — {team.driver_name} — {team.car_name}"
            searchable = f"{team.id} {team.name} {team.driver_name} {team.car_name}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=int(team.id)))

        return choices[:25]

    async def add_part_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete parts, hiding parts blocked by an already-filled slot when team_id is known."""
        current_lower = str(current).lower()
        team_id = getattr(interaction.namespace, "team_id", None)
        team = None

        if isinstance(team_id, int):
            team = await self.bot.db.get_team(team_id)

        choices: list[app_commands.Choice[str]] = []
        for key, part in PARTS.items():
            if team:
                # Hide already fitted parts.
                if key in team.parts:
                    continue
                # Hide parts from slots already occupied by another fitted part.
                occupied_slots = {
                    PARTS[p].slot
                    for p in team.parts
                    if p in PARTS
                }
                if part.slot in occupied_slots:
                    continue

            label = f"{_part_label(key)} [{part.slot.value}] — {key}"
            searchable = f"{key} {part.name} {part.slot.value} {part.description}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=key))

        return choices[:25]

    async def remove_part_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete only the parts currently fitted to the selected team."""
        current_lower = str(current).lower()
        team_id = getattr(interaction.namespace, "team_id", None)

        if not isinstance(team_id, int):
            return []

        team = await self.bot.db.get_team(team_id)
        if not team:
            return []

        choices: list[app_commands.Choice[str]] = []
        for key in team.parts:
            part = PARTS.get(key)
            if not part:
                continue
            label = f"{_part_label(key)} [{part.slot.value}] — {key}"
            searchable = f"{key} {part.name} {part.slot.value} {part.description}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=key))

        return choices[:25]

    # ----------------------------
    # TEAM COMMANDS
    # ----------------------------

    @app_commands.command(name="team_create", description="Create a rat rod racing team.")
    @app_commands.describe(
        name="Team name",
        driver="Driver name",
        pit_crew="Pit crew name",
        car_name="Rod name",
        car_type="Car archetype",
        nerve="1-8",
        handling="1-8",
        aggression="1-8",
        mechanics="1-8",
        reflexes="1-8",
        showmanship="1-8",
    )
    @app_commands.choices(
        nerve=STAT_CHOICES,
        handling=STAT_CHOICES,
        aggression=STAT_CHOICES,
        mechanics=STAT_CHOICES,
        reflexes=STAT_CHOICES,
        showmanship=STAT_CHOICES,
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        name: str,
        driver: str,
        pit_crew: str,
        car_name: str,
        car_type: CarArchetype,
        nerve: int,
        handling: int,
        aggression: int,
        mechanics: int,
        reflexes: int,
        showmanship: int,
    ):
        try:
            if not await self._require_admin(interaction):
                return
            stats = DriverStats(nerve, handling, aggression, mechanics, reflexes, showmanship)
            stats.validate()
            team = Team(None, name, driver, pit_crew, car_name, car_type, stats, [])
            team_id = await self.bot.db.create_team(team)
            team.id = team_id
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await audit_log(self.bot, "Team Created", f"#{team_id} {team.name}", interaction.user)

        await interaction.response.send_message(
            f"✅ Created team **{name}** as ID `{team_id}`.",
            embed=Embeds.team_sheet(team),
            ephemeral=True,
        )

    @app_commands.command(name="team_wizard", description="Create a racing team with a guided setup flow.")
    async def team_wizard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_admin(interaction) and await self.bot.db.get_team_by_owner(interaction.user.id):
            await interaction.followup.send("You already have a team. Use `/team_edit_wizard` or `/parts_wizard` to change it.", ephemeral=True)
            return
        view = TeamWizardView(self, interaction.user.id)
        await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="team_edit_wizard", description="Edit your team details, car, and driver stats.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_edit_wizard(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def open_selected(select_interaction: discord.Interaction, selected_team: Team):
                if selected_team.id is not None and await self.bot.db.team_in_open_tournament(selected_team.id):
                    await select_interaction.response.send_message(
                        "That team is in an open tournament, so team details are locked. You can still use `/parts_wizard`.",
                        ephemeral=True,
                    )
                    return
                view = EditTeamWizardView(self, select_interaction.user.id, selected_team)
                await select_interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

            await self._prompt_admin_team(interaction, open_selected, "Choose a team to edit.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team:
            return
        if team.id is not None and await self.bot.db.team_in_open_tournament(team.id):
            await interaction.followup.send(
                "That team is in an open tournament, so team details are locked. You can still use `/parts_wizard`.",
                ephemeral=True,
            )
            return

        view = EditTeamWizardView(self, interaction.user.id, team)
        await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="team_list", description="List all racing teams.")
    async def team_list(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        teams = await self.bot.db.list_teams()
        if not teams:
            await interaction.response.send_message("No teams yet. Use `/team_create`.", ephemeral=True)
            return

        lines = [f"`{t.id}` **{t.name}** — {t.driver_name} — {t.car_name}" for t in teams]
        view = PaginatedTextView(interaction.user.id, "Team List", lines, per_page=12)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="team_sheet", description="Show a full team sheet.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_sheet(self, interaction: discord.Interaction, team_id: int | None = None):
        if not await self._require_admin(interaction):
            return
        if team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                sheet = render_team_sheet(selected_team)
                if not sheet:
                    await select_interaction.response.send_message(embed=Embeds.team_sheet(selected_team), ephemeral=True)
                    return
                file = discord.File(sheet, filename="team_sheet.png")
                embed = discord.Embed(title=f"#{selected_team.id} {selected_team.name} Team Card")
                embed.set_image(url="attachment://team_sheet.png")
                await select_interaction.response.send_message(embed=embed, file=file, ephemeral=True)

            await self._prompt_admin_team(interaction, show_selected, "Choose a team sheet to view.")
            return
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        sheet = render_team_sheet(team)
        if not sheet:
            await interaction.response.send_message(embed=Embeds.team_sheet(team), ephemeral=True)
            return

        file = discord.File(sheet, filename="team_sheet.png")
        embed = discord.Embed(title=f"#{team.id} {team.name} Team Card")
        embed.set_image(url="attachment://team_sheet.png")

        illegal_risk = BuildService.illegal_disqualification_risk_percent(team)
        if illegal_risk:
            embed.add_field(
                name="Illegal Parts Warning",
                value=f"{BuildService.illegal_part_count(team)} illegal part(s): {illegal_risk}% disqualification risk per race.",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="team_reputation", description="Show a team's earned driver reputation.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_reputation(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return

        profile = await self.bot.db.team_profile(team.id)
        await interaction.followup.send(embed=reputation_embed(team, profile), ephemeral=True)

    @app_commands.command(name="my_team", description="Show your garage, parts, crew, risks, and next jobs.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def my_team(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                setup_rows = await self.bot.db.team_setups(selected_team.id)
                progress = await self.bot.db.team_progress(selected_team.id)
                level = level_for_xp(int(progress["xp"]) if progress else 0)
                view = GarageView(self, select_interaction.user.id, selected_team, setup_rows, level)
                await select_interaction.response.send_message(
                    embed=view.embed(),
                    view=view,
                    ephemeral=True,
                )

            await self._prompt_admin_team(interaction, show_selected, "Choose a team dashboard to view.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return

        setup_rows = await self.bot.db.team_setups(team.id)
        progress = await self.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        view = GarageView(self, interaction.user.id, team, setup_rows, level)
        await interaction.followup.send(
            embed=view.embed(),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="scrutineering", description="Inspect your team's race risks before fitting parts or racing.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def scrutineering(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                await select_interaction.response.send_message(
                    embed=scrutineering_embed([selected_team], title=f"Scrutineering Report: {selected_team.name}"),
                    ephemeral=True,
                )

            await self._prompt_admin_team(interaction, show_selected, "Choose a team to inspect.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team:
            return

        await interaction.followup.send(
            embed=scrutineering_embed([team], title=f"Scrutineering Report: {team.name}"),
            ephemeral=True,
        )

    @app_commands.command(name="hall_of_fame", description="Show champions, record holders, and legendary rivalries.")
    async def hall_of_fame(self, interaction: discord.Interaction):
        await interaction.response.defer()
        stat_keys = (
            "wins",
            "overtakes",
            "last_minute_wins",
            "pit_stops",
            "near_misses",
            "crashes",
            "illegal_moves",
            "peak_damage",
        )
        stat_leaders = {
            key: await self.bot.db.hall_of_fame_stat_leaders(key, limit=1)
            for key in stat_keys
        }
        embed = hall_of_fame_embed(
            champions=await self.bot.db.hall_of_fame_champions(),
            podiums=await self.bot.db.hall_of_fame_podiums(),
            stat_leaders=stat_leaders,
            rivalries=await self.bot.db.hall_of_fame_rivalries(),
            recent_seasons=await self.bot.db.season_history(limit=5),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="team_rivalries", description="Show a team's hottest rivalries.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_rivalries(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                rivalries = await self.bot.db.team_rivalries(selected_team.id)
                await select_interaction.response.send_message(embed=rivalries_embed(selected_team, rivalries), ephemeral=True)

            await self._prompt_admin_team(interaction, show_selected, "Choose a team for rivalries.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return

        rivalries = await self.bot.db.team_rivalries(team.id)
        await interaction.followup.send(embed=rivalries_embed(team, rivalries), ephemeral=True)

    @app_commands.command(name="team_progress", description="Show cosmetic XP, traits, achievements, sponsors, and fatigue.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_progress(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                await select_interaction.response.send_message(
                    embed=progress_embed(
                        selected_team,
                        await self.bot.db.team_progress(selected_team.id),
                        await self.bot.db.team_achievements(selected_team.id),
                        await self.bot.db.team_sponsor_offers(selected_team.id),
                        await self.bot.db.team_fatigue(selected_team.id),
                    ),
                    ephemeral=True,
                )

            await self._prompt_admin_team(interaction, show_selected, "Choose a team for progress.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return
        await interaction.followup.send(
            embed=progress_embed(
                team,
                await self.bot.db.team_progress(team.id),
                await self.bot.db.team_achievements(team.id),
                await self.bot.db.team_sponsor_offers(team.id),
                await self.bot.db.team_fatigue(team.id),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="team_title", description="Choose an unlocked cosmetic team title.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_title(self, interaction: discord.Interaction, title: str, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return
        progress = await self.bot.db.team_progress(team.id)
        xp = int(progress["xp"]) if progress else 0
        unlocked = available_titles_for_level(level_for_xp(xp))
        if title not in unlocked:
            await interaction.followup.send(
                "That title is not unlocked yet. Available titles: " + ", ".join(unlocked),
                ephemeral=True,
            )
            return
        await self.bot.db.set_team_title(team.id, title)
        await interaction.followup.send(f"Set **{team.name}** title to **{title}**.", ephemeral=True)

    @app_commands.command(name="sponsor_offers", description="Show your team's recent sponsor offers.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def sponsor_offers(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def show_selected(select_interaction: discord.Interaction, selected_team: Team):
                offers = await self.bot.db.team_sponsor_offers(selected_team.id, limit=8)
                await select_interaction.response.send_message(
                    embed=sponsor_offers_embed(selected_team, offers),
                    view=SponsorOfferActionView(self, select_interaction.user.id, selected_team, offers),
                    ephemeral=True,
                )

            await self._prompt_admin_team(interaction, show_selected, "Choose a team for sponsor offers.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return
        offers = await self.bot.db.team_sponsor_offers(team.id, limit=8)
        await interaction.followup.send(
            embed=sponsor_offers_embed(team, offers),
            view=SponsorOfferActionView(self, interaction.user.id, team, offers),
            ephemeral=True,
        )

    @app_commands.command(name="team_identity", description="Choose unlocked livery, emblem, garage decor and team intro.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_identity(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return
        progress = await self.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        identity = await self.bot.db.team_identity(team.id)
        view = TeamIdentityView(self, interaction.user.id, team, identity, level)
        await interaction.followup.send(embed=team_identity_embed(team, identity, level), view=view, ephemeral=True)

    @app_commands.command(name="track_records", description="Show track records and chaos marks.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def track_records(self, interaction: discord.Interaction, track_key: str | None = None):
        records = await self.bot.db.track_records(track_key)
        track_name = TRACKS[track_key].name if track_key in TRACKS else None
        await interaction.response.send_message(embed=track_records_embed(records, track_name))

    @app_commands.command(name="team_delete", description="Admin: delete a race team that is not in an open tournament.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_delete(self, interaction: discord.Interaction, team_id: int):
        if not await self._require_admin(interaction):
            return
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
        if await self.bot.db.team_in_open_tournament(team_id):
            await interaction.response.send_message(
                "That team is in an open tournament. Close the tournament before deleting it.",
                ephemeral=True,
            )
            return

        async def delete(confirm_interaction: discord.Interaction):
            try:
                await self.bot.db.delete_team(team_id)
            except Exception as exc:
                await confirm_interaction.response.edit_message(content=f"Team not deleted: {exc}", embed=None, view=None)
                return
            await audit_log(self.bot, "Team Deleted", f"#{team_id} {team.name}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(
                content=f"Deleted team **{team.name}** (`{team_id}`).",
                embed=None,
                view=None,
            )

        embed = discord.Embed(
            title="Confirm Team Delete",
            description=f"Delete **#{team.id} {team.name}**? This cannot be undone.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Delete Team", delete),
            ephemeral=True,
        )

    @app_commands.command(name="parts_wizard", description="Install and remove rod parts with a visual garage sheet.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def parts_wizard(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def open_selected(select_interaction: discord.Interaction, selected_team: Team):
                view = PartsWizardView(self, select_interaction.user.id, selected_team)
                file = view.garage_file()
                if file:
                    await select_interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
                else:
                    await select_interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

            await self._prompt_admin_team(interaction, open_selected, "Choose a team for parts wizard.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team:
            return

        view = PartsWizardView(self, interaction.user.id, team)
        file = view.garage_file()
        if file:
            await interaction.followup.send(
                embed=view.embed(has_sheet=True),
                file=file,
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=view.embed(has_sheet=False),
                view=view,
                ephemeral=True,
            )

    @app_commands.command(name="pit_crew_wizard", description="Assign pit crew members with buffs and debuffs.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def pit_crew_wizard(self, interaction: discord.Interaction, team_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        if is_admin(interaction) and team_id is None:
            async def open_selected(select_interaction: discord.Interaction, selected_team: Team):
                progress = await self.bot.db.team_progress(selected_team.id)
                level = level_for_xp(int(progress["xp"]) if progress else 0)
                view = PitCrewWizardView(self, select_interaction.user.id, selected_team, level)
                file = view.crew_file()
                if file:
                    await select_interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
                else:
                    await select_interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

            await self._prompt_admin_team(interaction, open_selected, "Choose a team for pit crew wizard.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team:
            return

        progress = await self.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        view = PitCrewWizardView(self, interaction.user.id, team, level)
        file = view.crew_file()
        if file:
            await interaction.followup.send(
                embed=view.embed(has_sheet=True),
                file=file,
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=view.embed(has_sheet=False),
                view=view,
                ephemeral=True,
            )

    @app_commands.command(name="team_add_part", description="Fit a custom part to a team rod.")
    @app_commands.autocomplete(team_id=team_autocomplete, part_key=add_part_autocomplete)
    async def team_add_part(self, interaction: discord.Interaction, team_id: int, part_key: str):
        if not await self._require_admin(interaction):
            return
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        if part_key not in PARTS:
            await interaction.response.send_message("Unknown part. Use `/parts_catalogue`.", ephemeral=True)
            return

        new_part = PARTS[part_key]
        existing_same_slot = [p for p in team.parts if PARTS.get(p) and PARTS[p].slot == new_part.slot]
        if existing_same_slot:
            await interaction.response.send_message(
                f"That rod already has a `{new_part.slot.value}` part fitted. Remove it first.",
                ephemeral=True,
            )
            return

        team.parts.append(part_key)
        await self.bot.db.update_team_parts(team_id, team.parts)
        await audit_log(self.bot, "Part Added", f"#{team_id} {team.name}: {new_part.name}", interaction.user)
        warning = ""
        if BuildService.is_illegal_part_key(part_key):
            risk = BuildService.illegal_disqualification_risk_percent(team)
            warning = f"\n⚠️ Illegal part fitted: this team now has {risk}% disqualification risk per race."
        await interaction.response.send_message(
            f"✅ Fitted **{new_part.name}** to **{team.name}**.{warning}",
            embed=Embeds.team_sheet(team),
            ephemeral=True,
        )

    @app_commands.command(name="team_remove_part", description="Remove a custom part from a team rod.")
    @app_commands.autocomplete(team_id=team_autocomplete, part_key=remove_part_autocomplete)
    async def team_remove_part(self, interaction: discord.Interaction, team_id: int, part_key: str):
        if not await self._require_admin(interaction):
            return
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        if part_key not in team.parts:
            await interaction.response.send_message("That team does not have that part fitted.", ephemeral=True)
            return

        team.parts.remove(part_key)
        await self.bot.db.update_team_parts(team_id, team.parts)
        await audit_log(self.bot, "Part Removed", f"#{team_id} {team.name}: {part_key}", interaction.user)
        await interaction.response.send_message(
            f"Removed `{part_key}` from **{team.name}**.",
            embed=Embeds.team_sheet(team),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamsCog(bot))
