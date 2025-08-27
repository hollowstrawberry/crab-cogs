import io
import discord
from discord.ui import View
from typing import List, Optional

from imagescanner.constants import VIEW_TIMEOUT


class ImageView(View):
    def __init__(self, params: str, embeds: List[discord.Embed], ephemeral: bool):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.params = params
        self.embeds = embeds
        self.ephemeral = ephemeral
        self.pressed = False
        self.current = 0
        self.message: Optional[discord.Message] = None

        self.button_full = discord.ui.Button(emoji='🔧', label='View Full', style=discord.ButtonStyle.blurple)
        self.button_full.callback = self.view_full_parameters
        self.button_left = discord.ui.Button(emoji="⬅️")
        self.button_left.callback = self.left
        self.button_left.disabled = True
        self.button_right = discord.ui.Button(emoji="➡️")
        self.button_right.callback = self.right

        if len(embeds) > 1:
            self.button_left.disabled = True
            self.add_item(self.button_left)
        self.add_item(self.button_full)
        if len(embeds) > 1:
            self.add_item(self.button_right)

    async def view_full_parameters(self, interaction: discord.Interaction):
        if len(self.embeds) == 1:
            self.pressed = True
            self.stop()
        if len(self.params) < 1980:
            await interaction.response.send_message(f"```yaml\n{self.params}```", ephemeral=self.ephemeral)
        else:
            with io.StringIO() as f:
                f.write(self.params)
                f.seek(0)
                await interaction.response.send_message(file=discord.File(f, "parameters.yaml"), ephemeral=self.ephemeral) # type: ignore
        if interaction.message and len(self.embeds) == 1:
            try:
                await interaction.message.edit(view=None, embed=self.embeds[0])
            except discord.NotFound:
                pass

    async def navigate(self, interaction: discord.Interaction, left: bool):
        if self.current > 0 and left:
            self.current -= 1
        elif self.current < len(self.embeds) - 1 and not left:
            self.current += 1
        self.button_left.disabled = self.current == 0
        self.button_right.disabled = self.current == len(self.embeds) - 1
        await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

    async def left(self, interaction: discord.Interaction):
        await self.navigate(interaction, left=True)

    async def right(self, interaction: discord.Interaction):
        await self.navigate(interaction, left=False)
    
    async def on_timeout(self) -> None:
        if self.message and not self.pressed and len(self.embeds) == 1:
            try:
                await self.message.edit(view=None, embed=self.embeds[0])
            except discord.NotFound:
                pass