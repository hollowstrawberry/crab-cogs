import io
import discord
from discord.ui import View
from typing import Optional

from imagescanner.constants import VIEW_TIMEOUT


class ImageView(View):
    def __init__(self, params: str, embed: discord.Embed):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.params = params
        self.embed = embed
        self.pressed = False
        self.message: Optional[discord.Message] = None

    @discord.ui.button(emoji="🔧", label='View Full Parameters', style=discord.ButtonStyle.grey)
    async def view_full_parameters(self, ctx: discord.Interaction, _: discord.Button):
        if len(self.params) < 1980:
            await ctx.response.send_message(f"```yaml\n{self.params}```")
        else:
            with io.StringIO() as f:
                f.write(self.params)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"))
        await ctx.message.edit(view=None, embed=self.embed)
        self.pressed = True
        self.stop()

    async def on_timeout(self) -> None:
        if self.message and not self.pressed:
            await self.message.edit(view=None, embed=self.embed)
