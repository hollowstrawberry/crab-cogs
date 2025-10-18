import re
import discord
from typing import Optional
from redbot.core.utils.chat_formatting import humanize_number

from minigames.base import Minigame

MAX_BUTTON_LABEL = 80


class RematchView(discord.ui.View):
    def __init__(self, game: Minigame, currency_name: str):
        super().__init__(timeout=300)
        self.game = game
        self.message: Optional[discord.Message] = None
        self.rematch_button = None
        if not self.game.is_cancelled():
            currency_name = re.sub(r"<a?:(\w+):\d+>", r"\1", currency_name)  # extract emoji name
            if game.bet == 0 or any(player.bot for player in self.game.players):
                label = "Rematch"
            else:
                label = f"Rematch and bet {humanize_number(game.bet)} {currency_name}"[:MAX_BUTTON_LABEL]
            self.rematch_button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, row=4)
            self.rematch_button.callback = self.rematch
            self.add_item(self.rematch_button)

    async def rematch(self, interaction: discord.Interaction):
        assert interaction.message and isinstance(interaction.user, discord.Member)
        if interaction.user not in self.game.players:
            return await interaction.response.send_message("You didn't play this game! You should start a new one.", ephemeral=True)
        
        opponent = [player for player in self.game.players if player != interaction.user][0]
        players = [interaction.user, opponent] if opponent.bot else [opponent, interaction.user]
        bet = None if opponent.bot else self.game.bet

        self.stop()
        await self.game.cog.base_minigame_cmd(type(self.game), interaction, players, opponent.bot, bet)
        await self.on_timeout()
        
    async def on_timeout(self):
        if self.message:
            if self.rematch_button:
                self.remove_item(self.rematch_button)
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
