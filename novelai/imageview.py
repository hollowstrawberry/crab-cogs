import re
import discord
import calendar
from datetime import datetime, timedelta
from discord.ui import View
from novelai_api.ImagePreset import ImagePreset

from novelai.constants import VIEW_TIMEOUT


class ImageView(View):
    def __init__(self, cog, prompt: str, preset: ImagePreset, seed: int, model: ImageModel):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.prompt = prompt
        self.preset = preset
        self.seed = seed
        self.model = model
        self.deleted = False

    @discord.ui.button(emoji="🌱", style=discord.ButtonStyle.grey)
    async def seed(self, ctx: discord.Interaction, _: discord.Button):
        embed = discord.Embed(title="Generation seed", description=f"{self.seed}", color=0x77B255)
        await ctx.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="♻", style=discord.ButtonStyle.grey)
    async def recycle(self, ctx: discord.Interaction, btn: discord.Button):
        if not ctx.guild and not await self.cog.config.dm_allowed():
            return await ctx.response.send_message("Direct message use is disabled.", ephemeral=True)
    
        if ctx.user.id not in await self.cog.config.vip():
            cooldown = await self.cog.config.server_cooldown() if ctx.guild else await self.cog.config.dm_cooldown()
            if self.cog.generating.get(ctx.user.id, False):
                content = "Your current image must finish generating before you can request another one."
                return await ctx.response.send_message(content, ephemeral=True)
            if ctx.user.id in self.cog.last_img and (datetime.utcnow() - self.cog.last_img[ctx.user.id]).seconds < cooldown:
                eta = self.cog.last_img[ctx.user.id] + timedelta(seconds=cooldown)
                content = f"You may use this command again <t:{calendar.timegm(eta.utctimetuple())}:R>."
                if not ctx.guild:
                    content += " (You can use it more frequently inside a server)"
                return await ctx.response.send_message(content, ephemeral=True)

        self.preset.seed = 0
        btn.disabled = True
        await ctx.message.edit(view=self)
        btn.disabled = False  # re-enables it after the task calls back

        content = self.cog.get_loading_message()
        self.cog.queue_add(ctx, self.prompt, self.preset, self.model, ctx.user.id, ctx.message.edit(view=self))
        await ctx.response.send_message(content=content)

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
        else:
            await ctx.response.send_message("Only a moderator or the user who requested the image may delete it.", ephemeral=True)


class RetryView(View):
    def __init__(self, cog, prompt: str, preset: ImagePreset, model: ImageModel):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.prompt = prompt
        self.preset = preset
        self.model = model
        self.deleted = False

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.grey)
    async def retry(self, ctx: discord.Interaction, _: discord.Button):
        if not ctx.guild and not await self.cog.config.dm_allowed():
            return await ctx.response.send_message("Direct message use is disabled.", ephemeral=True)
    
        if not await self.cog.bot.is_owner(ctx.user):
            if self.cog.generating.get(ctx.user.id, False):
                content = "Your current image must finish generating before you can request another one."
                return await ctx.response.send_message(content, ephemeral=True)

        self.deleted = True
        self.stop()
        await ctx.message.edit(view=None)
        content = self.cog.get_loading_message()
        self.cog.queue_add(ctx, self.prompt, self.preset, self.model, ctx.user.id, ctx.message.edit(view=None))
        await ctx.response.send_message(content=content)
