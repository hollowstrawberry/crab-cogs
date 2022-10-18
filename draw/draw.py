import os
import discord
import cv2
from PIL import Image
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from typing import *

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

    @commands.command(aliases=["drawme", "sketch", "sketchme"])
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def draw(self, ctx: commands.Context, user: Union[discord.User, discord.Member, str] = None):
        """Produces a pencil drawing of you or someone else"""
        if user == "me" or user is None:
            user = ctx.author
        elif user == "you" or user == "yourself":
            user = self.bot.user
        elif isinstance(user, str):
            return await ctx.send("Can't find a user with that name.")
        await ctx.trigger_typing()
        # load image
        await user.avatar_url.save(self.input_image(ctx))
        Image.open(self.input_image(ctx)).convert('RGB').resize((256, 256), Image.BICUBIC).save(self.output_image(ctx))
        img = cv2.imread(self.output_image(ctx), cv2.IMREAD_GRAYSCALE)
        # apply filter
        img_blurred = cv2.bitwise_not(cv2.GaussianBlur(cv2.bitwise_not(img), (65, 65), 0))
        img_divided = cv2.divide(img, img_blurred, scale=256)
        img_normalized = cv2.normalize(img_divided, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(self.output_image(ctx), img_normalized)
        await ctx.send(file=discord.File(self.output_image(ctx)))
        os.remove(self.input_image(ctx))
        os.remove(self.output_image(ctx))

    @commands.command(aliases=["paintme"])
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def paint(self, ctx: commands.Context, user: Union[discord.User, discord.Member, str] = None):
        """Produces an oil painting of you or someone else"""
        if user == "me" or user is None:
            user = ctx.author
        elif user == "you" or user == "yourself":
            user = self.bot.user
        elif isinstance(user, str):
            return await ctx.send("Can't find a user with that name.")
        await ctx.trigger_typing()
        # load image
        await user.avatar_url.save(self.input_image(ctx))
        Image.open(self.input_image(ctx)).convert('RGB').resize((256, 256), Image.BICUBIC).save(self.output_image(ctx))
        img = cv2.imread(self.output_image(ctx), cv2.IMREAD_COLOR)
        # apply filter
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        img_morphed = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        img_normalized = cv2.normalize(img_morphed, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(self.output_image(ctx), img_normalized)
        await ctx.send(file=discord.File(self.output_image(ctx)))
        os.remove(self.input_image(ctx))
        os.remove(self.output_image(ctx))
