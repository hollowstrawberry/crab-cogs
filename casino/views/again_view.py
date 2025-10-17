import discord
from typing import Any, Awaitable, Callable, Optional


class AgainView(discord.ui.View):
    def __init__(self, callback: Callable[[discord.Interaction, int], Awaitable[Any]], bid: int, message: Optional[discord.Message]):
        super().__init__(timeout=60)
        self.callback = callback
        self.bid = bid
        self.message = message

    @discord.ui.button(label="Again", style=discord.ButtonStyle.green)
    async def again(self, interaction: discord.Interaction, _):
        await self.callback(interaction, self.bid)
        
    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
