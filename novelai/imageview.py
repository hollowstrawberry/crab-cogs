import re
import asyncio
import discord
from discord.ui import View
from novelai_api.ImagePreset import ImagePreset

from novelai.constants import VIEW_TIMEOUT


class ImageView(View):
    def __init__(self, cog, prompt: str, preset: ImagePreset):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.prompt = prompt
        self.preset = preset
        self.deleted = False

    @discord.ui.button(emoji="♻", style=discord.ButtonStyle.grey)
    async def recycle(self, ctx: discord.Interaction, btn: discord.Button):
        self.preset.seed = 0
        self.cog.queue.append(self.cog.fulfill_novelai_request(ctx, self.prompt, self.preset, ctx.user.id))
        if not self.cog.queue_task or self.cog.queue_task.done():
            self.cog.queue_task = asyncio.create_task(self.cog.consume_queue())

        btn.disabled = True
        await ctx.message.edit(view=self)
        await ctx.response.defer()  # noqa

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.grey)
    async def delete(self, ctx: discord.Interaction, _: discord.Button):
        if ctx.message.interaction:
            original_user_id = ctx.message.interaction.user.id
        elif m := re.search(r"([0-9]+)", ctx.message.content):
            original_user_id = int(m.group(1))
        else:
            original_user_id = 0
        if not ctx.guild or ctx.user.id == original_user_id or ctx.channel.permissions_for(ctx.user).manage_messages:
            self.deleted = True
            self.stop()
            await ctx.message.delete()
            # await ctx.response.send_message("✅ Generation deleted.", ephemeral=True)  # noqa
        else:
            await ctx.response.send_message("Only a moderator or the user who requested the image may delete it.", ephemeral=True)  # noqa
