


import discord

from simplecasino.base import BasePokerGame


class PokerRematchView(discord.ui.View):
    def __init__(self, game: BasePokerGame):
        super().__init__(timeout=300)
        self.game = game

    @discord.ui.button(label="Play another round", style=discord.ButtonStyle.primary)
    async def rematch(self, interaction: discord.Interaction, _):
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message("You didn't participate in this game, but you could start a new one.", ephemeral=True)
        members = [self.game.channel.guild.get_member(uid) for uid in self.game.players_ids]
        members = [m for m in members if m]
        if len(members) < 2:
            return await interaction.response.send_message("Failed to start the game as some players couldn't be found.", ephemeral=True)
        members_shifted = members[1:] + [members[0]]
        success = await self.game.cog.poker(interaction, members_shifted, self.game.minimum_bet)
        if success:
            self.stop()
            await self.on_timeout()

    async def on_timeout(self) -> None:
        await super().on_timeout()
        if self.game.message:
            try:
                await self.game.message.edit(view=None)
            except discord.NotFound:
                pass
