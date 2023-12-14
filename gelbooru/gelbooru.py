import discord
import booru
import json
import re
import logging
from redbot.core import commands, app_commands, Config

log = logging.getLogger("red.crab-cogs.boorucog")

EMBED_COLOR = 0xD7598B
EMBED_ICON = "https://i.imgur.com/FeRu6Pw.png"
IMAGE_TYPES = (".png", ".jpeg", ".jpg", ".webp", ".gif")
TAG_BLACKLIST = "loli guro video"

class Booru(commands.Cog):
    """Searches images on Gelbooru with slash command and tag completion support."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.gel = None
        self.tag_cache = {}
        self.config = Config.get_conf(self, identifier=62667275)
        self.config.register_global(tag_cache={})

    async def cog_load(self):
        self.tag_cache = await self.config.tag_cache()
        keys = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = keys.get("api_key"), keys.get("user_id")
        if api_key and user_id:
            self.gel = booru.Gelbooru(api_key, user_id)
        else:
            self.gel = booru.Gelbooru()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.hybrid_command(aliases=["gelbooru"])
    @app_commands.describe(tags="Will suggest tags with autocomplete. Separate tags with spaces.")
    async def booru(self, ctx: commands.Context, *, tags: str):
        """Finds an image on Gelbooru. Type tags separated by spaces.

        As a slash command, will provide suggestions for the latest tag typed.
        Will be limited to safe searches in non-NSFW channels.
        Type - before a tag to exclude it.
        You can add score:>NUMBER to have a minimum score above a number.
        You can add rating:general / rating:sensitive / rating:questionable / rating:explicit"""

        tags = tags.strip()
        if tags.lower() in ["none", "error"]:
            tags = ""

        if not ctx.channel.nsfw:
            tags = re.sub(" ?rating:[^ ]+", "", tags)
            tags += " rating:general"

        result = {}
        while not result.get("file_url", "").endswith(IMAGE_TYPES):
            try:
                response = await self.gel.search(query=tags, block=TAG_BLACKLIST, gacha=True)
                result = json.loads(response)
            except KeyError:
                description = "💨 No results..."
                if not ctx.channel.nsfw:
                    description += " (safe mode)"
                await ctx.send(embed=discord.Embed(description=description, color=EMBED_COLOR))
                return
            except Exception as e:
                log.error("Failed to grab image from Gelbooru", exc_info=e)
                await ctx.send("Sorry, there was an error trying to grab an image from Gelbooru. Please try again or contact the bot owner.")
                return

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Booru Post", url=result.get("post_url", None), icon_url=EMBED_ICON)
        embed.set_image(url=result["file_url"] if result["width"]*result["height"] < 4200000 else result["sample_url"])
        if result.get("source", ""):
            embed.description = f"[🔗 Original Source]({result['source']})"
        embed.set_footer(text=f"⭐ {result.get('score', 0)}")
        await ctx.send(embed=embed)

    @booru.autocomplete("tags")
    async def tags_autocomplete(self, interaction: discord.Interaction, current: str):
        if current is None:
            current = ""
        if ' ' in current:
            previous, last = [x.strip() for x in current.rsplit(' ', maxsplit=1)]
        else:
            previous, last = "", current.strip()
        excluded = last.startswith('-')
        last = last.lstrip('-')
        if not last and not excluded:
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
            results = ["rating:general"]
            if interaction.channel.nsfw:
                results += ["rating:sensitive", "rating:questionable", "rating:explicit"]
        else:
            try:
                results = await self.get_tags(last)
            except Exception as e:
                log.error("Failed to load Gelbooru tags", exc_info=e)
                results = ["Error"]
                previous = None
        if excluded:
            results = [f"-{res}" for res in results]
        if previous:
            results = [f"{previous} {res}" for res in results]
        return [discord.app_commands.Choice(name=i, value=i) for i in results]

    async def get_tags(self, query):
        if query in self.tag_cache:
            return self.tag_cache[query].split(' ')
        response = await self.gel.find_tags(query=f"*{query}*")
        results = json.loads(response)
        results = [res for res in results if '%' not in res]
        results = results[:20]
        self.tag_cache[query] = ' '.join(results)
        async with self.config.tag_cache() as tag_cache:
            tag_cache[query] = self.tag_cache[query]
        return results
