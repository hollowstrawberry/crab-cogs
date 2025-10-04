import logging
import discord
from typing import Optional
from discord.ext import commands

from minigames.base import Minigame


class RematchView(discord.ui.View):
    def __init__(self, game: Minigame):
        super().__init__(timeout=None)
        self.game = game
        self.message: Optional[discord.Message] = None
        if not self.game.is_cancelled():
            button = discord.ui.Button(label="Rematch", style=discord.ButtonStyle.green, row=4)
            button.callback = self.rematch
            self.add_item(button)

    async def rematch(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member) and self.game.command
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game!", ephemeral=True)
        players = list(self.game.players)
        players.remove(interaction.user)
        interaction.command = self.game.command # type: ignore
        ctx = await commands.Context.from_interaction(interaction)
        await self.game.command(ctx, players[0])
        
    async def on_timeout(self):
        await super().on_timeout()
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
