import re
import discord
import logging
from random import random
from emoji import is_emoji
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.views import SimpleMenu
from typing import Optional, Union

log = logging.getLogger("red.crab-cogs.autoreact")

def batched(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def is_regional_indicator(string: str):
    return string.strip() in "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿"


class Autoreact(commands.Cog):
    """Lets you configure emojis that will be added to any message containing text matching a regex."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=61757472)
        self.autoreacts: dict[int, dict[str, re.Pattern]] = {}
        self.coreact_chance: dict[int, float] = {}
        self.config.register_guild(autoreact_regexes={}, coreact_chance=0.0)

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        self.autoreacts = {guild_id: {emoji: re.compile(text) for emoji, text in conf['autoreact_regexes'].items()}
                           for guild_id, conf in all_config.items()}
        self.coreact_chance = {guild_id: conf['coreact_chance'] for guild_id, conf in all_config.items()}

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        channel_perms = message.channel.permissions_for(message.guild.me)
        if not channel_perms.add_reactions:
            return
        autoreact = self.autoreacts.get(message.guild.id, None)
        if not autoreact:
            return
        if not await self.is_valid_red_message(message):
            return
        for emoji, regex in autoreact.items():
            if not regex.search(message.content):
                continue
            try:
                await message.add_reaction(emoji)
            except Exception as error:
                if "Unknown Emoji" in str(error):
                    async with self.config.guild(message.guild).autoreact_regexes() as autoreacts:
                        removed1 = autoreacts.pop(emoji, None)
                        removed2 = self.autoreacts[message.guild.id].pop(emoji, None)
                        if removed1 or removed2:
                            log.info(f"Removed invalid or deleted emoji {emoji}")
                            return
                log.warning(f"Failed to react with {emoji} - {type(error).__name__}: {error}", exc_info=True)
                    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        message = reaction.message
        if not message or not message.guild or user.bot:
            return
        if any(existing.me for existing in message.reactions if existing.emoji == reaction.emoji):
            return
        chance = self.coreact_chance.get(message.guild.id, 0.0)
        if not chance or random() >= chance:
            return
        if not await self.is_valid_red_message(message):
            return
        try:
            await message.add_reaction(reaction.emoji)
        except Exception as error:
            log.warning(f"Failed to react with {reaction.emoji} - {type(error).__name__}: {error}", exc_info=True)

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    # Commands

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def autoreact(self, ctx: commands.Context):
        """Reacts to specific text with an emoji."""
        await ctx.send_help()

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def add(self, ctx: commands.Context, emoji: Union[discord.Emoji, str], *, pattern: str):
        """Add a new autoreact using regex. Tip: (?i) in a regex makes it case-insensitive."""
        if isinstance(emoji, str) and not is_emoji(emoji) and not is_regional_indicator(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji to react with.")
            return
        if isinstance(emoji, discord.Emoji) and emoji not in self.bot.emojis:
            await ctx.send("I must be in the same guild as an emoji to be able to use it!")
            return
        if len(pattern) > 400:
            await ctx.send("Sorry, the regex may not be longer than 400 characters.")
            return
        if pattern.startswith('`') and pattern.endswith('`'):
            pattern = pattern.strip('`')
        try:
            pattern = re.compile(pattern)
        except Exception as error:
            await ctx.send(f"Invalid regex pattern: {error}")
            return
        emoji = str(emoji)
        self.autoreacts.setdefault(ctx.guild.id, {})
        async with self.config.guild(ctx.guild).autoreact_regexes() as autoreacts:
            autoreacts[emoji] = pattern.pattern
            self.autoreacts[ctx.guild.id][emoji] = pattern
            await ctx.react_quietly("✅")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx: commands.Context, emoji: Union[discord.Emoji, str]):
        """Remove an existing autoreact for an emoji."""
        if isinstance(emoji, str) and not is_emoji(emoji) and not is_regional_indicator(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji. "
                           "If the emoji was deleted, trigger the autoreact to remove it automatically.")
            return
        emoji = str(emoji)
        self.autoreacts.setdefault(ctx.guild.id, {})
        async with self.config.guild(ctx.guild).autoreact_regexes() as autoreacts:
            removed1 = autoreacts.pop(emoji, None)
            removed2 = self.autoreacts[ctx.guild.id].pop(emoji, None)
            if removed1 or removed2:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that emoji.")

    @autoreact.command()
    async def list(self, ctx: commands.Context):
        """Shows all autoreacts."""
        if ctx.guild.id not in self.autoreacts or not self.autoreacts[ctx.guild.id]:
            return await ctx.send("None.")
        autoreacts = [f"{emoji} {regex.pattern if '`' in regex.pattern else f'`{regex.pattern}`'}"
                      for emoji, regex in self.autoreacts[ctx.guild.id].items()]
        pages = []
        for i, batch in enumerate(batched(autoreacts, 10)):
            embed = discord.Embed(title="Server Autoreacts", color=await ctx.embed_color())
            if len(autoreacts) > 10:
                embed.set_footer(text=f"Page {i+1}/{(9+len(autoreacts))//10}")
            embed.description = '\n'.join(batch)
            pages.append(embed)
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            await SimpleMenu(pages, timeout=600).start(ctx)
        
    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def coreact(self, ctx: commands.Context):
        """Copies other people's reactions to recent messages."""
        await ctx.send_help()
        
    @coreact.command()
    async def chance(self, ctx: commands.Context, chance: Optional[float]):
        """The percent chance that the bot will add its own reaction when anyone else reacts."""
        if chance is None:
            return await ctx.send(f"The current chance is {self.coreact_chance.get(ctx.guild.id, 0.0) * 100:.2f}%")
        chance = max(0.0, min(100.0, chance)) / 100
        await self.config.guild(ctx.guild).coreact_chance.set(chance)
        self.coreact_chance[ctx.guild.id] = chance
        await ctx.send(f"✅ The new chance is {chance * 100:.2f}%")

