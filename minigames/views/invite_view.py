import discord

from minigames.base import Minigame


class InviteView(discord.ui.View):
    def __init__(self, game: Minigame):
        super().__init__()
        self.game = game

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.primary)
    async def accept(self, interaction: discord.Interaction, _):
        assert isinstance(interaction.user, discord.Member)
        if interaction.user != self.game.players[0]:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        self.game.accept(interaction.user)
        await interaction.response.edit_message(content=self.game.get_content(), embed=self.game.get_embed(), view=self.game.get_view())

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _):
        assert isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        self.game.cancel(interaction.user)
        self.stop()
        assert interaction.message
        await interaction.message.delete()
