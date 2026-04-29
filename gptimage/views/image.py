import re
import discord
from discord.ui import View
from typing import List, Optional

from gptimage.base import GptImageBase


class ImageView(View):
    def __init__(self, cog: GptImageBase, prompt: str, resolution: str, images: List[bytes]):
        super().__init__(timeout=600)
        self.cog = cog
        self.prompt = prompt
        self.resolution = resolution
        self.images = images
        self.message: Optional[discord.Message] = None
        self.deleted = False

    @discord.ui.button(emoji="🔎", style=discord.ButtonStyle.grey)
    async def inspect(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert isinstance(interaction.channel, discord.abc.Messageable)
        embed = discord.Embed(color=await self.cog.bot.get_embed_color(interaction.channel))
        embed.title = "Generated Image"
        embed.description = f"```\n{self.prompt}\n```"
        embed.set_footer(text=interaction.user.display_name, icon_url=interaction.user.display_avatar)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🎲", style=discord.ButtonStyle.grey)
    async def recycle(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        await self.cog.imagine(interaction, self.resolution, self.prompt, self.images)

    @discord.ui.button(emoji="📝", style=discord.ButtonStyle.grey)
    async def modify_image(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert self.message
        from gptimage.views.edit import EditModal
        modal = EditModal(self.cog, self.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.grey)
    async def delete(self, interaction: discord.Interaction, _):
        assert interaction.message and interaction.channel and isinstance(interaction.user, discord.Member)
        if interaction.message.interaction:
            original_user_id = interaction.message.interaction.user.id
        elif m := re.search(r"(\d+)", interaction.message.content):
            original_user_id = int(m.group(1))
        else:
            original_user_id = 0
        if not interaction.guild or interaction.user.id == original_user_id or interaction.channel.permissions_for(interaction.user).manage_messages:
            self.deleted = True
            self.stop()
            imagelog = self.cog.bot.get_cog("ImageLog")
            if imagelog:
                getattr(imagelog, "manual_deleted_by")[interaction.message.id] = interaction.user.id
            await interaction.message.delete()
        else:
            await interaction.response.send_message("Only a moderator or the user who requested the image may delete it.", ephemeral=True)

    async def on_timeout(self) -> None:
        await super().on_timeout()
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
