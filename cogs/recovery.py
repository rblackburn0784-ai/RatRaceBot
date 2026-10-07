from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_VERSION
from data.defaults import WEATHER_CONDITIONS
from models.domain import Team
from services.access import deny_admin_only, is_admin
from services.audit import audit_log
from services.media import MediaRegistry
from services.race_report import send_race_report
from services.race_snapshot import restore_replay_snapshot
from services.recovery import RecoveryError
from services.streamer import RaceStreamer


EXPECTED_SLASH_COMMANDS = {
    "ratbot_init", "media_list", "parts_catalogue", "backup_database", "admin_panel", "ai_personalize_saved",
    "world", "menu", "status", "version",
    "race_tracks", "race_wizard", "race_quick", "race_demo", "race_replay", "track_cards",
    "admin_health", "validate_database", "undo_last_race", "reprocess_race", "correct_result",
    "restore_tournament", "repair_team_data", "restore_backup", "resume_interrupted_race",
    "team_create", "team_wizard", "team_edit_wizard", "team_list", "team_sheet", "team_reputation",
    "my_team", "scrutineering", "hall_of_fame", "team_rivalries", "team_progress", "team_title",
    "sponsor_offers", "team_identity", "track_records", "team_delete", "parts_wizard",
    "pit_crew_wizard", "team_add_part", "team_remove_part",
    "tournament_create", "tournament_wizard", "tournament_add_team", "tournament_standings",
    "tournament_stats", "season_history", "championship", "tournament_start_race",
    "tournament_next_race", "tournament_schedule", "tournament_close",
    "world_events", "world_event_choose", "rivalry_story",
}


RESULT_STATUS_CHOICES = [
    app_commands.Choice(name="Keep current status", value="keep"),
    app_commands.Choice(name="Official finisher", value="finish"),
    app_commands.Choice(name="DNF", value="dnf"),
    app_commands.Choice(name="Disqualified", value="dsq"),
]


