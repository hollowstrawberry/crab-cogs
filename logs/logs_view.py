import discord
from typing import Optional
from discord.ui import View
from redbot.core.bot import Red

from imagescanner.constants import VIEW_TIMEOUT
from logs.navigate_view import EphemeralNavigationView


class LogsView(View):
    def __init__(self, filepath: str, pages: list[str], bot: Red):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.filepath = filepath
        self.pages = pages
        self.bot = bot
        self.message: Optional[discord.Message] = None
        self.logs_button = discord.ui.Button(emoji="📜", label="Logs", style=discord.ButtonStyle.blurple)
        self.logs_button.callback = self.show_logs
        self.file_button = discord.ui.Button(emoji="📁", label="File", style=discord.ButtonStyle.gray)
        self.file_button.callback = self.show_file
        self.save_button = discord.ui.Button(emoji="📨", label="Save", style=discord.ButtonStyle.gray)
        self.save_button.callback = self.save_dm
        self.add_item(self.logs_button)
        self.add_item(self.file_button)
        self.add_item(self.save_button)

    async def check_owner(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            return True
        else:
            await interaction.response.send_message("You must be the bot owner to view the logs.", ephemeral=True)
            return False

    async def show_logs(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        if len(self.pages) > 1:
            view = EphemeralNavigationView(VIEW_TIMEOUT, self.pages, len(self.pages) - 1)
            await interaction.response.send_message(self.pages[-1], view=view, ephemeral=True)
        else:
            await interaction.response.send_message(self.pages[-1], ephemeral=True)

    async def show_file(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        file = discord.File(self.filepath, filename=f"red_logs_{int(interaction.created_at.timestamp())}.txt")
        await interaction.response.send_message(file=file, ephemeral=True)

    async def save_dm(self, interaction: discord.Interaction):
        if not await self.check_owner(interaction):
            return
        try:
            file = discord.File(self.filepath, filename=f"red_logs_{int(interaction.created_at.timestamp())}.txt")
            await interaction.user.send(file=file)
        except discord.Forbidden:
            await interaction.response.send_message("It appears you don't accept DMs, so I can't send you the logs file.", ephemeral=True)
        else:
            await interaction.response.send_message("Logs file sent to your DMs.", ephemeral=True)

    async def on_timeout(self) -> None:
        await super().on_timeout()
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
