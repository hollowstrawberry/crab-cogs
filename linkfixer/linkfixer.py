import regex
import logging
import discord
from typing import Dict, List, Tuple
from dataclasses import dataclass
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.linkfixer")

Span = Tuple[int, int]


@dataclass(frozen=True)
class Link:
    name: str
    pattern: regex.Pattern
    sub: str
    translatable: bool = False

    def fix(self, url: str) -> str:
        return self.pattern.sub(self.sub, url.split("?")[0])


GENERIC_LINK = regex.compile(r"(?<!<)(https?://[^\s|)>\]]+)")
BLOCK_OR_DELIMITER = regex.compile(r"```.*?```|`[^`]*?`|\\.|\|\|", regex.DOTALL)
TAIL = r"[^\s|)>\]]*[^\s|)>\].,;:!?]" + ")"
NOT = r"(?<![<=])"
FLAGS = regex.IGNORECASE
 
TWITTER_RE = regex.compile(NOT + r"https?://(?:www\.|m\.|mobile\.)?(?:x|twitter)\.com/(?P<tail>(?:[^\s/]+/)+status/" + TAIL, FLAGS)
INSTAGRAM_RE = regex.compile(NOT + r"https?://(?:www\.)?instagram\.com/(?P<tail>[^\s/]+/" + TAIL, FLAGS)
REDDIT_RE = regex.compile(NOT + r"https?://(?:www\.|old\.|np\.)?reddit\.com/(?P<tail>r/[^\s/]+/" + TAIL, FLAGS)
PIXIV_RE = regex.compile(NOT + r"https?://(?:www\.)?pixiv\.net/(?P<tail>" + TAIL, FLAGS)
THREADS_RE = regex.compile(NOT + r"https?://(?:www\.)?threads\.(?:net|com)/(?P<tail>@[^\s/]+/" + TAIL, FLAGS)
BILIBILI_RE = regex.compile(NOT + r"https?://(?P<pre>\w+\.)?bilibili\.com/(?P<tail>" + TAIL, FLAGS)
B23_RE = regex.compile(NOT + r"https?://(?P<pre>\w+\.)?b23\.tv/(?P<tail>" + TAIL, FLAGS)
TIKTOK_RE = regex.compile("".join([
    NOT, r"https?://(?:",
    r"(?P<pre>www\.)?tiktok\.com/(?P<tail>(?:[^\s/]+/[^\s/]+|t)/", TAIL,
    r"|(?P<pre>v[mt]\.)tiktok\.com/(?P<tail>", TAIL,
    r")"
]), FLAGS)
FIXEMBED_RE = regex.compile("".join([
    NOT, r"https?://(?:[\w-]+\.)?(?:",
    r"twitter\.com|x\.com|instagram\.com|reddit\.com|redd\.it",
    r"|threads\.(?:net|com)|pixiv\.net|bilibili\.com|b23\.tv|youtube\.com/post",
    r"|pinterest\.com/pin|pin\.it|tiktok\.com|sta\.sh",
    r")/(?P<tail>", TAIL
]), FLAGS)
 
ALL_LINKS = [
    Link("fxtwitter",   TWITTER_RE,   r"https://fxtwitter.com/\g<tail>", translatable=True),
    Link("vxtwitter",   TWITTER_RE,   r"https://vxtwitter.com/\g<tail>", translatable=True),
    Link("oginstagram", INSTAGRAM_RE, r"https://oginstagram.com/\g<tail>"),
    Link("vxinstagram", INSTAGRAM_RE, r"https://vxinstagram.com/\g<tail>"),
    Link("kkinstagram", INSTAGRAM_RE, r"https://kkinstagram.com/\g<tail>"),
    Link("vxreddit",    REDDIT_RE,    r"https://vxreddit.com/\g<tail>"),
    Link("redditez",    REDDIT_RE,    r"https://redditez.com/\g<tail>"),
    Link("phixiv",      PIXIV_RE,     r"https://phixiv.net/\g<tail>"),
    Link("ppxiv",       PIXIV_RE,     r"https://ppxiv.net/\g<tail>"),
    Link("viewthreads", THREADS_RE,   r"https://viewthreads.com/\g<tail>"),
    Link("tnktok",      TIKTOK_RE,    r"https://\g<pre>tnktok.com/\g<tail>"),
    Link("tiktokez",    TIKTOK_RE,    r"https://\g<pre>tiktokez.com/\g<tail>"),
    Link("vxbilibili",  BILIBILI_RE,  r"https://\g<pre>vxbilibili.com/\g<tail>", translatable=True),
    Link("vxb23",       B23_RE,       r"https://\g<pre>vxb23.tv/\g<tail>", translatable=True),
    Link("fixembed",    FIXEMBED_RE,  r"https://fixembed.app/embed?url=\g<0>"),
]

