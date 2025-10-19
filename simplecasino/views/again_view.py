import re
import discord
from typing import Any, Awaitable, Callable, Optional
from redbot.core.utils.chat_formatting import humanize_number

MAX_BUTTON_LENGTH = 80


class AgainView(discord.ui.View):
    def __init__(self, callback: Callable[[discord.Interaction, int], Awaitable[Any]], bet: int, message: Optional[discord.Message], currency_name: str):
        super().__init__(timeout=60)
        self.callback = callback
        self.bet = bet
        self.message = message
        currency_name = re.sub(r"<a?:(\w+):\d+>", r"\1", currency_name)  # extract emoji name
        label = f"Bet {humanize_number(bet)} {currency_name}"[:MAX_BUTTON_LENGTH]
        self.again_button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        self.again_button.callback = self.again
        self.add_item(self.again_button)

    async def again(self, interaction: discord.Interaction):
        await self.callback(interaction, self.bet)
        
    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
