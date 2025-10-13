import discord

from minigames.base import Minigame


class MinigameView(discord.ui.View):
    def __init__(self, game: Minigame):
        super().__init__(timeout=None)
        self.game = game
        if not self.game.is_finished():
            bump_button = discord.ui.Button(emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary, row=4)
            end_button = discord.ui.Button(emoji="🏳️", label="Surrender", style=discord.ButtonStyle.danger, row=4)
            bump_button.callback = self.bump
            end_button.callback = self.end
            self.add_item(bump_button)
            self.add_item(end_button)

    async def bump(self, interaction: discord.Interaction):
        assert interaction.message
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        self.message = await interaction.message.channel.send(content=await self.game.get_content(), embed=await self.game.get_embed(), view=await self.game.get_view())
        await interaction.message.delete()
    
    async def end(self, interaction: discord.Interaction):
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
        await self.game.cancel(interaction.user)
        new_view = await self.game.get_view()
        if new_view:
            new_view.stop()
        self.stop()
        await interaction.response.edit_message(content=await self.game.get_content(), embed=await self.game.get_embed(), view=new_view)
