import discord
from typing import Optional

from minigames.base import Minigame


class RematchView(discord.ui.View):
    def __init__(self, game: Minigame):
        super().__init__(timeout=300)
        self.game = game
        self.message: Optional[discord.Message] = None
        self.rematch_button = None
        if not self.game.is_cancelled():
            self.rematch_button = discord.ui.Button(label="Rematch", style=discord.ButtonStyle.green, row=4)
            self.rematch_button.callback = self.rematch
            self.add_item(self.rematch_button)

    async def rematch(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game! You should start a new one.", ephemeral=True)
        
        temp_players = list(self.game.players)
        temp_players.remove(interaction.user)
        opponent = temp_players[0]
        players = [interaction.user, opponent] if opponent.bot else [opponent, interaction.user]

        self.stop()
        await self.game.cog.base_minigame_cmd(type(self.game), interaction, players, opponent.bot)
        await self.on_timeout()
        
    async def on_timeout(self):
        if self.message:
            if self.rematch_button:
                self.remove_item(self.rematch_button)
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
