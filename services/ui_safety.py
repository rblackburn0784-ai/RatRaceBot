from __future__ import annotations

import logging

import discord


LOGGER = logging.getLogger(__name__)


async def safe_reply(
    interaction: discord.Interaction,
    message: str,
    *,
    ephemeral: bool = True,
) -> None:
    """Acknowledge an interaction whether or not another callback already responded."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(message, ephemeral=ephemeral)
    except (discord.HTTPException, discord.NotFound):
        # The interaction token itself may have expired. Logging is preferable to
        # throwing a second exception from an error handler.
        LOGGER.warning("Could not acknowledge Discord interaction %s", getattr(interaction, "id", "unknown"))


class ReliableView(discord.ui.View):
    """Shared UI error boundary for all interactive Rat Rod views."""

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        LOGGER.exception(
            "UI callback failed in %s for item %s",
            self.__class__.__name__,
            getattr(item, "custom_id", None) or getattr(item, "label", None) or item.__class__.__name__,
            exc_info=error,
        )
        await safe_reply(
            interaction,
            "That control could not be completed. Nothing else was changed. Refresh this screen or use `/menu` and try again.",
            ephemeral=True,
        )


class OneShotReliableView(ReliableView):
    """Reliable view helper for actions that must never execute twice."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._action_started = False

    def begin_once(self) -> bool:
        if self._action_started:
            return False
        self._action_started = True
        return True
