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
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game!", ephemeral=True)
        temp_players = list(self.game.players)
        temp_players.remove(interaction.user)
        opponent = temp_players[0]
        players = [interaction.user, opponent] if opponent.bot else [opponent, interaction.user]
        await self.game.cog.base_minigame_cmd(type(self.game), interaction, players, opponent.bot)
        
    async def on_timeout(self):
        await super().on_timeout()
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
