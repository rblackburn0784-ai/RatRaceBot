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
    """Shared UI error boundary plus best-effort stale-control cleanup."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bound_message = None

    def bind_message(self, message) -> None:
        self._bound_message = message

    def _disable(self) -> None:
        for item in self.children:
            item.disabled = True

    async def _scheduled_task(self, item, interaction):
        # discord.py does not automatically retain the source message on View.
        # Capture it on every component interaction so timeout cleanup can edit it.
        message = getattr(interaction, "message", None)
        if message is not None:
            self._bound_message = message
        return await super()._scheduled_task(item, interaction)

    async def on_timeout(self) -> None:
        self._disable()
        if self._bound_message is None:
            return
        try:
            await self._bound_message.edit(view=self)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            LOGGER.info("Could not disable timed-out %s controls in Discord", self.__class__.__name__)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        LOGGER.error(
            "UI callback failed in %s for item %s",
            self.__class__.__name__,
            getattr(item, "custom_id", None) or getattr(item, "label", None) or item.__class__.__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        await safe_reply(
            interaction,
            "That control could not be completed. Refresh this screen or use `/menu` or `/world` and try again.",
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


class ReliableModal(discord.ui.Modal):
    """Shared error boundary for Discord modal submissions."""

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        LOGGER.error(
            "Modal submission failed in %s",
            self.__class__.__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        await safe_reply(
            interaction,
            "That form could not be completed. Reopen the screen and try again.",
            ephemeral=True,
        )


async def bind_view_to_interaction(view: ReliableView, interaction: discord.Interaction) -> None:
    """Bind a newly-sent View to its message so timeout can visibly disable it."""
    try:
        message = getattr(interaction, "message", None)
        if message is None:
            message = await interaction.original_response()
        view.bind_message(message)
    except (discord.HTTPException, discord.NotFound, discord.Forbidden, AttributeError):
        LOGGER.debug("Could not bind %s to an interaction message", view.__class__.__name__)
