from typing import Any, Awaitable, Callable
import discord


class ReplaceView(discord.ui.View):
    def __init__(self, cog, callback: Callable[..., Awaitable[Any]], author: discord.Member, channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.callback = callback
        self.author = author
        self.channel = channel

    @discord.ui.button(label="Yes, start a new game", style=discord.ButtonStyle.danger)
    async def replace(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert interaction.message
        if interaction.user != self.author:
            return await interaction.response.send_message("This confirmation message is not directed at you!", ephemeral=True)
        await interaction.message.delete()
        await self.callback()
        
