import discord


def is_admin(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    if permissions and permissions.administrator:
        return True

    settings = getattr(interaction.client, "settings", None)
    admin_role_ids = getattr(settings, "admin_role_ids", set()) or set()
    if not admin_role_ids:
        return False

    roles = getattr(interaction.user, "roles", []) or []
    return any(getattr(role, "id", None) in admin_role_ids for role in roles)


async def deny_admin_only(interaction: discord.Interaction) -> None:
    message = "Only admins can use that command. Drivers can use `/menu`, `/status`, `/team_wizard`, `/team_edit_wizard`, `/parts_wizard`, `/pit_crew_wizard`, `/my_team`, `/scrutineering`, `/team_reputation`, `/team_rivalries`, `/team_progress`, `/team_title`, `/sponsor_offers`, `/track_records`, `/race_tracks`, `/track_cards`, and `/race_wizard`."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
