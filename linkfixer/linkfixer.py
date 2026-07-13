import re
import logging
import discord
from typing import Dict, List, Tuple
from dataclasses import dataclass
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.linkfixer")

Span = Tuple[int, int]

@dataclass(frozen=True)
class Link:
    name: str
    pattern: re.Pattern
    fixed: str


GENERIC_LINK = re.compile(r"(?<!<)(https?://[^\s|)>\]]+)")
BLOCK_OR_DELIMITER = re.compile(r"```.*?```|`[^`]*?`|\\.|\|\|", re.DOTALL)

ALL_LINKS = [
    Link(
        "twitter",
        re.compile(r"(?<!<)(https?://(?:www\.|m\.)?(?:x|twitter)\.com/([^\s]+status/[^\s|)>\]]+))"),
        "https://fxtwitter.com/"
    ),
    Link(
        "tiktok",
        re.compile(r"(?<!<)(https?://(?:www\.)?tiktok\.com/([^\s/]+/[^/]+/[^\s|)>\]]+))"),
        "https://tiktokez.com/"
    ),
    Link(
        "vmtiktok",
        re.compile(r"(?<!<)(https?://vm\.tiktok\.com/([^\s|)>\]]+))"),
        "https://vm.tiktokez.com/"
    ),
    Link(
        "instagram",
        re.compile(r"(?<!<)(https?://(?:www\.)?instagram\.com/([^\s/]+/[^\s|)>\]]+))"),
        "https://kkinstagram.com/"
    ),
    Link(
        "reddit",
        re.compile(r"(?<!<)(https?://(?:www\.|old\.)?reddit\.com/(r/[^\s/]+/[^\s|)>\]]+))"),
        "https://redditez.com/"
    ),
    Link(
        "pixiv",
        re.compile(r"(?<!<)(https?://(?:www\.)?pixiv\.net/([^\s|)>\]]+))"),
        "https://phixiv.net/"
    ),
    Link(
        "threads",
        re.compile(r"(?<!<)(https?://(?:www\.)?threads\.com/(@[^\s/]+/[^\s|)>\]]+))"),
        "https://viewthreads.com/"
    ),
]

def get_code_and_spoiler_spans(content: str) -> Tuple[List[Span], List[Span]]:
    """
    Returns lists of ```code blocks```/`code blocks` and ||spoiler blocks||
    """
    code_spans = []
    spoiler_spans = []
    spoiler_start = None
    for m in BLOCK_OR_DELIMITER.finditer(content):
        token = m.group(0)
        if token == "||":
            if spoiler_start is None:
                spoiler_start = m.end()
            else:
                spoiler_spans.append((spoiler_start, m.start()))
                spoiler_start = None
        elif token.startswith("`"):
            code_spans.append((m.start(), m.end()))
    return code_spans, spoiler_spans

def is_in_span(spans: List[Span], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)


