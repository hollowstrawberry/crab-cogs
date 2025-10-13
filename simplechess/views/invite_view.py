import re
import discord
from redbot.core import bank

from simplechess.base import BaseChessGame

MAX_BUTTON_LABEL = 80


class InviteView(discord.ui.View):
    def __init__(self, game: BaseChessGame, currency_name: str):
        super().__init__(timeout=None)
        self.game = game
        currency_name = re.sub(r"<a?:(\w+):\d+>", r"\1", currency_name)
        label = "Accept" if game.bet == 0 else f"Accept and bet {game.bet} {currency_name}"[:MAX_BUTTON_LABEL]
        accept_button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        accept_button.callback = self.accept
        cancel_button.callback = self.cancel
        self.add_item(accept_button)
        self.add_item(cancel_button)

    async def accept(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        if interaction.user != self.game.players[0]:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        if self.game.bet > 0:
            for player in self.game.players:
                if not await bank.can_spend(player, self.game.bet):
                    content = f"{player.mention} doesn't have enough {await bank.get_currency_name(interaction.guild)}!"
                    return await interaction.response.send_message(content, allowed_mentions=discord.AllowedMentions.none())
        await self.game.start()
        await interaction.response.pong()
        await self.game.update_message()

    async def cancel(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        self.stop()
        await self.game.cancel(None)
        await interaction.message.delete()
