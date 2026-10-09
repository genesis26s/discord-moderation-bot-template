"""Custom embed builder command."""
from __future__ import annotations

import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import is_guild_admin

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _parse_color(raw: str, default: int = 0x5865F2) -> int:
    if not raw:
        return default
    m = HEX_RE.match(raw.strip())
    if not m:
        return default
    return int(m.group(1), 16)


class EmbedModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        target_channel: discord.TextChannel,
        edit_message: Optional[discord.Message] = None,
    ):
        super().__init__(title=("Edit Embed" if edit_message else "Create Embed")[:45])
        self.target_channel = target_channel
        self.edit_message = edit_message

        # Prefill when editing
        existing_title = ""
        existing_desc = ""
        existing_color = ""
        existing_image = ""
        existing_footer = ""
        if edit_message and edit_message.embeds:
            e = edit_message.embeds[0]
            existing_title = e.title or ""
            existing_desc = e.description or ""
            if e.color is not None and e.color.value is not None:
                existing_color = "#{:06X}".format(e.color.value)
            if e.image and e.image.url:
                existing_image = e.image.url
            if e.footer and e.footer.text:
                existing_footer = e.footer.text

        self.title_input = discord.ui.TextInput(
            label="Title",
            default=existing_title,
            max_length=256,
            required=False,
        )
        self.desc_input = discord.ui.TextInput(
            label="Description",
            default=existing_desc,
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=False,
        )
        self.color_input = discord.ui.TextInput(
            label="Color (hex, e.g. #5865F2)",
            default=existing_color,
            max_length=9,
            required=False,
        )
        self.image_input = discord.ui.TextInput(
            label="Image URL",
            default=existing_image,
            max_length=500,
            required=False,
        )
        self.footer_input = discord.ui.TextInput(
            label="Footer",
            default=existing_footer,
            max_length=200,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)
        self.add_item(self.image_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = (self.title_input.value or "").strip()
        desc = (self.desc_input.value or "").strip()
        color_raw = (self.color_input.value or "").strip()
        image = (self.image_input.value or "").strip()
        footer = (self.footer_input.value or "").strip()

        if not (title or desc or image):
            return await interaction.response.send_message(
                "Provide at least a title, description, or image.", ephemeral=True
            )

        color = _parse_color(color_raw)

        embed = discord.Embed(
            title=title or None,
            description=desc or None,
            color=color,
        )
        if image:
            embed.set_image(url=image)
        if footer:
            embed.set_footer(text=footer)

        await interaction.response.defer(ephemeral=True)
        try:
            if self.edit_message is not None:
                await self.edit_message.edit(embed=embed)
                await interaction.followup.send(
                    "Embed updated in " + self.target_channel.mention + ".", ephemeral=True
                )
            else:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(
                    "Embed posted in " + self.target_channel.mention + ".", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to post in that channel.", ephemeral=True
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                "Failed to send: `" + str(exc)[:150] + "`", ephemeral=True
            )


class Embed(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="embed", description="Post or edit a custom embed.")
    @app_commands.describe(
        channel="Channel to post in (defaults to current channel)",
        edit_message_id="Optional: ID of a message to edit instead of posting new",
    )
    @is_guild_admin()
    async def embed(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        edit_message_id: Optional[str] = None,
    ) -> None:
        if interaction.guild is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message(
                "Invalid channel.", ephemeral=True
            )

        edit_message = None
        if edit_message_id:
            try:
                msg_id = int(edit_message_id.strip())
            except ValueError:
                return await interaction.response.send_message(
                    "Message ID must be numeric.", ephemeral=True
                )
            try:
                edit_message = await target.fetch_message(msg_id)
            except discord.NotFound:
                return await interaction.response.send_message(
                    "Message not found in " + target.mention + ".", ephemeral=True
                )
            except discord.HTTPException as exc:
                return await interaction.response.send_message(
                    "Couldn't fetch message: `" + str(exc)[:150] + "`", ephemeral=True
                )
            bot_id = self.bot.user.id if self.bot.user else 0
            if edit_message.author.id != bot_id:
                return await interaction.response.send_message(
                    "I can only edit my own messages.", ephemeral=True
                )

        await interaction.response.send_modal(
            EmbedModal(target_channel=target, edit_message=edit_message)
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Embed(bot))
