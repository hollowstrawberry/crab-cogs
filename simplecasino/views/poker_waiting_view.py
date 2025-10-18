


import discord
from redbot.core import bank

from simplecasino.base import BasePokerGame
from simplecasino.utils import PokerState


class PokerWaitingView(discord.ui.View):
    def __init__(self, game: BasePokerGame):
        super().__init__(timeout=None)
        self.game = game
        self.join_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} join",
            label="Join",
            style=discord.ButtonStyle.success
        )
        self.leave_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} leave",
            label="Leave",
            style=discord.ButtonStyle.secondary,
            disabled=len(game.players_ids) == 1
        )
        self.start_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} start",
            label="Start",
            style=discord.ButtonStyle.primary
        )
        self.cancel_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} cancel",
            label="Cancel",
            style=discord.ButtonStyle.danger
        )
        self.join_button.callback = self.join
        self.leave_button.callback = self.leave
        self.start_button.callback = self.start
        self.cancel_button.callback = self.cancel
        self.add_item(self.join_button)
        self.add_item(self.leave_button)
        self.add_item(self.start_button)
        self.add_item(self.cancel_button)

    async def join(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        success, message = self.game.try_add_player(interaction.user.id)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        if not await bank.can_spend(interaction.user, self.game.minimum_bet):
            currency_name = await bank.get_currency_name(interaction.guild)
            return await interaction.response.send_message(f"You need to own at least {self.game.minimum_bet} {currency_name} to join.", ephemeral=True)
        self.leave_button.disabled = True
        await interaction.response.edit_message(embed=await self.game.get_embed(), view=self)
    
    async def leave(self, interaction: discord.Interaction):
        success, message = self.game.try_remove_player(interaction.user.id)
        if not success:
            return await interaction.response.send_message(message, ephemeral=True)
        self.leave_button.disabled = len(self.game.players_ids) == 1
        await interaction.response.edit_message(embed=await self.game.get_embed(), view=self)

    async def start(self, interaction: discord.Interaction):
        assert interaction.guild
        if len(self.game.players_ids) < 2:
            return await interaction.response.send_message("The game needs at least 2 players.", ephemeral=True)
        if interaction.user.id != self.game.players_ids[0]:
            return await interaction.response.send_message("Only the dealer can start the game.", ephemeral=True)
        if self.game.state != PokerState.WaitingForPlayers:
            return await interaction.response.send_message("The game already started.", ephemeral=True)
        for pid in self.game.players_ids:
            member = interaction.guild.get_member(pid)
            if not member:
                return await interaction.response.send_message(f"There was a problem starting the game: <@{pid}> could not be found.", ephemeral=True)
            if not await bank.can_spend(member, self.game.minimum_bet):
                currency_name = await bank.get_currency_name(interaction.guild)
                return await interaction.response.send_message(f"{member.mention} doesn't have enough {currency_name} to start the game.")
        self.stop()
        await self.game.start_hand()
        await self.game.update_message(interaction)

    async def cancel(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user.id != self.game.players_ids[0]:
            return await interaction.response.send_message("Only the dealer can cancel the game.", ephemeral=True)
        if self.game.state != PokerState.WaitingForPlayers:
            return await interaction.response.send_message("The game already started.", ephemeral=True)
        self.stop()
        await self.game.cancel()
        await interaction.message.delete()
