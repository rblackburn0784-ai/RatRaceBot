import discord


async def audit_log(bot, title: str, detail: str, actor: discord.abc.User | None = None) -> None:
    settings = getattr(bot, "settings", None)
    channel_id = getattr(settings, "audit_log_channel_id", None)
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.HTTPException, discord.NotFound):
            return

    actor_text = f"{actor} (`{actor.id}`)" if actor else "Unknown"
    embed = discord.Embed(title=title, description=detail[:3900], color=discord.Color.dark_gold())
    embed.set_footer(text=f"Actor: {actor_text}")
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        return