DEFAULT_DISABLED_LINKS = ["vxtwitter", "kkinstagram", "vxinstagram", "redditez", "tiktokez", "ppxiv"]


def is_in_span(spans: List[Span], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)

def get_code_and_spoiler_spans(content: str) -> Tuple[List[Span], List[Span]]:
    """Returns lists of ```code blocks```/`code blocks` and ||spoiler blocks||"""
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

def fix_links(content: str, link_types: list[Link], language: str) -> str | None:
    code_spans, spoiler_spans = get_code_and_spoiler_spans(content)
    # stupid edge case
    # as of july 2026 in discord for android, an unclosed "||" can get closed by a codeblocked "||" even though a codeblocked "||" normally does not constitute a spoiler delimiter
    # but this whole thing is kinda pointless, as any spoilered url makes all embeds get spoilered
    spoiler_edge_case = any("||" in content[start:end] for start, end in code_spans)

    urls: Dict[str, bool] = {}
    for m in GENERIC_LINK.finditer(content):
        if is_in_span(code_spans, m.start()):
            continue
        spoiler = is_in_span(spoiler_spans, m.start()) or spoiler_edge_case
        urls[m.group(0)] = urls.get(m.group(0), False) or spoiler
    if not urls:
        return None
    
    out = []
    any_fixed = False
    for url, spoiler in urls.items():
        for fixer in link_types:
            if fixer.pattern.match(url):
                url = fixer.fix(url)
                if language and fixer.translatable:
                    url = f"{url.rstrip('/')}/{language}"
                any_fixed = True
                break
        spoiled_url = f"|| {url} ||"
        if spoiled_url in out and not spoiler:
            continue
        if url in out and spoiler:
            out.remove(url)
        if url not in out and spoiled_url not in out:
            out.append(spoiled_url if spoiler else url)

    return "\n".join(out) if any_fixed else None


