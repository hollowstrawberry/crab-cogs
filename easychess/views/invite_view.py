import discord

from easychess.base import BaseChessGame


class InviteView(discord.ui.View):
    def __init__(self, game: BaseChessGame):
        super().__init__()
        self.game = game

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.primary)
    async def accept(self, interaction: discord.Interaction, _):
        assert isinstance(interaction.user, discord.Member)
        if interaction.user != self.game.players[0]:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        self.game.accept()
        await interaction.response.pong()
        await self.game.update_message()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        self.stop()
        await self.game.cancel(None)
        await interaction.message.delete()
