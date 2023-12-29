import re
import asyncio
import discord
import calendar
from datetime import datetime, timedelta
from discord.ui import View
from novelai_api.ImagePreset import ImagePreset, ImageGenerationType

from novelai.constants import VIEW_TIMEOUT


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
        if not await self.cog.bot.is_owner(ctx.user):
            cooldown = await self.cog.config.server_cooldown() if ctx.guild else await self.cog.config.dm_cooldown()
            if self.cog.generating.get(ctx.user.id, False):
                message = "Your current image must finish generating before you can request another one."
                return await ctx.response.send_message(message, ephemeral=True)  # noqa
            if ctx.user.id in self.cog.last_img and (datetime.utcnow() - self.cog.last_img[ctx.user.id]).seconds < cooldown:
                eta = self.cog.last_img[ctx.user.id] + timedelta(seconds=cooldown)
                message = f"You may use this command again <t:{calendar.timegm(eta.utctimetuple())}:R>."
                if not ctx.guild:
                    message += " (You can use it more frequently inside a server)"
                return await ctx.response.send_message(message, ephemeral=True)  # noqa

        btn.disabled = True
        await ctx.message.edit(view=self)
        await ctx.response.defer(thinking=True)  # noqa
        btn.disabled = False  # re-enables it after the task calls back

        self.preset.seed = 0
        self.cog.generating[ctx.user.id] = True
        task = self.cog.fulfill_novelai_request(
            ctx, self.prompt, self.preset, ImageGenerationType.NORMAL, ctx.user.id, ctx.message.edit(view=self))
        self.cog.queue.append(task)
        if not self.cog.queue_task or self.cog.queue_task.done():
            self.cog.queue_task = asyncio.create_task(self.cog.consume_queue())

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
            imagelog = self.cog.bot.get_cog("ImageLog")
            if imagelog:
                imagelog.manual_deleted_by[ctx.message.id] = ctx.user.id
            await ctx.message.delete()
            # await ctx.response.send_message("✅ Generation deleted.", ephemeral=True)  # noqa
        else:
            await ctx.response.send_message("Only a moderator or the user who requested the image may delete it.", ephemeral=True)  # noqa
