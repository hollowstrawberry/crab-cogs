import os
import io
import re
import json
import hashlib
import aiohttp
import discord
import cv2
from PIL import Image
from redbot.core import commands
from typing import *

DONUT_FILE = "donuts.json"
REP_FILE = "reputation.json"
IMG_DL = "download.png"
IMG_OUT = "output.jpg"

DONUTS = [
    "<:bluedonut:879880267391705089>", "<:plaindonut:879880268431892560>",
    "<:greendonut:879880268482232331>", "<:chocchocdonut:879880268658380840>",
    "<:pinkdonut:879880268704538634>", "<:pinkdonut2:879880268704546826>",
    "<:plaindonutfull:879892288870961262>", "<:whitedonut:879882533553184848>",
    "<:chocdonut:879880269140725800>", "<:chocdonutfull:879892288111783966>",
    "<:whitepinkdonut:879880269434339398>", "<:yellowdonut:879882288270303282>",
    "<:pinkdonutfull:879892287839154268>", "<:chocplaindonut:879880269560152124>",
    "<:whitechocdonut:879880269857976371>", "<:pinkplaindonut:879880269937647616>",
    "<:whitewhitedonut:879892288241815663>", "<:reddonut:879880270105444413>",
    "<:pinkpinkdonut:879880270168330260>", "<:pinkchocdonut:879880271829299220>"]


class Crab(commands.Cog):
    """Commands you might actually want to use"""
    def __init__(self, bot):
        self.bot = bot

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
    @commands.cooldown(rate=5, per=5, type=commands.BucketType.channel)
    async def donut(self, ctx: commands.Context):
        """Gives you donuts"""
        try:
            with open(DONUT_FILE, 'r') as file:
                data = json.load(file)
        except FileNotFoundError:
            with open(DONUT_FILE, 'w+'):
                data = {}
        count = data.get(str(ctx.author.id), 0) + 1
        data[str(ctx.author.id)] = count
        with open(DONUT_FILE, 'w') as file:
            json.dump(data, file)
        hashed = abs(int(hashlib.sha256(bytes(count)).hexdigest(), 16)) + 11
        donut = DONUTS[hashed % len(DONUTS)]
        await ctx.send(f'{count} {donut}')
        print(f'User {ctx.author.id} now has {count} donuts')

    @staticmethod
    async def get_emojis(ctx: commands.Context) -> Optional[List[Tuple[str]]]:
        reference = ctx.message.reference
        if not reference:
            await ctx.send("Reply to a message with this command to steal an emoji")
            return
        message = reference.cached_message or await ctx.channel.fetch_message(reference.message_id)
        if not message:
            await ctx.send("I couldn't grab that message, sorry")
            return
        emojis = re.findall(r"<(a?):(\w+):(\d{10,20})>", message.content)
        if not emojis:
            await ctx.send("Can't find an emoji in that message")
            return
        return emojis

    @commands.group()
    async def steal(self, ctx: commands.Context):
        """Steals emojis you reply to"""
        if ctx.invoked_subcommand:
            return
        if not (emojis := await self.get_emojis(ctx)):
            return
        links = [f"https://cdn.discordapp.com/emojis/{m[2]}.{'gif' if m[0] else 'png'}" for m in emojis]
        await ctx.send('\n'.join(links))

    @steal.command()
    async def upload(self, ctx: commands.Context, name=None):
        """Steals emojis you reply to, and uploads it to the server"""
        if not ctx.message.author.guild_permissions.manage_emojis:
            await ctx.send("You don't have permission to manage emojis")
            return
        if not (emojis := await self.get_emojis(ctx)):
            return
        async with aiohttp.ClientSession() as session:
            for emoji in emojis:
                link = f"https://cdn.discordapp.com/emojis/{emoji[2]}.{'gif' if emoji[0] else 'png'}"
                try:
                    async with session.get(link) as resp:
                        image = io.BytesIO(await resp.read()).read()
                except Exception as error:
                    await ctx.send(f"Couldn't download {emoji[1]}, {type(error).__name__}: {error}")
                    return
                try:
                    added = await ctx.guild.create_custom_emoji(name=name or emoji[1], image=image)
                except Exception as error:
                    await ctx.send(f"Couldn't upload {emoji[1]}, {type(error).__name__}: {error}")
                    return
                try:
                    await ctx.message.add_reaction(added)
                except:
                    pass

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
        await user.avatar_url.save(IMG_DL)
        Image.open(IMG_DL).convert('RGB').resize((256, 256), Image.BICUBIC).save(IMG_OUT)
        img = cv2.imread(IMG_OUT, cv2.IMREAD_COLOR)
        # apply morphology open to smooth the outline
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        morph = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        # brighten dark regions
        result = cv2.normalize(morph, None, 20, 255, cv2.NORM_MINMAX)
        # save and send
        cv2.imwrite(IMG_OUT, result)
        await ctx.send(file=discord.File(IMG_OUT))
        os.remove(IMG_DL)
        os.remove(IMG_OUT)
        print(f"Successfully painted user {user.id}")

    @commands.command()
    async def pp(self, ctx: commands.Context):
        """Evaluates your pp"""
        pp = ctx.author.id % 13
        await ctx.send(f'Your pp size is {pp} inches')
        print(f'pp {ctx.author.id} {pp}')
