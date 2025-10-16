import discord
from typing import Any, Awaitable, Callable, Optional


class ReplaceView(discord.ui.View):
    def __init__(self, cog, callback: Callable[..., Awaitable[Any]], author: discord.Member):
        super().__init__()
        self.cog = cog
        self.callback = callback
        self.author = author
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Yes, start a new game", style=discord.ButtonStyle.danger)
    async def replace(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert interaction.message
        if interaction.user != self.author:
            return await interaction.response.send_message("This confirmation message is not directed at you!", ephemeral=True)
        self.stop()
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        await self.callback()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert interaction.message
        if interaction.user != self.author:
            return await interaction.response.send_message("This confirmation message is not directed at you!", ephemeral=True)
        await interaction.message.delete()

    async def on_timeout(self):
        await super().on_timeout()
        if self.message:
            try:
                await self.message.delete()
            except discord.NotFound:
                pass
