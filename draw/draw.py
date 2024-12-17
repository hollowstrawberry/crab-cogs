import cv2
import asyncio
import discord
import functools
from io import BytesIO
from PIL import Image
from typing import Optional
from redbot.core import commands, app_commands


def prepare_image(fp: BytesIO):
    fp2 = BytesIO()
    Image.open(fp).convert('RGB').resize((256, 256), Image.Resampling.BICUBIC).save(fp2, "jpg")
    fp2.seek(0)
    del fp
    img = cv2.imdecode(fp2, cv2.IMREAD_COLOR)
    del fp2
    return img


class Draw(commands.Cog):
    """A couple fun image filters for your friends' avatars. Also includes an avatar context menu."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.avatar_context_menu = app_commands.ContextMenu(name='View Avatar', callback=self.avatar_app_command)
        self.bot.tree.add_command(self.avatar_context_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.avatar_context_menu.name, type=self.avatar_context_menu.type)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.describe(user="The person whose avatar you want to see.")
    async def avatar(self, ctx: commands.Context, user: Optional[discord.Member]):
        """Simply shows your avatar or somebody else's."""
        if not user:
            user = ctx.author
        embed = discord.Embed(color=await ctx.embed_color())
        whose = "your" if user == ctx.author else "my" if user == self.bot.user else f"{user.display_name}'s"
        embed.title = f"Here's {whose} avatar!"
        embed.set_image(url=user.display_avatar.url)
        await ctx.send(embed=embed, ephemeral=True)

    # context menu added in __init__
    async def avatar_app_command(self, inter: discord.Interaction, member: discord.Member):
        """Gets the avatar for a user quietly."""
        ctx = await commands.Context.from_interaction(inter)
        await self.avatar(ctx, member)

    @staticmethod
    def draw_effect(fp: BytesIO) -> BytesIO:
        img = prepare_image(fp)
        del fp
        img_blurred = cv2.bitwise_not(cv2.GaussianBlur(cv2.bitwise_not(img), (65, 65), 0))
        img_divided = cv2.divide(img, img_blurred, scale=256)
        del img
        del img_blurred
        img_normalized = cv2.normalize(img_divided, None, 20, 255, cv2.NORM_MINMAX)
        del img_divided
        is_success, buffer = cv2.imencode(".jpg", img_normalized)
        del img_normalized
        result = BytesIO(buffer)  # noqa
        del buffer
        return result

    @staticmethod
    def paint_effect(fp: BytesIO) -> BytesIO:
        img = prepare_image(fp)
        del fp
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        img_morphed = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        del img
        img_normalized = cv2.normalize(img_morphed, None, 20, 255, cv2.NORM_MINMAX)
        del img_morphed
        is_success, buffer = cv2.imencode(".jpg", img_normalized)
        del img_normalized
        result = BytesIO(buffer)  # noqa
        del buffer
        return result

    @commands.hybrid_command()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    @app_commands.describe(user="The person whose avatar I should draw.")
    async def draw(self, ctx: commands.Context, user: Optional[discord.User]):
        """Produces a pencil drawing of you or someone else."""
        user = user or ctx.author
        await ctx.typing()

        fp1 = BytesIO()
        await user.display_avatar.save(fp1, seek_begin=True)
        fp2 = await asyncio.to_thread(self.draw_effect, fp1)
        del fp1

        filename = f"draw_{user.id}.jpg"
        embed = discord.Embed(color=await ctx.embed_color())
        whom = "you" if user == ctx.author else "me" if user == self.bot.user else user.display_name
        embed.title = f"Here's a drawing of {whom}!"
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=discord.File(fp2, filename=filename))

    @commands.hybrid_command()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    @app_commands.describe(user="The person whose avatar I should paint.")
    async def paint(self, ctx: commands.Context, user: Optional[discord.User]):
        """Produces an oil painting of you or someone else."""
        user = user or ctx.author
        await ctx.typing()

        fp1 = BytesIO()
        await user.display_avatar.save(fp1, seek_begin=True)
        fp2 = await asyncio.to_thread(self.paint_effect, fp1)
        del fp1

        filename = f"paint_{user.id}.jpg"
        embed = discord.Embed(color=await ctx.embed_color())
        whom = "you" if user == ctx.author else "me" if user == self.bot.user else user.display_name
        embed.title = f"Here's a painting of {whom}!"
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=discord.File(fp2, filename=filename))
