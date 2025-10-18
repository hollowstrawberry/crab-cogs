import re
import discord
from redbot.core import bank
from redbot.core.utils.chat_formatting import humanize_number

from minigames.base import Minigame

MAX_BUTTON_LABEL = 80


class InviteView(discord.ui.View):
    def __init__(self, game: Minigame, currency_name: str):
        super().__init__(timeout=None)
        self.game = game
        currency_name = re.sub(r"<a?:(\w+):\d+>", r"\1", currency_name)  # extract emoji name
        label = "Accept" if game.bet == 0 else f"Accept and bet {humanize_number(game.bet)} {currency_name}"[:MAX_BUTTON_LABEL]
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
        self.game.accept(interaction.user)
        await self.game.init()
        await interaction.response.edit_message(content=await self.game.get_content(), embed=await self.game.get_embed(), view=await self.game.get_view())

    async def cancel(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
        await self.game.cancel(interaction.user)
        self.stop()
        assert interaction.message
        await interaction.message.delete()