class RecoveryCog(commands.Cog):
    """v0.5.1 administration, health and recovery tools."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    async def _require_idle(self) -> None:
        snapshot = await self.bot.race_activity.snapshot()
        if snapshot["active_team_ids"] or snapshot["lobby_team_ids"]:
            raise RecoveryError(
                "Recovery is blocked while a race or lobby is active. Finish/cancel it first so the database cannot change underneath recovery."
            )

    @staticmethod
    def _confirm_message(action: str) -> str:
        return (
            f"This is a destructive recovery action. Run the command again with confirm:true to {action}. "
            "Checkpoint-based race recovery restores the whole pre-race database state, so later DB edits can also roll back; a safety backup is created first."
        )

    def _media_summary(self) -> tuple[int, int]:
        self.media.load()
        registered = set()
        for section in ("gifs", "audio"):
            for raw in self.media.data.get(section, {}).values():
                registered.add(Path(raw))
        direct = set(Path("assets/gifs").glob("*.gif")) | {
            path for path in Path("assets/audio").glob("*") if path.is_file()
        }
        expected = registered | direct
        available = sum(1 for path in expected if path.exists())
        return available, len(expected)

    @app_commands.command(name="admin_health", description="Admin: release-candidate health and diagnostics screen.")
    async def admin_health(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        validation = await self.bot.recovery.validate_database()
        activity = await self.bot.race_activity.snapshot()
        tournament = await self.bot.db.current_tournament()
        backups = self.bot.recovery.list_backups()
        available_media, total_media = self._media_summary()
        loaded_commands = {command.name for command in self.bot.tree.get_commands()}
        missing_commands = sorted(EXPECTED_SLASH_COMMANDS - loaded_commands)
        extra_commands = sorted(loaded_commands - EXPECTED_SLASH_COMMANDS)
        commands_ok = not missing_commands and not extra_commands
        release_health = {}
        health_path = Path("data/release_health.json")
        if health_path.exists():
            try:
                release_health = json.loads(health_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                release_health = {}
        db_icon = "✅" if validation["ok"] else "❌"
        active_text = f"{len(activity['active_team_ids'])} team(s)" if activity["active_team_ids"] else "None"
        open_tournament = tournament["name"] if tournament else "None"
        balance_status = str(release_health.get("balance_lab", "UNKNOWN")).upper()
        balance_icon = "✅" if balance_status == "PASS" else "⚠️"
        test_status = str(release_health.get("tests", "UNKNOWN")).upper()
        py312_status = str(release_health.get("python_312", test_status)).upper()
        py313_status = str(release_health.get("python_313", test_status)).upper()
        interrupted = await self.bot.recovery.interrupted_races()

        release_version = str(release_health.get("version", "UNKNOWN"))
        release_version_ok = release_version == str(BOT_VERSION)
        overall_ok = (
            validation["ok"]
            and commands_ok
            and balance_status == "PASS"
            and py312_status == "PASS"
            and py313_status == "PASS"
            and release_version_ok
        )
        embed = discord.Embed(
            title="🛠️ Rat Rod Admin Health",
            description=f"v{BOT_VERSION} runtime diagnostics",
            color=discord.Color.green() if overall_ok else discord.Color.orange(),
        )
        command_icon = "✅" if commands_ok else "❌"
        version_icon = "✅" if release_version_ok else "⚠️"
        embed.add_field(
            name="Core",
            value=(
                f"Bot: ✅\nDatabase: {db_icon}\n"
                f"Commands: {command_icon} **{len(loaded_commands)}/{len(EXPECTED_SLASH_COMMANDS)} expected**\n"
                f"Media: **{available_media}/{total_media} available**\n"
                f"Build Metadata: {version_icon} **{release_version}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Live State",
            value=(
                f"Open Tournament: **{open_tournament}**\nActive Race: **{active_text}**\n"
                f"Backups: **{len(backups)}**\nInterrupted Races: **{len(interrupted)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Release Gate",
            value=(
                f"Tests Python 3.12: **{py312_status}**\n"
                f"Tests Python 3.13: **{py313_status}**\n"
                f"Balance Lab: {balance_icon} **{balance_status}**\n"
                f"Database Tables Checked: **{validation.get('tables_checked', 0)}**\n"
                f"Database Issues: **{len(validation['issues'])}** · Warnings: **{len(validation['warnings'])}**"
            ),
            inline=False,
        )
        if missing_commands or extra_commands:
            details = []
            if missing_commands:
                details.append("Missing: " + ", ".join(f"`/{name}`" for name in missing_commands))
            if extra_commands:
                details.append("Unexpected: " + ", ".join(f"`/{name}`" for name in extra_commands))
            embed.add_field(name="Command Registration", value="\n".join(details)[:1024], inline=False)
        if not release_version_ok:
            embed.add_field(
                name="Build Metadata",
                value=f"Runtime is v{BOT_VERSION}, but release_health.json reports {release_version}.",
                inline=False,
            )
        if validation["issues"]:
            embed.add_field(name="Database Problems", value="\n".join(f"• {item}" for item in validation["issues"][:8])[:1024], inline=False)
        if validation["warnings"]:
            embed.add_field(name="Warnings", value="\n".join(f"• {item}" for item in validation["warnings"][:8])[:1024], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="validate_database", description="Admin: run SQLite and Rat Rod data-integrity checks.")
    async def validate_database(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        report = await self.bot.recovery.validate_database()
        embed = discord.Embed(
            title="Database Validation",
            description="✅ PASS" if report["ok"] else "❌ PROBLEMS FOUND",
            color=discord.Color.green() if report["ok"] else discord.Color.red(),
        )
        embed.add_field(name="SQLite", value=", ".join(report["integrity"]), inline=False)
        embed.add_field(name="Issues", value="\n".join(f"• {item}" for item in report["issues"][:15]) if report["issues"] else "None", inline=False)
        embed.add_field(name="Warnings", value="\n".join(f"• {item}" for item in report["warnings"][:15]) if report["warnings"] else "None", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="undo_last_race", description="Admin: restore the automatic checkpoint from before the latest race.")
    async def undo_last_race(self, interaction: discord.Interaction, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message("undo the latest race"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            async with self.bot.recovery_lock:
                result = await self.bot.recovery.undo_last_race()
        except RecoveryError as exc:
            await interaction.followup.send(f"Undo refused: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Undo Last Race", f"Race #{result['race_id']} restored from checkpoint", interaction.user)
        await interaction.followup.send(f"✅ Race **#{result['race_id']}** was undone. Safety backup: {result['safety']}", ephemeral=True)

    @app_commands.command(name="reprocess_race", description="Admin: safely rebuild the latest race from its pre-race checkpoint.")
    async def reprocess_race(self, interaction: discord.Interaction, race_id: int, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message(f"reprocess race #{race_id}"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            async with self.bot.recovery_lock:
                await self.bot.recovery.reprocess_latest_race(race_id)
        except (RecoveryError, ValueError) as exc:
            await interaction.followup.send(f"Reprocess refused: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Race Reprocessed", f"Race #{race_id}", interaction.user)
        await interaction.followup.send(f"✅ Race **#{race_id}** was rebuilt from its automatic pre-race checkpoint and processed once.", ephemeral=True)

    @app_commands.command(name="correct_result", description="Admin: correct classification for the latest recoverable race and reprocess it.")
    @app_commands.choices(status=RESULT_STATUS_CHOICES)
    async def correct_result(self, interaction: discord.Interaction, race_id: int, team_id: int, new_position: int, status: app_commands.Choice[str], confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message(f"correct race #{race_id}"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            async with self.bot.recovery_lock:
                await self.bot.recovery.correct_latest_result(race_id, team_id, new_position, status.value)
        except (RecoveryError, ValueError) as exc:
            await interaction.followup.send(f"Correction refused: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Race Result Corrected", f"Race #{race_id}; team #{team_id}; P{new_position}; {status.value}", interaction.user)
        await interaction.followup.send(f"✅ Corrected race **#{race_id}** for team **#{team_id}** and rebuilt that race's downstream effects.", ephemeral=True)

    @app_commands.command(name="restore_tournament", description="Admin: reopen a closed tournament and remove its final history snapshot.")
    async def restore_tournament(self, interaction: discord.Interaction, tournament_id: int, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message(f"restore tournament #{tournament_id}"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            async with self.bot.recovery_lock:
                result = await self.bot.recovery.restore_tournament(tournament_id)
        except RecoveryError as exc:
            await interaction.followup.send(f"Restore refused: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Tournament Restored", f"#{tournament_id} {result['name']}", interaction.user)
        if result.get("already_open"):
            await interaction.followup.send("That tournament is already open; nothing changed.", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Restored **{result['name']}** (#{tournament_id}) to open status. Safety backup: {result['safety']}", ephemeral=True)

    @app_commands.command(name="repair_team_data", description="Admin: repair malformed/retired team loadout data without changing names or flavour text.")
    async def repair_team_data(self, interaction: discord.Interaction, team_id: int, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message(f"repair team #{team_id}"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            if await self.bot.race_activity.is_team_busy(team_id):
                raise RecoveryError("That team is currently in a race or lobby.")
            async with self.bot.recovery_lock:
                result = await self.bot.recovery.repair_team_data(team_id)
        except RecoveryError as exc:
            await interaction.followup.send(f"Repair refused: {exc}", ephemeral=True)
            return
        fixes = result["fixes"]
        await audit_log(self.bot, "Team Data Repaired", f"Team #{team_id}: {', '.join(fixes) or 'no changes'}", interaction.user)
        detail = f"Repairs: {', '.join(fixes)}." if fixes else "No repair was needed."
        await interaction.followup.send(f"✅ Team **#{team_id}** checked. {detail} Safety backup: {result['safety']}", ephemeral=True)

    @app_commands.command(name="restore_backup", description="Admin: replace the live database with a named backup from backups/.")
    async def restore_backup(self, interaction: discord.Interaction, backup_name: str, confirm: bool = False):
        if not confirm:
            await interaction.response.send_message(self._confirm_message(f"restore backup {backup_name}"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            async with self.bot.recovery_lock:
                source, safety = await self.bot.recovery.restore_backup(backup_name)
        except RecoveryError as exc:
            await interaction.followup.send(f"Restore refused: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Database Backup Restored", str(source), interaction.user)
        await interaction.followup.send(f"✅ Restored **{source.name}** after integrity validation. Pre-restore safety backup: {safety}", ephemeral=True)

    @app_commands.command(name="resume_interrupted_race", description="Admin: continue saved race presentation without resimulating the result.")
    async def resume_interrupted_race(self, interaction: discord.Interaction, race_id: int | None = None):
        await interaction.response.defer(ephemeral=True)
        try:
            await self._require_idle()
            if race_id is None:
                rows = await self.bot.recovery.interrupted_races()
                if not rows:
                    raise RecoveryError("No interrupted race presentation is recorded.")
                race_id = int(rows[0]["race_id"])
            state = await self.bot.recovery.presentation_state(race_id)
            if not state:
                raise RecoveryError("That race has no resumable v0.4.9 presentation state.")
            if str(state["status"]) == "complete":
                raise RecoveryError("That race presentation is already marked complete.")
            race = await self.bot.db.get_race(race_id)
            if not race:
                raise RecoveryError("Saved race not found.")
            events = [self.bot.recovery.event_from_dict(item) for item in json.loads(race["events_json"])]
            results = [self.bot.recovery.result_from_dict(item) for item in json.loads(race["results_json"])]
            teams: list[Team] = []
            laps = max((event.lap for event in events), default=10)
            weather_name = "Unknown"
            if race["replay_json"]:
                replay = json.loads(race["replay_json"])
                teams, laps, _damage, weather_key, _rng = restore_replay_snapshot(replay)
                weather = WEATHER_CONDITIONS.get(weather_key) if weather_key else None
                weather_name = weather.name if weather else str(weather_key or "Unknown")
            else:
                for result in results:
                    team = await self.bot.db.get_team(int(result.team_id))
                    if team:
                        teams.append(team)
            start_index = int(state["last_event_index"]) + 1
            await self.bot.recovery.mark_presentation(race_id, start_index - 1, "streaming")
            async def progress_callback(index: int) -> None:
                await self.bot.recovery.mark_presentation(race_id, index, "streaming")
            await interaction.followup.send(f"Resuming race **#{race_id}** from event **{start_index + 1}/{len(events)}** in this channel.", ephemeral=True)
            await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events, start_index=start_index, progress_callback=progress_callback)
            await self.bot.recovery.mark_presentation(race_id, len(events) - 1, "complete")
            await send_race_report(
                channel=interaction.channel, db=self.bot.db, track_key=str(race["track_key"]), race_id=race_id,
                teams=teams, results=results, events=events, weather_name=weather_name,
                title=f"Resumed Race #{race_id} Results", race_laps=laps, award_rewards=False,
                reward_embeds_override=[], persisted_report=True,
            )
            await audit_log(self.bot, "Interrupted Race Resumed", f"Race #{race_id} from event {start_index}", interaction.user)
        except (RecoveryError, json.JSONDecodeError, ValueError, discord.HTTPException, OSError) as exc:
            if race_id is not None:
                state = await self.bot.recovery.presentation_state(race_id)
                last_index = int(state["last_event_index"]) if state else -1
                await self.bot.recovery.mark_presentation(race_id, last_index, "interrupted")
            await interaction.followup.send(f"Resume failed: {exc}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RecoveryCog(bot))
