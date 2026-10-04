"""Reusable views: confirmations, error toasts."""
from __future__ import annotations

from typing import Awaitable, Callable

import discord


class ConfirmView(discord.ui.View):
    def __init__(self, *, author_id: int, confirm_label: str = "Confirm", cancel_label: str = "Cancel", timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.result: bool | None = None
        self.confirm.label = confirm_label
        self.cancel.label = cancel_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _btn: discord.ui.Button) -> None:
        self.result = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _btn: discord.ui.Button) -> None:
        self.result = False
        await interaction.response.defer()
        self.stop()


class ModalText(discord.ui.Modal):
    def __init__(self, title: str, inputs: list[tuple[str, str, bool, str | None, int | None]]) -> None:
        super().__init__(title=title)
        for label, field_id, required, default, max_length in inputs:
            self.add_item(
                discord.ui.TextInput(
                    label=label,
                    custom_id=field_id,
                    required=required,
                    default=default,
                    max_length=max_length,
                )
            )
