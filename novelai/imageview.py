import re
import asyncio
import discord
import calendar
from datetime import datetime, timedelta, timezone
from discord.ui import View
from novelai_api.ImagePreset import ImagePreset

from novelai.constants import VIEW_TIMEOUT, DM_COOLDOWN


class ImageView(View):
    def __init__(self, cog, prompt: str, preset: ImagePreset, seed: int):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.prompt = prompt
        self.preset = preset
        self.seed = seed
        self.deleted = False

    @discord.ui.button(emoji="🌱", style=discord.ButtonStyle.grey)
    async def seed(self, ctx: discord.Interaction, _: discord.Button):
        embed = discord.Embed(title="Generation seed", description=f"{self.seed}", color=0x77B255)
        await ctx.response.send_message(embed=embed, ephemeral=True)  # noqa

    @discord.ui.button(emoji="♻", style=discord.ButtonStyle.grey)
    async def recycle(self, ctx: discord.Interaction, btn: discord.Button):
        if not ctx.guild and ctx.user.id in self.cog.last_dm \
                and (datetime.now(timezone.utc) - self.cog.last_dm[ctx.user.id]).seconds < DM_COOLDOWN:
            eta = self.cog.last_dm[ctx.user.id] + timedelta(seconds=DM_COOLDOWN)
            return await ctx.response.send_message(  # noqa
                f"You may use this command again in DMs <t:{calendar.timegm(eta.utctimetuple())}:R>", ephemeral=True)
        self.preset.seed = 0
        self.cog.queue.append(self.cog.fulfill_novelai_request(ctx, self.prompt, self.preset, ctx.user.id))
        if not self.cog.queue_task or self.cog.queue_task.done():
            self.cog.queue_task = asyncio.create_task(self.cog.consume_queue())

        btn.disabled = True
        await ctx.message.edit(view=self)
        await ctx.response.defer(thinking=True)  # noqa

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
