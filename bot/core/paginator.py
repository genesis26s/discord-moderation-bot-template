"""Simple paginator for long embeds/lists."""
from __future__ import annotations

import discord


class Paginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], *, author_id: int, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError("pages cannot be empty")
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self._update()

    def _update(self) -> None:
        self.page_label.label = f"{self.index + 1}/{len(self.pages)}"
        self.prev.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This paginator is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if self.index > 0:
            self.index -= 1
            self._update()
            await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if self.index < len(self.pages) - 1:
            self.index += 1
            self._update()
            await interaction.response.edit_message(embed=self.pages[self.index], view=self)
