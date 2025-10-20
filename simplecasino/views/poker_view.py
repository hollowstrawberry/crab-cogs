


import re
import logging
import discord
from redbot.core import bank
from redbot.core.utils.chat_formatting import humanize_number

from simplecasino.base import BasePokerGame
from simplecasino.utils import InsufficientFundsError

log = logging.getLogger("red.crab-cogs.simplecasino.poker")

MAX_OPTIONS = 25
RAISE_BET_FACTOR = 1.21153  # 10x every 12th power

ERROR_PLAYING = "You're not playing this game!"
ERROR_TURN = "It's not your turn!"


class PokerView(discord.ui.View):
    def __init__(self, game: BasePokerGame, cur_player_money: int, cur_player_bet: int, currency_name: str):
        super().__init__(timeout=None)
        self.game = game

        to_call = max(0, game.current_bet - cur_player_bet)
        if to_call <= 0:
            call_label = "Call"
            call_disabled = True
        elif cur_player_money >= to_call:
            call_label = "Call"
            call_disabled = False
        else:
            call_label = f"All in"
            call_disabled = False if cur_player_money > 0 else True

        self.fold_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} fold",
            label="Fold",
            style=discord.ButtonStyle.danger,
            disabled=False,
        )
        self.check_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} check",
            label="Check",
            style=discord.ButtonStyle.success,
            disabled=not self.game.can_check,
        )
        self.call_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} call",
            label=call_label,
            style=discord.ButtonStyle.primary,
            disabled=call_disabled or cur_player_bet >= game.current_bet
        )
        self.view_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} view",
            emoji="🃏",
            label="View my cards",
            style=discord.ButtonStyle.secondary
        )
        self.bump_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} bump",
            emoji="⬇️",
            label="Bump",
            style=discord.ButtonStyle.secondary,
        )
        self.fold_button.callback = self.fold
        self.check_button.callback = self.check
        self.call_button.callback = self.call
        self.view_button.callback = self.view
        self.bump_button.callback = self.bump
        self.add_item(self.fold_button)
        self.add_item(self.check_button)
        self.add_item(self.call_button)
        self.add_item(self.view_button)
        self.add_item(self.bump_button)

        currency_name = re.sub(r"<a?:(\w+):\d+>", r"\1", currency_name)  # extract emoji name
        raise_values = [game.minimum_bet * (RAISE_BET_FACTOR ** x) for x in range(MAX_OPTIONS)]  # multiply each consecutive step by the factor
        raise_values = [int(val // 100) * 100 if val > 1000  # round to hundreds
                        else int(val // 10) * 10 if val > 100  # round to tens
                        else int(val)
                        for val in raise_values]
        raise_values = [val for val in raise_values if val > game.current_bet and val <= cur_player_money]  # only valid amounts
        raise_options = [discord.SelectOption(label=f"{humanize_number(val)} {currency_name}", value=f"{val}") for val in raise_values]
        if raise_options:
            self.raise_select = discord.ui.Select(
                custom_id=f"poker {game.channel.id} raise",
                options=raise_options,
                placeholder="Raise Bet",
                disabled=cur_player_money < game.minimum_bet
            )
            self.raise_select.callback = self.raisebet
            self.add_item(self.raise_select)

    async def fold(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)
        self.stop()
        await self.game.fold(interaction.user.id)
        await self.game.update_message(interaction)
    
    async def check(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)
        if not self.game.can_check:
            return await interaction.response.send_message("You can't check right now.", ephemeral=True)
        self.stop()
        await self.game.check(interaction.user.id)
        await self.game.update_message(interaction)

    async def call(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)

        try:
            await self.game.bet(interaction.user.id, self.game.current_bet)
        except InsufficientFundsError:
            currency_name = await bank.get_currency_name(interaction.guild)
            return await interaction.response.send_message(f"You don't have enough {currency_name} to call!", ephemeral=True)
        
        self.stop()
        await self.game.update_message(interaction)

    async def view(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        await self.game.send_cards(interaction)

    async def bump(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        self.stop()
        await self.game.update_message(None)

    async def raisebet(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)
        
        try:
            new_bet = int(interaction.data['values'][0])  # type: ignore
            await self.game.bet(interaction.user.id, new_bet)
        except InsufficientFundsError:
            currency_name = await bank.get_currency_name(interaction.guild)
            return await interaction.response.send_message(f"You don't have enough {currency_name} to raise the bet!", ephemeral=True)

        self.stop()
        await self.game.update_message(interaction)
