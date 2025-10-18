


import re
import discord
from redbot.core.utils.chat_formatting import humanize_number

from casino.base import BasePokerGame

MAX_OPTIONS = 25
RAISE_BET_FACTOR = 1.2

ERROR_PLAYING = "You're not playing this game!"
ERROR_TURN = "It's not your turn!"


class PokerView(discord.ui.View):
    def __init__(self, game: BasePokerGame, cur_player_money: int, cur_player_bet: int, currency_name: str):
        super().__init__(timeout=None)
        self.game = game

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
            label="Call",
            style=discord.ButtonStyle.primary,
            disabled=cur_player_money < game.current_bet - cur_player_bet or cur_player_bet > game.current_bet
        )
        self.view_button = discord.ui.Button(
            custom_id=f"poker {game.channel.id} view",
            emoji="🃏",
            label="View Cards",
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
        raise_values = [int(val // 10) * 10 if val > 100 else int(val) for val in raise_values if val > game.current_bet and val < cur_player_money]  # round to tens and only include what the user can pay
        raise_options = [discord.SelectOption(label=f"{humanize_number(val)} {currency_name}", value=f"{val}") for val in raise_values]
        self.raise_select = discord.ui.Select(
            custom_id=f"poker {game.channel.id} raise",
            options=raise_options,
            placeholder="Raise bet",
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
        await self.game.update_message()
    
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
        await self.game.update_message()

    async def call(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)
        self.stop()
        await self.game.call(interaction.user.id)
        await self.game.update_message()

    async def view(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        await self.game.send_cards(interaction)

    async def bump(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        self.stop()
        await self.game.update_message()

    async def raisebet(self, interaction: discord.Interaction):
        assert self.game.turn is not None
        if interaction.user.id not in self.game.players_ids:
            return await interaction.response.send_message(ERROR_PLAYING, ephemeral=True)
        if interaction.user.id != self.game.players_ids[self.game.turn]:
            return await interaction.response.send_message(ERROR_TURN, ephemeral=True)
        self.stop()
        new_bet = int(interaction.data['values'][0])  # type: ignore
        await self.game.raise_to(interaction.user.id, new_bet)