class LinkFixer(commands.Cog):
    """Sends modified links to embed content from popular social media sites."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=44141349)
        self.config.register_guild(**{
            "enabled": False,
            "disabled_links": list(DEFAULT_DISABLED_LINKS),
            "language": None,
        })
        self.enabled_guilds: List[int] = []
        self.disabled_links: Dict[int, List[str]] = {}

    async def cog_load(self):
        all_guilds = await self.config.all_guilds()
        for gid, config in all_guilds.items():
            if config.get("enabled", False):
                self.enabled_guilds.append(gid)
                self.disabled_links[gid] = config.get("disabled_links", DEFAULT_DISABLED_LINKS)

    async def red_delete_data_for_user(self, *args, **kwargs):
        """Nothing to delete"""
        pass

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.guild.id not in self.enabled_guilds or message.author == message.guild.me:
            return
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return
        if not await self.is_valid_red_message(message):
            return

        link_types = [link for link in ALL_LINKS if link.name not in self.disabled_links.get(message.guild.id, [])]
        language = await self.config.guild(message.guild).language()
        fixed = fix_links(message.content, link_types, language)
        if not fixed:
            return

        fixed = f"-# {message.author.mention} I fixed the links so the content embeds better.\n" + fixed
        await message.channel.send(fixed, allowed_mentions=discord.AllowedMentions.none())
        if message.channel.permissions_for(message.guild.me).manage_messages:
            try:
                await message.edit(suppress=True)
            except discord.NotFound:
                pass

    @app_commands.command(name="fixlink", description="Send a fixed social media link with better embeds.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.choices(language=[app_commands.Choice(name="Unchanged", value=""),
                                    app_commands.Choice(name="English", value="en")])
    @app_commands.describe(link="One or more links to send as fixed embeds.",
                           language="If the provider supports it, translate the contents of the embed.")
    async def fix_links_command(self, inter: discord.Interaction, link: str, language: str = ""):
        disallowed_links = self.disabled_links.get(inter.guild.id, []) if inter.guild else DEFAULT_DISABLED_LINKS
        link_types = [link for link in ALL_LINKS if link.name not in disallowed_links]
        fixed = fix_links(link, link_types, language)
        if fixed:
            await inter.response.send_message(fixed, allowed_mentions=discord.AllowedMentions.none())
        elif GENERIC_LINK.search(link):
            await inter.response.send_message("The link(s) you provided are not supported, sorry!", ephemeral=True)
        else:
            await inter.response.send_message("You didn't provide a valid link!", ephemeral=True)

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return (
            isinstance(message.author, discord.Member)
            and await self.bot.allowed_by_whitelist_blacklist(message.author)
            and await self.bot.ignored_channel_or_guild(message)
            and not await self.bot.cog_disabled_in_guild(self, message.guild)
        )

    
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
            self.disabled_links[ctx.guild.id] = await self.config.guild(ctx.guild).disabled_links()
        await ctx.reply(f"✅ LinkFixer enabled in {ctx.guild.name}")

    @command_linkfixer.command(name="disable")
    async def command_linkfixer_disable(self, ctx: commands.Context):
        """Disable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(False)
        if ctx.guild.id in self.enabled_guilds:
            self.enabled_guilds.remove(ctx.guild.id)
        await ctx.reply(f"⛔ LinkFixer disabled in {ctx.guild.name}")

    
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
        await ctx.reply(f"⛔ Embeds will not be translated.")

    
    @command_linkfixer.group(name="links", aliases=["link", "fix"], invoke_without_command=True)
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
        await ctx.send("-# (Links will be fixed with the first matching fixer in the list)\n>>> " + "\n".join(links))

    @command_linkfixer_links.command(name="enable", aliases=["add"])
    async def command_linkfixer_links_enable(self, ctx: commands.Context, *link_names: str):
        """Enables one or more link fixes."""
        assert ctx.guild
        if ctx.guild.id not in self.enabled_guilds:
            return await ctx.reply(f"⚠️ LinkFixer is not enabled in {ctx.guild.name}")
        if not link_names:
            return await ctx.send_help()
        link_names = tuple(name.casefold() for name in link_names)
        all_links = set(link.name for link in ALL_LINKS)
        if len(link_names) == 1 and link_names[0] == "all":
            link_names = tuple(all_links)
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(set(disabled_links) - set(link_names))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        invalid_links = list(set(link_names) - all_links)
        if invalid_links:
            await ctx.send("⚠️ Invalid options: " + ", ".join([f"`{link}`" for link in invalid_links]))
        else:
            await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)

    @command_linkfixer_links.command(name="disable", aliases=["remove"])
    async def command_linkfixer_links_disable(self, ctx: commands.Context, *link_names: str):
        """Disables one or more link fixes."""
        assert ctx.guild
        if ctx.guild.id not in self.enabled_guilds:
            return await ctx.reply(f"⚠️ LinkFixer is not enabled in {ctx.guild.name}")
        if not link_names:
            return await ctx.send_help()
        link_names = tuple(name.casefold() for name in link_names)
        all_links = set(link.name for link in ALL_LINKS)
        if len(link_names) == 1 and link_names[0] == "all":
            link_names = tuple(all_links)
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(all_links & (set(disabled_links) | set(link_names)))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        invalid_links = list(set(link_names) - all_links)
        if invalid_links:
            await ctx.send("⚠️ Invalid options: " + ", ".join([f"`{link}`" for link in invalid_links]))
        else:
            await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)
