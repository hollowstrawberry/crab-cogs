import discord

from minigames.minigame import Minigame


class GameView(discord.ui.View):
    def __init__(self, game: Minigame):
        super().__init__()
        self.game = game
        if not self.game.is_finished():
            bump_button = discord.ui.Button(emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary, row=4)
            end_button = discord.ui.Button(emoji="🛑", label="End", style=discord.ButtonStyle.danger, row=4)
            bump_button.callback = self.bump
            end_button.callback = self.end
            self.add_item(bump_button)
            self.add_item(end_button)

    async def bump(self, interaction: discord.Interaction):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        await interaction.message.delete()
        self.message = await interaction.message.channel.send(content=self.game.get_content(), embed=self.game.get_embed(), view=self.game.get_view())
    
    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players and not interaction.channel.permissions_for(interaction.user).manage_messages:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        self.game.end()
        new_view = self.game.get_view()
        new_view.stop()
        self.stop()
        await interaction.response.edit_message(content=self.game.get_content(), embed=self.game.get_embed(), view=new_view)
