import asyncio
import discord

from easychess.base import BaseChessGame


class BotsView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(emoji="♟️", label="Next Move", style=discord.ButtonStyle.success)
    async def move(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.game.move_engine()
        await self.game.update_message()
        
    @discord.ui.button(emoji="🏳️", label="End", style=discord.ButtonStyle.danger)
    async def end(self, interaction: discord.Interaction, _):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        self.stop()
        self.game.cancel(interaction.user)
        await interaction.response.pong()
        await self.game.update_message()
