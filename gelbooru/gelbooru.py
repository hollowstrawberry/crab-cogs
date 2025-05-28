import re
import html
import random
import logging
import urllib.parse
import aiohttp
import discord
from typing import Optional, List, Dict
from expiringdict import ExpiringDict
from redbot.core import commands, app_commands, Config

log = logging.getLogger("red.crab-cogs.boorucog")

EMBED_COLOR = 0xD7598B
EMBED_ICON = "https://i.imgur.com/FeRu6Pw.png"
IMAGE_TYPES = (".png", ".jpeg", ".jpg", ".webp", ".gif")
TAG_BLACKLIST = ["loli", "shota", "guro", "video"]
HEADERS = {
    "User-Agent": "crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}

MAX_OPTIONS = 25
MAX_OPTION_SIZE = 100


class Booru(commands.Cog):
    """Searches images on Gelbooru with slash command and tag completion support."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.session = aiohttp.ClientSession(headers=HEADERS)
        self.tag_cache: Dict[str, str] = {}
        self.image_cache: Dict[int, List[int]] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.config = Config.get_conf(self, identifier=62667275)
        self.config.register_global(tag_cache={})

    async def cog_load(self):
        self.tag_cache = await self.config.tag_cache()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.command()
    @commands.is_owner()
    async def boorudeletecache(self, ctx: commands.Context):
        del self.tag_cache
        self.tag_cache = {}
        async with self.config.tag_cache() as tag_cache:
            tag_cache.clear()
        await ctx.tick(message="Booru cache deleted")


    @commands.hybrid_command(aliases=["gelbooru"])
    @app_commands.describe(tags="Will suggest tags with autocomplete. Separate tags with spaces.")
    async def booru(self, ctx: commands.Context, *, tags: str):
        """Finds an image on Gelbooru. Type tags separated by spaces.

        As a slash command, will provide suggestions for the latest tag typed.
        Won't repeat the same post until all posts with the same search have been exhausted.
        Will be limited to safe searches in non-NSFW channels.
        Type - before a tag to exclude it.
        You can add score:>NUMBER to have a minimum score above a number.
        You can add rating:general / rating:sensitive / rating:questionable / rating:explicit"""

        tags = tags.strip()
        if tags.lower() in ["none", "error"]:
            tags = ""
        if not ctx.channel.nsfw:
            tags = re.sub(r"\s?rating:\S+", "", tags)
            tags += " rating:general"

        try:
            result = await self.grab_image(tags, ctx)
        except (aiohttp.ClientError, KeyError):
            log.exception("Failed to grab image from Gelbooru")
            await ctx.send("Sorry, there was an error trying to grab an image from Gelbooru. Please try again or contact the bot owner.")
            return

        if not result:
            description = "💨 No results..."
            if not ctx.channel.nsfw:
                description += " (safe mode)"
            await ctx.send(embed=discord.Embed(description=description, color=EMBED_COLOR))
            return

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Booru Post", url=f"https://gelbooru.com/index.php?page=post&s=view&id={result['id']}", icon_url=EMBED_ICON)
        embed.set_image(url=result["file_url"] if result["width"]*result["height"] < 4200000 else result["sample_url"])
        if result.get("source", ""):
            embed.description = f"[🔗 Original Source]({result['source']})"
        embed.set_footer(text=f"⭐ {result.get('score', 0)}")
        await ctx.send(embed=embed)


    @commands.hybrid_command(aliases=["boorutags"])
    async def boorutag(self, ctx: commands.Context, *, tag_search: str):
        """Searches for tags on Gelbooru."""
        tag_search = tag_search.replace(" ", "_").strip()
        results = await self.tags_autocomplete(None, tag_search)
        if results:
            results_str = ", ".join([f"`{choice.name}`" for choice in results])
            await ctx.send(f"> Matches for `{tag_search}` in order of popularity:\n{results_str}")
        else:
            await ctx.send(f"No matches for `{tag_search}`")


    @booru.autocomplete("tags")
    async def tags_autocomplete(self, interaction: Optional[discord.Interaction], current: str):
        if current is None:
            current = ""
        if ' ' in current:
            previous, last = [x.strip() for x in current.rsplit(' ', maxsplit=1)]
        else:
            previous, last = "", current.strip()

        excluded = last.startswith('-')
        last = last.lstrip('-')

        if not last and not excluded:
            # suggestions
            results = []
            if "full_body" not in previous:
                results.append("full_body")
            if "-" not in previous:
                results.append("-excluded_tag")
            if "score" not in previous:
                results += ["score:>10", "score:>100"]
            if interaction.channel.nsfw and "rating" not in previous:
                results += ["rating:general", "rating:sensitive", "rating:questionable", "rating:explicit"]

        elif "rating" in last.lower():
            if interaction.channel.nsfw:
                ratings = ["rating:general", "rating:sensitive", "rating:questionable", "rating:explicit"]
                results = []
                for r in tuple(ratings):
                    if r.startswith(last.lower()):
                        results.append(r)
                        ratings.remove(r)
                        break
                for r in ratings:
                    results.append(r)
            else:
                results = ["rating:general"]
                excluded = False

        elif "score" in last.lower():
            excluded = False
            results = ["score:>10", "score:>100", "score:>1000"]
            if re.match(r"score:>([0-9]+)", last):
                if last in results:
                    results.remove(last)
                results.insert(0, last)

        else:
            try:
                results = await self.grab_tags(last)
            except (aiohttp.ClientError, KeyError):
                log.exception("Failed to load Gelbooru tags")
                results = ["Error"]
                previous = None

        if excluded:
            results = [f"-{res}" for res in results]
        if previous:
            while len(f"{previous} {res}") > MAX_OPTION_SIZE and ' ' in previous:
                previous = previous.split(' ', maxsplit=1)[1]
            results = [f"{previous} {res}" for res in results]

        return [discord.app_commands.Choice(name=i, value=i) for i in results]


    async def grab_tags(self, query) -> List[str]:
        if query in self.tag_cache:
            return self.tag_cache[query].split(' ')

        query = urllib.parse.quote(query.lower(), safe=' ')
        url = f"https://gelbooru.com/index.php?page=dapi&s=tag&q=index&json=1&sort=desc&order_by=index_count&name_pattern=%25{query}%25"

        api = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = api.get("api_key"), api.get("user_id")
        if api_key and user_id:
            url += f"&api_key={api_key}&user_id={user_id}"

        async with self.session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data or "tag" not in data:
            return []

        results = [tag["name"] for tag in data["tag"]][:MAX_OPTIONS]
        results = [html.unescape(tag) for tag in results]
        self.tag_cache[query] = ' '.join(results)
        async with self.config.tag_cache() as tag_cache:
            tag_cache[query] = self.tag_cache[query]
        return results


    async def grab_image(self, query: str, ctx: commands.Context) -> dict:
        query = urllib.parse.quote(query.lower(), safe=' ')
        tags = [tag for tag in query.split(' ') if tag]
        tags = [tag for tag in tags if tag not in TAG_BLACKLIST]
        tags += [f"-{tag}" for tag in TAG_BLACKLIST]
        query = ' '.join(tags)
        url = "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit=1000&tags=" + query.replace(' ', '+')

        api = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = api.get("api_key"), api.get("user_id")
        if api_key and user_id:
            url += f"&api_key={api_key}&user_id={user_id}"

        async with self.session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data or "post" not in data:
            return {}
        images = [img for img in data["post"] if img["file_url"].endswith(IMAGE_TYPES)]

        # prevent duplicates
        key = ctx.channel.id
        if key not in self.image_cache:
            self.image_cache[key] = []
        if all(img["id"] in self.image_cache[key] for img in images):
            self.image_cache[key] = self.image_cache[key][-1:]
        if len(images) > 1:
            images = [img for img in images if img["id"] not in self.image_cache[key]]

        choice = random.choice(images)
        self.image_cache[key].append(choice["id"])
        return choice
