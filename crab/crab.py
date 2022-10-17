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

class Crab(commands.Cog):
    """Random fun commands for the crab friend group."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6460697574)
        self.autoreact: Dict[int, Dict[str, str]] = {}
        default_global_config = {
            "donuts": "🍩",
        }
        default_guild_config = {
            "autoreact": {}
        }
        self.config.register_global(**default_global_config)
        self.config.register_guild(**default_guild_config)

    async def load_config(self) -> 'Crab':
        all_config = await self.config.all_guilds()
        self.autoreact = {guild_id: conf['autoreact'] for guild_id, conf in all_config.items()}
        return self

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        try:
            with open(cog_data_path(self).joinpath(DONUT_FILE), 'r') as file:
                data = json.load(file)
            if data:
                data.pop(str(user_id), None)
            with open(cog_data_path(self).joinpath(DONUT_FILE), 'w') as file:
                json.dump(data, file)
        except FileNotFoundError:
            pass

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        autoreact = self.autoreact.get(message.guild.id, None)
        if not autoreact:
            return
        for key in autoreact.keys():
            if key in message.content:
                await message.add_reaction(autoreact[key])

    # Commands

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

    @commands.command()
    async def pp(self, ctx: commands.Context):
        """Evaluates your pp"""
        pp = ctx.author.id % 13
        await ctx.send(f'Your pp size is {pp} inches')

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

    @donut.command()
    @commands.is_owner()
    async def set(self, ctx: commands.Context, *, emojis: str):
        """Pass a list of emojis to use for the donut command, separated by spoces"""
        await self.config.donuts.set(emojis)
        await ctx.react_quietly("✅")

    @commands.command(aliases=["drawme", "sketch", "sketchme"])
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def draw(self, ctx: commands.Context, user: Union[discord.User, str] = None):
        """Produces a pencil drawing of you or someone else"""
        if user == "me" or user is None:
            user = ctx.author
        elif user == "you" or user == "yourself":
            user = self.bot.user
        elif isinstance(user, str):
            return await ctx.send("Who?")
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
    async def paint(self, ctx: commands.Context, user: Union[discord.User, str] = None):
        """Produces an oil painting of you or someone else"""
        if user == "me" or user is None:
            user = ctx.author
        elif user == "you" or user == "yourself":
            user = self.bot.user
        elif isinstance(user, str):
            return await ctx.send("Who?")
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

    def input_image(self, ctx: commands.Context) -> str:
        return str(cog_data_path(self).joinpath(f"download_{ctx.command.name}_{ctx.author.id}.png"))

    def output_image(self, ctx: commands.Context) -> str:
        return str(cog_data_path(self).joinpath(f"output_{ctx.command.name}_{ctx.author.id}.jpg"))

    # Settings

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def autoreact(self, ctx: commands.Context):
        """Reacts to a specific text with an emoji"""
        await ctx.send_help()

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def add(self, ctx: commands.Context, emoji: discord.Emoji, *, text: str):
        """Add a new autoreact with an emoji to a text"""
        async with self.config.guild(ctx.guild).autoreact() as autoreact:
            autoreact[text] = str(emoji)
            self.autoreact.setdefault(ctx.guild.id, {})
            self.autoreact[ctx.guild.id][text] = str(emoji)
        await ctx.react_quietly("✅")

    @autoreact.command()
    @commands.has_permissions(manage_messages=True)
    async def remove(self, ctx: commands.Context, *, text: str):
        """Remove an existing autoreact through its target text"""
        async with self.config.guild(ctx.guild).autoreact() as autoreact:
            emoji = autoreact.pop(text, None)
            self.autoreact.setdefault(ctx.guild.id, {})
            self.autoreact[ctx.guild.id].pop(text, None)
        if emoji:
            await ctx.react_quietly("✅")
        else:
            await ctx.send("No autoreact found for that text")

    @autoreact.command()
    async def list(self, ctx: commands.Context):
        """Lists all autoreacts"""
        if ctx.guild.id not in self.autoreact or not self.autoreact[ctx.guild.id]:
            await ctx.send("None")
            return
        await ctx.send('\n'.join(f"{emoji} - `{text}`" for text, emoji in self.autoreact[ctx.guild.id].items()))
