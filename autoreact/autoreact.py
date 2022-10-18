import discord
from emoji import is_emoji
from redbot.core import commands, Config
from typing import *

class Autoreact(commands.Cog):
    """Lets you configure emojis that will be added to any message containing specific text."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=61757472)
        self.autoreact: Dict[int, List[Tuple[str, str]]] = {}
        self.config.register_guild(autoreact=[])

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.autoreact = {guild_id: conf['autoreact'] for guild_id, conf in all_config.items()}

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        autoreact = self.autoreact.get(message.guild.id, None)
        if not autoreact:
            return
        for text, emoji in autoreact:
            if text in message.content:
                await message.add_reaction(emoji)

    # Commands

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def autoreact(self, ctx: commands.Context):
        """Reacts to a specific text with an emoji"""
        await ctx.send_help()

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def add(self, ctx: commands.Context, emoji: Union[discord.Emoji, str], *, text: str):
        """Add a new autoreact with an emoji to a text"""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji to react with.")
            return
        if len(text) > 200:
            await ctx.send("Sorry, the target text may not be longer than 200 characters.")
            return
        async with self.config.guild(ctx.guild).autoreact() as autoreact:
            pair = (text, str(emoji))
            if pair in autoreact:
                await ctx.react_quietly("✅")
                return
            autoreact.append(pair)
            self.autoreact.setdefault(ctx.guild.id, [])
            self.autoreact[ctx.guild.id].append(pair)
            await ctx.react_quietly("✅")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def removetext(self, ctx: commands.Context, *, text: str):
        """Remove existing autoreacts for a target text."""
        self.autoreact.setdefault(ctx.guild.id, [])
        async with self.config.guild(ctx.guild).autoreact() as autoreact:
            to_remove = [pair for pair in autoreact if pair[0] == text]
            for pair in to_remove:
                autoreact.remove(pair)
                if pair in self.autoreact[ctx.guild.id]:
                    self.autoreact[ctx.guild.id].remove(pair)
            if to_remove:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that text.")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def removeemoji(self, ctx: commands.Context, emoji: Union[discord.Emoji, str]):
        """Remove existing autoreacts for an emoji."""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji.")
            return
        self.autoreact.setdefault(ctx.guild.id, [])
        async with self.config.guild(ctx.guild).autoreact() as autoreact:
            to_remove = [pair for pair in autoreact if pair[1] == str(emoji)]
            for pair in to_remove:
                autoreact.remove(pair)
                if pair in self.autoreact[ctx.guild.id]:
                    self.autoreact[ctx.guild.id].remove(pair)
            if to_remove:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that emoji.")

    @autoreact.command()
    async def list(self, ctx: commands.Context, page: int = 1):
        """Lists all autoreacts"""
        embed = discord.Embed(title="Server Autoreacts", color=await ctx.embed_color(), description="None")
        embed.set_footer(text=f"Page {page}")
        if ctx.guild.id in self.autoreact and self.autoreact[ctx.guild.id]:
            autoreacts = [f"{emoji} {text if '`' in text else f'`{text}`'}"
                          for text, emoji in self.autoreact[ctx.guild.id]]
            autoreacts = autoreacts[10*(page-1):10*page]
            if autoreacts:
                embed.description = '\n'.join(autoreacts)
        await ctx.send(embed=embed)