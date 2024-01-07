import re
import hashlib
from redbot.core import commands, app_commands, Config

DESSERTS = "🍩 🍰 🎂 🍪 🍫 🧁 🍨 🥨 🥐 🥨 🥯 🥞 🧇"

class Randomness(commands.Cog):
    """A few fun commands involving randomness."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6460697574)
        self.config.register_global(donuts=DESSERTS)
        self.config.register_user(donuts=0)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()

    # Commands

    @commands.hybrid_command()
    @app_commands.describe(thing="The thing to give a rating for.")
    async def rate(self, ctx: commands.Context, *, thing):
        """Gives a unique rating to anything you ask."""
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

    @commands.hybrid_command()
    @app_commands.describe(whose="Whose pp to evaluate. This is a joke, you can only view your own.")
    async def pp(self, ctx: commands.Context, *, whose=""):
        """Evaluates your pp size."""
        if whose and all(x.lower() not in whose.lower() for x in ("me", "my", "mine", ctx.author.id, ctx.author.name, ctx.author.display_name)):
            await ctx.reply(f"You can't view someone else's pp")
        else:
            pp = ctx.author.id % 13
            await ctx.reply(f"Your pp size is {pp} inches")

    @commands.hybrid_command(aliases=["dessert"])
    @commands.cooldown(rate=5, per=5, type=commands.BucketType.channel)
    async def donut(self, ctx: commands.Context):
        """Gives you a random dessert and a score."""
        count = await self.config.user(ctx.author).donuts() + 1
        await self.config.user(ctx.author).donuts.set(count)
        hashed = abs(int(hashlib.sha256(bytes(count)).hexdigest(), 16)) + 11
        donuts = (await self.config.donuts()).split(' ')
        donut = donuts[hashed % len(donuts)]
        await ctx.send(f'{count} {donut}')

    @commands.command()
    @commands.is_owner()
    async def donutset(self, ctx: commands.Context, *emojis: str):
        """Pass space-separated emojis to use for the donut command."""
        if not emojis:
            emojistr = DESSERTS
        else:
            emojistr = ' '.join(emojis)
        await self.config.donuts.set(emojistr)
        await ctx.react_quietly("✅")
