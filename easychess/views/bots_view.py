import asyncio
import discord

from easychess.base import BaseChessGame
from easychess.views.thinking_view import ThinkingView


class BotsView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(emoji="♟️", label="Next Move", style=discord.ButtonStyle.success)
    async def move(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=ThinkingView())
        await self.game.move_engine()
        await self.game.update_message(interaction)
        
    @discord.ui.button(emoji="🏳️", label="End", style=discord.ButtonStyle.danger)
    async def end(self, interaction: discord.Interaction, _):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        self.stop()
        self.game.cancel(interaction.user)
        await self.game.update_message(interaction)
