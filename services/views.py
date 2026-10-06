from collections.abc import Awaitable, Callable

import discord

from services.ui_safety import OneShotReliableView, ReliableView, safe_reply


class PaginatedTextView(ReliableView):
    def __init__(self, owner_id: int, title: str, lines: list[str], *, per_page: int = 10):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.title = title
        self.lines = lines or ["Nothing to show."]
        self.per_page = max(1, per_page)
        self.page = 0
        self._sync_buttons()

    @property
    def page_count(self) -> int:
        return max(1, (len(self.lines) + self.per_page - 1) // self.per_page)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This page control belongs to someone else.", ephemeral=True)
        return False

    def embed(self) -> discord.Embed:
        start = self.page * self.per_page
        page_lines = self.lines[start:start + self.per_page]
        embed = discord.Embed(title=self.title, description="\n".join(page_lines)[:4000])
        embed.set_footer(text=f"Page {self.page + 1}/{self.page_count}")
        return embed

    def _sync_buttons(self) -> None:
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.page_count - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.page_count - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class ConfirmView(OneShotReliableView):
    def __init__(
        self,
        owner_id: int,
        confirm_label: str,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        *,
        danger: bool = True,
    ):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.on_confirm = on_confirm
        self.confirm.label = confirm_label[:80]
        self.confirm.style = discord.ButtonStyle.danger if danger else discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This confirmation belongs to someone else.", ephemeral=True)
        return False

    def _disable(self) -> None:
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.begin_once():
            await safe_reply(interaction, "That confirmation has already been used. No second action was taken.")
            return
        self._disable()
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._action_started:
            await safe_reply(interaction, "That confirmation has already been used.")
            return
        self._action_started = True
        self._disable()
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=self)
