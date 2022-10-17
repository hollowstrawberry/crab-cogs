import os
import re
import json
import hashlib
import discord
import cv2
from PIL import Image
from redbot.core import commands, Config
from redbot.core.data_manager import cog_data_path
from typing import *

DONUT_FILE = "donuts.json"
IMG_DL = "download.png"
IMG_OUT = "output.jpg"

class Crab(commands.Cog):
    """Random fun commands for the crab friend group."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6460697574)
        default_config = {
            "donuts": "🍩",
        }
        self.config.register_global(**default_config)

    @commands.command()
    async def rate(self, ctx: commands.Context, *, thing):
        """Gives a unique rating to anything you want"""
        thing = thing.lower()
        # Invert bot-mention temporarily
        thing = re.sub(f'^<@!?{self.bot.user.id}>$', 'yourself', thing)
        # Capture groups
        author = re.search(r'\b(my|me)\b', thing)
        mention = re.search(r'<@!?([0-9]+)>', thing)
        server = re.search(r'\b(server|guild)\b', thing)
        # Invert mentions temporarily
        thing = re.sub(r"^<@!?[0-9]+> ?'?s\b", 'my', thing)
        thing = re.sub(r'^<@!?[0-9]+>', 'you', thing)
        # Flip grammatical persons
        thing = re.sub(r'\b(me|myself|I)\b', 'you', thing)
        thing = re.sub(r'\byourself\b', 'myself', thing)
        thing = re.sub(r'\byour\b', 'MY', thing)
        thing = re.sub(r'\bmy\b', 'your', thing)
        thing = re.sub(r'MY', 'my', thing)
        # Generate deterministic random value
        formatted = ''.join(ch for ch in thing if ch.isalnum()).encode('utf-8')
        hashed = abs(int(hashlib.sha512(formatted).hexdigest(), 16))
        if server:
            hashed += ctx.guild.id
        if author:
            hashed += ctx.author.id
        elif mention:
            hashed += int(mention.group(1))
            thing = re.sub('your', f"{mention.group()}'s", thing)  # Revert mentions
            thing = re.sub('you', mention.group(), thing)
        # Assign score from random value
        if thing.endswith(('ism', 'phobia', 'philia')):
            rating = hashed % 3
        elif re.search(r'(orange|food|eat|cry|rights)', thing):
            rating = hashed % 4 + 7
        else:
            rating = hashed % 11

        await ctx.send(f'I give {thing} a {rating}/10')
        print(f'rate {thing} {rating}')

    @commands.command()
    async def pp(self, ctx: commands.Context):
        """Evaluates your pp"""
        pp = ctx.author.id % 13
        await ctx.send(f'Your pp size is {pp} inches')
        print(f'pp {ctx.author.id} {pp}')

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=5, per=5, type=commands.BucketType.channel)
    async def donut(self, ctx: commands.Context):
        """Gives you donuts"""
        try:
            with open(cog_data_path(self).joinpath(DONUT_FILE), 'r') as file:
                data = json.load(file)
        except FileNotFoundError:
            with open(cog_data_path(self).joinpath(DONUT_FILE), 'w+'):
                data = {}
        count = data.get(str(ctx.author.id), 0) + 1
        data[str(ctx.author.id)] = count
        with open(cog_data_path(self).joinpath(DONUT_FILE), 'w') as file:
            json.dump(data, file)
        hashed = abs(int(hashlib.sha256(bytes(count)).hexdigest(), 16)) + 11
        donuts = (await self.config.donuts()).split(' ')
        donut = donuts[hashed % len(donuts)]
        await ctx.send(f'{count} {donut}')
        print(f'User {ctx.author.id} now has {count} donuts')

    @donut.command()
    @commands.is_owner()
    async def set(self, ctx: commands.Context, *, emojis: str):
        """Pass a list of emojis to use for the donut command, separated by spoces"""
        await self.config.donuts.set(emojis)
        await ctx.react_quietly("✅")

    @commands.command(aliases=["paintme", "paint", "drawme"])
    async def draw(self, ctx: commands.Context, user: Union[discord.User, str] = None):
        """Produces a painting of you or someone else"""
        if user == "me" or user is None:
            user = ctx.author
        elif user == "you" or user == "yourself":
            user = self.bot.user
        elif isinstance(user, str):
            return await ctx.send("who?")
        # load image
        await user.avatar_url.save(cog_data_path(self).joinpath(IMG_DL))
        Image.open(cog_data_path(self).joinpath(IMG_DL)).convert('RGB').resize((256, 256), Image.BICUBIC).save(cog_data_path(self).joinpath(IMG_OUT))
        img = cv2.imread(IMG_OUT, cv2.IMREAD_COLOR)
        # apply morphology open to smooth the outline
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        morph = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        # brighten dark regions
        result = cv2.normalize(morph, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(IMG_OUT, result)
        await ctx.send(file=discord.File(str(cog_data_path(self).joinpath(IMG_OUT))))
        os.remove(cog_data_path(self).joinpath(IMG_DL))
        os.remove(cog_data_path(self).joinpath(IMG_OUT))
        print(f"Successfully painted user {user.id}")
