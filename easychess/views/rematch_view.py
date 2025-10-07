import discord

from easychess.base import BaseChessGame


class RematchView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__(timeout=300)
        self.game = game

    @discord.ui.button(label="Rematch", style=discord.ButtonStyle.green)
    async def rematch(self, interaction: discord.Interaction, _):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game! You should start a new one.", ephemeral=True)
        
        temp_players = list(self.game.players)
        temp_players.remove(interaction.user)
        opponent = temp_players[0]

        self.stop()
        await self.game.cog.chess_new(interaction, opponent, self.game.limit.depth)
        await self.on_timeout()
        
    async def on_timeout(self):
        if self.game.message:
            try:
                await self.game.message.edit(view=None)
            except discord.NotFound:
                pass