class LinkFixer(commands.Cog):
    """Sends modified links to embed content from popular social media sites."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=44141349)
        self.config.register_guild(**{
            "enabled": False,
            "disabled_links": [],
            "language": None,
        })
        self.enabled_guilds: List[int] = []
        self.disabled_links: Dict[int, List[str]] = {}

    async def cog_load(self):
        all_guilds = await self.config.all_guilds()
        for gid, config in all_guilds.items():
            if config.get("enabled", False):
                self.enabled_guilds.append(gid)
                self.disabled_links[gid] = config.get("disabled_links", [])

    async def red_delete_data_for_user(self, *args, **kwargs):
        """Nothing to delete"""
        pass

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.guild.id not in self.enabled_guilds or not isinstance(message.author, discord.Member) or message.author == message.guild.me:
            return
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return
        if not await self.is_valid_red_message(message):
            return

        code_spans, spoiler_spans = get_code_and_spoiler_spans(message.content)
        
        # stupid edge case
        # as of july 2026 in discord for android, an unclosed "||" can get closed by a codeblocked "||" even though a codeblocked "||" normally does not constitute a spoiler delimiter
        # but this whole thing is kinda pointless, as any spoilered url makes all embeds get spoilered
        spoiler_edge_case = any("||" in message.content[start:end] for start, end in code_spans)

        matched_links: List[str] = []
        for match in GENERIC_LINK.finditer(message.content):
            if is_in_span(code_spans, match.start()):
                continue
            link = match.group(0)
            spoilered_link = f"|| {link} ||"
            should_spoiler = is_in_span(spoiler_spans, match.start()) or spoiler_edge_case
            if link in matched_links or spoilered_link in matched_links:
                if should_spoiler and link in matched_links:
                    matched_links[matched_links.index(link)] = spoilered_link
                continue
            matched_links.append(spoilered_link if should_spoiler else link)

        if not matched_links:
            return

        language = await self.config.guild(message.guild).language()
        any_fixed = False
        link_types = [link for link in ALL_LINKS if link.name not in self.disabled_links.get(message.guild.id, [])]
        for i in range(len(matched_links)):
            link = matched_links[i]
            for link_type in link_types:
                if match := link_type.pattern.search(link):
                    any_fixed = True
                    tail = [g for g in match.groups() if g][-1].split("?")[0]
                    if language and "fxtwitter" in link_type.fixed:
                        tail = tail.rstrip("/") + "/en"
                    matched_links[i] = link.replace(match.group(0), f"{link_type.fixed}{tail}")
                    break

        if not any_fixed:
            return

        matched_links.insert(0, f"-# {message.author.mention} I fixed the links so the content embeds better.")
        await message.channel.send("\n".join(matched_links), allowed_mentions=discord.AllowedMentions.none())
        if message.channel.permissions_for(message.guild.me).manage_messages:
            await message.edit(suppress=True)

    
    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
            and await self.bot.ignored_channel_or_guild(message) \
            and not await self.bot.cog_disabled_in_guild(self, message.guild)

    
    @commands.group(name="linkfixer", aliases=["linkfix"], invoke_without_command=True)  # type: ignore
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def command_linkfixer(self, ctx: commands.Context):
        """Configure the LinkFixer cog."""
        await ctx.send_help()

    @command_linkfixer.command(name="enable")
    async def command_linkfixer_enable(self, ctx: commands.Context):
        """Enable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(True)
        if ctx.guild.id not in self.enabled_guilds:
            self.enabled_guilds.append(ctx.guild.id)
        await ctx.reply(f"✅ LinkFixer enabled in {ctx.guild.name}")

    @command_linkfixer.command(name="disable")
    async def command_linkfixer_disable(self, ctx: commands.Context):
        """Disable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(False)
        if ctx.guild.id in self.enabled_guilds:
            self.enabled_guilds.remove(ctx.guild.id)
        await ctx.reply(f"✅ LinkFixer disabled in {ctx.guild.name}")

    
    @command_linkfixer.group(name="translate", aliases=["language", "english"], invoke_without_command=True)
    async def command_linkfixer_translate(self, ctx: commands.Context):
        """Controls automatic embed translations."""
        await ctx.send_help()
    
    @command_linkfixer_translate.command(name="enable", aliases=["english", "on", "yes", "true"])
    async def command_linkfixer_translate_enable(self, ctx: commands.Context):
        """Enables compatible links to be translated to English."""
        assert ctx.guild
        await self.config.guild(ctx.guild).language.set("en")
        await ctx.reply(f"✅ Compatible links will be translated to English (such as fxtwitter).")

    @command_linkfixer_translate.command(name="disable", aliases=["off", "no", "false"])
    async def command_linkfixer_translate_disable(self, ctx: commands.Context):
        """Disables compatible links from being translated to English."""
        assert ctx.guild
        await self.config.guild(ctx.guild).language.set(None)
        await ctx.reply(f"✅ Embeds will not be translated.")

    
    @command_linkfixer.group(name="link", aliases=["links"], invoke_without_command=True)
    async def command_linkfixer_links(self, ctx: commands.Context):
        """List or toggle available links for the fixer."""
        await ctx.send_help()

    @command_linkfixer_links.command(name="list")
    async def command_linkfixer_links_list(self, ctx: commands.Context):
        """List all available links for the fixer."""
        assert ctx.guild
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        links = []
        for link in ALL_LINKS:
            links.append(f" `{'⛔' if link.name in disabled_links else '✅'} {link.name}`")
        await ctx.send(">>> " + "\n".join(links))

    @command_linkfixer_links.command(name="enable")
    async def command_linkfixer_links_enable(self, ctx: commands.Context, *link_names: str):
        """Enables one or more link fixes."""
        assert ctx.guild
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(set(disabled_links) - set(link_names))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)

    @command_linkfixer_links.command(name="disable")
    async def command_linkfixer_links_disable(self, ctx: commands.Context, *link_names: str):
        """Disables one or more link fixes."""
        assert ctx.guild
        all_links = set(link.name for link in ALL_LINKS)
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(all_links & (set(disabled_links) | set(link_names)))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)
