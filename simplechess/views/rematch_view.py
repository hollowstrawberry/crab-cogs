import discord
from typing import Optional

from simplechess.base import BaseChessGame

MAX_BUTTON_LABEL = 80


class RematchView(discord.ui.View):
    def __init__(self, game: BaseChessGame, currency_name: str):
        super().__init__(timeout=300)
        self.game = game
        self.rematch_button = None
        if not self.game.is_cancelled():
            if game.bet == 0 or any(player.bot for player in self.game.players):
                label = "Rematch"
            else:
                label = f"Rematch and bet {game.bet} {currency_name}"[:MAX_BUTTON_LABEL]
            self.rematch_button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, row=4)
            self.rematch_button.callback = self.rematch
            self.add_item(self.rematch_button)

    async def rematch(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game! You should start a new one.", ephemeral=True)
        
        temp_players = list(self.game.players)
        temp_players.remove(interaction.user)
        opponent = temp_players[0]

        self.stop()
        await self.game.cog.chess_new(interaction, opponent, self.game.bet)
        await self.on_timeout()
        
    async def on_timeout(self):
        if self.game.message:
            try:
                await self.game.message.edit(view=None)
            except discord.NotFound:
                pass
