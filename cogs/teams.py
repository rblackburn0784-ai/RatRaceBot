from dataclasses import dataclass

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
from services.crew_sheet import render_crew_sheet
from services.engagement import available_titles_for_level, level_for_xp, progress_embed, sponsor_offers_embed, track_records_embed
from services.formatting import Embeds
from services.garage_sheet import render_parts_sheet
from services.scrutineering import scrutineering_embed
from services.story import garage_summary_embed, hall_of_fame_embed, reputation_embed, rivalries_embed
from services.team_sheet import render_team_sheet
from services.views import ConfirmView, PaginatedTextView


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


def _ready_marker(value: object) -> str:
    return "Ready" if value else "Needed"


def _driver_stats_text(stats: DriverStats | None) -> str:
    if not stats:
        return (
            "Not set yet.\n"
            "Use six numbers for: Nerve, Handling, Aggression, Mechanics, Reflexes, Showmanship.\n"
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


class TeamDetailsModal(discord.ui.Modal):
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


class DriverStatsModal(discord.ui.Modal):
    def __init__(self, wizard: "TeamWizardView"):
        super().__init__(title="Driver Stats")
        self.wizard = wizard
        default = ""
        if wizard.state.stats:
            stats = wizard.state.stats
            default = f"{stats.nerve}, {stats.handling}, {stats.aggression}, {stats.mechanics}, {stats.reflexes}, {stats.showmanship}"
        self.stats_input = discord.ui.TextInput(
            label="Driver stat values",
            placeholder="Nerve, Handling, Aggression, Mechanics, Reflexes, Showmanship. Example: 4,4,4,4,4,4",
            default=default,
            max_length=90,
        )
        self.add_item(self.stats_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_parts = str(self.stats_input.value).replace("\n", ",").replace("/", ",").split(",")
        try:
            values = [int(part.strip()) for part in raw_parts if part.strip()]
            if len(values) != 6:
                raise ValueError("Enter six numbers: nerve, handling, aggression, mechanics, reflexes, showmanship.")
            stats = DriverStats(*values)
            stats.validate()
        except ValueError as exc:
            await interaction.response.send_message(f"Stats not saved: {exc}", ephemeral=True)
            return

        self.wizard.state.stats = stats
        await self.wizard.refresh(interaction)


class TeamWizardView(discord.ui.View):
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
        await interaction.response.send_modal(DriverStatsModal(self))

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
            content=f"Created team **{team.name}** as ID `{team_id}`.",
            embed=Embeds.team_sheet(team),
            view=self,
        )


class EditTeamWizardView(discord.ui.View):
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
        current = wizard.installed_part_key_for_slot(wizard.selected_slot)
        if current:
            part = PARTS[current]
            options = [discord.SelectOption(label=_shorten(f"Installed: {_part_label(current)}"), value=current)]
            disabled = True
        else:
            part_keys = wizard.available_part_keys_for_slot(wizard.selected_slot)
            if not part_keys:
                options = [discord.SelectOption(label="No parts available for this slot", value="none")]
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
            placeholder="Choose a part to install",
            min_values=1,
            max_values=1,
            options=options,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        self.wizard.selected_part_key = self.values[0]
        await self.wizard.refresh(interaction)


class PartsWizardView(discord.ui.View):
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
        can_install = bool(self.selected_part_key) and not current
        self.add_item(PartSlotSelect(self))
        self.add_item(PartChoiceSelect(self))

        install_button = discord.ui.Button(label="Install Part", style=discord.ButtonStyle.success, disabled=not can_install)
        install_button.callback = self.install_selected_part
        self.add_item(install_button)

        remove_button = discord.ui.Button(label="Remove Slot Part", style=discord.ButtonStyle.danger, disabled=not current)
        remove_button.callback = self.remove_slot_part
        self.add_item(remove_button)

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
                projected = min(100, current_risk + ILLEGAL_PART_DISQUALIFICATION_RISK)
                embed.add_field(
                    name="Illegal Part Warning",
                    value=(
                        f"This part adds +{ILLEGAL_PART_DISQUALIFICATION_RISK}% disqualification risk. "
                        f"If installed, this team will have {projected}% risk per race. Illegal risks stack."
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
        if self.installed_part_key_for_slot(self.selected_slot):
            await interaction.response.send_message("Remove the current part in that slot first.", ephemeral=True)
            return
        part = PARTS[self.selected_part_key]
        if part.slot != self.selected_slot:
            await interaction.response.send_message("That part does not fit the selected slot.", ephemeral=True)
            return
        parts = [*self.team.parts, self.selected_part_key]
        await self.cog.bot.db.update_team_parts(self.team.id, parts)
        await self.reload_team()
        self.selected_part_key = self.first_available_part_key()
        await self.refresh(interaction)

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


class PitCrewWizardView(discord.ui.View):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.selected_slot = CrewSlot.CREW_CHIEF
        self.selected_member_key: str | None = self.current_member_key_for_slot(self.selected_slot) or self.first_member_key()
        self.rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This pit crew wizard belongs to someone else.", ephemeral=True)
        return False

    def member_keys_for_slot(self, slot: CrewSlot) -> list[str]:
        return [key for key, member in CREW_MEMBERS.items() if member.slot == slot]

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
            mods = ", ".join(f"{key.title()} {value:+d}" for key, value in selected.modifiers.as_dict().items() if value)
            embed.add_field(name="Selected Member Effects", value=mods or "No stat modifiers", inline=False)
            embed.add_field(name="Crew Note", value=selected.description, inline=False)
        crew_stats = BuildService.crew_stats(self.team)
        crew_mods = ", ".join(f"{key.title()} {value:+d}" for key, value in crew_stats.as_dict().items() if value)
        embed.add_field(name="Overall Crew Stats", value=crew_mods or "No crew stat modifiers yet.", inline=False)
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


class MyTeamActionsView(discord.ui.View):
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
        view = PitCrewWizardView(self.cog, interaction.user.id, self.team)
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


class SponsorOfferActionView(discord.ui.View):
    def __init__(self, cog: "TeamsCog", owner_id: int, team: Team, offers):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.offer = next((offer for offer in offers if offer["status"] == "offered"), None)
        disabled = self.offer is None
        self.accept.disabled = disabled
        self.reject.disabled = disabled

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or is_admin(interaction):
            return True
        await interaction.response.send_message("These sponsor controls belong to another driver.", ephemeral=True)
        return False

    async def _set_status(self, interaction: discord.Interaction, status: str) -> None:
        if not self.offer:
            await interaction.response.send_message("No active sponsor offer to update.", ephemeral=True)
            return
        await self.cog.bot.db.update_sponsor_offer_status(int(self.offer["id"]), status)
        await audit_log(
            self.cog.bot,
            f"Sponsor Offer {status.title()}",
            f"#{self.team.id} {self.team.name}: {self.offer['sponsor_name']}",
            interaction.user,
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Sponsor offer **{status}**.", view=self)

    @discord.ui.button(label="Accept Latest Offer", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_status(interaction, "accepted")

    @discord.ui.button(label="Reject Latest Offer", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_status(interaction, "rejected")


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


class AdminTeamCommandSelectView(discord.ui.View):
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
                profile = await self.bot.db.team_profile(selected_team.id)
                rivalries = await self.bot.db.team_rivalries(selected_team.id, limit=1)
                in_open_tournament = await self.bot.db.team_in_open_tournament(selected_team.id)
                await select_interaction.response.send_message(
                    embed=garage_summary_embed(selected_team, profile, rivalries, in_open_tournament),
                    view=MyTeamActionsView(self, select_interaction.user.id, selected_team),
                    ephemeral=True,
                )

            await self._prompt_admin_team(interaction, show_selected, "Choose a team dashboard to view.")
            return
        team = await self._owned_or_admin_team(interaction, team_id)
        if not team or team.id is None:
            return

        profile = await self.bot.db.team_profile(team.id)
        rivalries = await self.bot.db.team_rivalries(team.id, limit=1)
        in_open_tournament = await self.bot.db.team_in_open_tournament(team.id)
        await interaction.followup.send(
            embed=garage_summary_embed(team, profile, rivalries, in_open_tournament),
            view=MyTeamActionsView(self, interaction.user.id, team),
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
                view = PitCrewWizardView(self, select_interaction.user.id, selected_team)
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

        view = PitCrewWizardView(self, interaction.user.id, team)
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
