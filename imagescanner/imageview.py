import io
import discord
from discord.ui import View
from typing import Optional

from imagescanner.constants import VIEW_TIMEOUT


class ImageView(View):
    def __init__(self, params: str, embed: discord.Embed, ephemeral: bool):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.params = params.strip(", \n")
        self.embed = embed
        self.pressed = False
        self.ephemeral = ephemeral
        self.message: Optional[discord.Message] = None

    @discord.ui.button(emoji="🔧", label='View Full Parameters', style=discord.ButtonStyle.grey) # type: ignore
    async def view_full_parameters(self, ctx: discord.Interaction, _: discord.Button):
        self.pressed = True
        self.stop()
        if len(self.params) < 1980:
            await ctx.response.send_message(f"```yaml\n{self.params}```", ephemeral=self.ephemeral)
        else:
            with io.StringIO() as f:
                f.write(self.params)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"), ephemeral=self.ephemeral)  # type: ignore
        if ctx.message:
            await ctx.message.edit(view=None, embed=self.embed)

    async def on_timeout(self) -> None:
        if self.message and not self.pressed:
            await self.message.edit(view=None, embed=self.embed)
