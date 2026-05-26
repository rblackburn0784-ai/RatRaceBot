import discord


def is_admin(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


async def deny_admin_only(interaction: discord.Interaction) -> None:
    message = "Only admins can use that command. Drivers can use `/team_wizard`, `/team_edit_wizard`, and `/parts_wizard`."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
