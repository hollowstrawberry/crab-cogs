import discord
from typing import Optional
from redbot.core import commands

from gptimage.base import GptImageBase
from gptimage.utils import MODELS


class GptImageSettings(GptImageBase):
    
    @commands.group(name="gptimage", aliases=["gptimageset"]) # type: ignore
    @commands.is_owner()
    async def gptimage_cmd(self, _):
        """Configure /imagine bot-wide"""
        pass

    @gptimage_cmd.command(name="enable")
    async def enable_cmd(self, ctx: commands.Context):
        """
        Enables the generator on this server
        """
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.tick()

    @gptimage_cmd.command(name="disable")
    async def disable_cmd(self, ctx: commands.Context):
        """
        Disables the generator on this server
        """
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.tick()

    @gptimage_cmd.command(name="model")
    async def model_cmd(self, ctx: commands.Context, model: Optional[str]):
        """The OpenAI image generation model to be used. Careful of costs, see https://openai.com/api/pricing/"""
        if model is None:
            model = await self.config.model()
        else:
            model = model.lower().strip()
            if model not in MODELS.keys():
                await ctx.reply("Model must be one of: " + ",".join([f'`{m}`' for m in MODELS.keys()]))
                return
            await self.config.model.set(model)
            quality = await self.config.quality()
            if quality not in MODELS[model]:
                await self.config.quality.set(MODELS[model][0] if len(MODELS[model]) else None)
        await ctx.reply(f"The /imagine command will use the {model} model.")

    @gptimage_cmd.command(name="quality")
    async def quality_cmd(self, ctx: commands.Context, quality: Optional[str]):
        """The quality to be used with the image generation model. Careful of costs, see https://openai.com/api/pricing/"""
        if quality is None:
            quality = await self.config.quality()
        else:
            model = await self.config.model()
            quality = quality.lower().strip()
            qualities = MODELS.get(model, [])
            if quality not in qualities:
                return await ctx.reply("Quality must be one of: " + ",".join([f'`{m}`' for m in (qualities)]))
            await self.config.quality.set(quality)
        await ctx.reply(f"The /imagine command will use {quality} quality.")

    @gptimage_cmd.command(name="loading_emoji")
    async def loading_emoji_cmd(self, ctx: commands.Context, emoji: str):
        """
        Sets a loading emoji for the progress message
        """
        await self.config.loading_emoji.set(emoji)
        await ctx.tick()

    @gptimage_cmd.command(name="quota", aliases=["limit"])
    async def quota_cmd(self, ctx: commands.Context, gens: int):
        """
        Sets the number of images a non-vip user can generate per hour
        """
        if gens < 0 or gens > 1000:
            return await ctx.send("Valid quota values range from 0 to 1000")
        await self.config.quota.set(gens)
        await ctx.send(f"Hourly quota set to {gens}")

    @gptimage_cmd.group(name="vip")
    async def vip_cmd(self, _: commands.Context):
        """
        Manage the VIP role for image generation, which can generate as many images as they want
        """
        pass

    @vip_cmd.command(name="view", aliases=["show", "list"])
    async def vip_view(self, ctx: commands.Context):
        """
        View the VIP role
        """
        assert ctx.guild
        role_id = await self.config.guild(ctx.guild).vip_role()
        all_users = await self.config.all_users()
        users = [f"<@{uid}>" for uid, config in all_users.items() if config.get("vip")]
        content = "`VIP role for this guild:` " + (f"<@&{role_id}>" if role_id and role_id >= 0 else "*none*")
        content += "\n`VIP users globally:` " + (" ".join(users) if users else "*none*")
        await ctx.send(content, allowed_mentions=discord.AllowedMentions.none())

    @vip_cmd.command(name="role")
    async def vip_role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Sets a VIP role for this server
        """
        assert ctx.guild
        await self.config.guild(ctx.guild).vip_role.set(role.id)
        await ctx.send(f"VIP role set to {role.mention}", allowed_mentions=discord.AllowedMentions.none())

    @vip_cmd.command(name="user", aliases=["users"])
    async def vip_user(self, ctx: commands.Context, *, user: discord.User):
        """
        Toggles whether a user is VIP
        """
        vip_list = await self.config.vip()
        if ctx.author.id in vip_list:
            vip_list.remove(ctx.author.id)
        else:
            vip_list.append(ctx.author.id)
        await self.config.vip.set(vip_list)
        await ctx.send(f"User {user.mention} is {'now VIP' if ctx.author.id in vip_list else 'no longer VIP'}", allowed_mentions=discord.AllowedMentions.none())

    @staticmethod
    def is_nsfw(channel: discord.abc.Messageable):
        if isinstance(channel, discord.TextChannel):
            return channel.nsfw
        elif isinstance(channel, discord.Thread) and channel.parent:
            return channel.parent.nsfw
        else:
            return False
