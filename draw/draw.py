import os
import discord
import cv2
from PIL import Image
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from typing import Optional

class Draw(commands.Cog):
    """A couple fun image filters for your friends' avatars."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    def input_image(self, ctx: commands.Context) -> str:
        return str(cog_data_path(self).joinpath(f"download_{ctx.command.name}_{ctx.author.id}.png"))

    def output_image(self, ctx: commands.Context) -> str:
        return str(cog_data_path(self).joinpath(f"output_{ctx.command.name}_{ctx.author.id}.jpg"))

    @commands.hybrid_command()
    async def avatar(self, ctx: commands.Context, user: Optional[discord.User]):
        """Simply shows your avatar or somebody else's."""
        if not user:
            user = ctx.author
        embed = discord.Embed(color=await ctx.embed_color())
        embed.title = f"Here's " + ("your" if user == ctx.author else f"{user.display_name}'s") + " avatar!"
        embed.set_image(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def draw(self, ctx: commands.Context, user: Optional[discord.User]):
        """Produces a pencil drawing of you or someone else."""
        if not user:
            user = ctx.author
        await ctx.typing()
        # load image
        await user.display_avatar.save(self.input_image(ctx))
        Image.open(self.input_image(ctx)).convert('RGB').resize((256, 256), Image.BICUBIC).save(self.output_image(ctx))
        img = cv2.imread(self.output_image(ctx), cv2.IMREAD_GRAYSCALE)
        # apply filter
        img_blurred = cv2.bitwise_not(cv2.GaussianBlur(cv2.bitwise_not(img), (65, 65), 0))
        img_divided = cv2.divide(img, img_blurred, scale=256)
        img_normalized = cv2.normalize(img_divided, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(self.output_image(ctx), img_normalized)
        embed = discord.Embed(color=await ctx.embed_color())
        embed.title = f"Here's a drawing of {'you' if user == ctx.author else user.display_name}!"
        embed.set_image(url=f"attachment://output_{ctx.command.name}_{ctx.author.id}.jpg")
        try:
            await ctx.send(embed=embed, file=discord.File(self.output_image(ctx)))
        finally:
            os.remove(self.input_image(ctx))
            os.remove(self.output_image(ctx))

    @commands.hybrid_command()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def paint(self, ctx: commands.Context, user: Optional[discord.User]):
        """Produces an oil painting of you or someone else."""
        if not user:
            user = ctx.author
        await ctx.typing()
        # load image
        await user.display_avatar.save(self.input_image(ctx))
        Image.open(self.input_image(ctx)).convert('RGB').resize((256, 256), Image.BICUBIC).save(self.output_image(ctx))
        img = cv2.imread(self.output_image(ctx), cv2.IMREAD_COLOR)
        # apply filter
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        img_morphed = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        img_normalized = cv2.normalize(img_morphed, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(self.output_image(ctx), img_normalized)
        embed = discord.Embed(color=await ctx.embed_color())
        embed.title = f"Here's a painting of {'you' if user == ctx.author else user.display_name}!"
        embed.set_image(url=f"attachment://output_{ctx.command.name}_{ctx.author.id}.jpg")
        try:
            await ctx.send(embed=embed, file=discord.File(self.output_image(ctx)))
        finally:
            os.remove(self.input_image(ctx))
            os.remove(self.output_image(ctx))
