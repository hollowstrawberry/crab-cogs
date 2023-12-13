import discord
import booru
import json
import re
import logging
from redbot.core import commands, app_commands

log = logging.getLogger("red.crab-cogs.boorucog")

EMBED_COLOR = 0xD7598B
EMBED_ICON = "https://i.imgur.com/FeRu6Pw.png"
IMAGE_TYPES = (".png", ".jpeg", ".jpg", ".webp")
TAG_BLACKLIST = "loli guro video"

class Booru(commands.Cog):
    """Searches images on Gelbooru with slash command and tag completion support."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.gel = None

    async def cog_load(self):
        keys = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = keys.get("api_key"), keys.get("user_id")
        if api_key and user_id:
            self.gel = booru.Gelbooru(api_key, user_id)
        else:
            self.gel = booru.Gelbooru()
        pass

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.hybrid_command(aliases=["gelbooru"])
    @app_commands.describe(tags="Has autocomplete. Spaces will separate tags.")
    async def booru(self, ctx: commands.Context, tags: str):
        """Finds an image on Gelbooru. Type tags separated by spaces.

        As a slash command, will provide suggestions for the latest tag typed.
        Will be limited to safe searches in non-NSFW channels.
        Type - before a tag to exclude it.
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
        embed.set_author(name="Gelbooru Post", url=result.get("post_url", None), icon_url=EMBED_ICON)
        embed.set_image(url=result["file_url"] if result["width"]*result["height"] < 4200000 else result["sample_url"])
        if result.get("source", ""):
            embed.description = f"[🔗 Original Source]({result['source']})"
        embed.set_footer(text=f"⭐ {result.get('score', 0)}")
        await ctx.send(embed=embed)

    @booru.autocomplete("tags")
    async def tags_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.strip()
        if not current:
            results = ["None", "full_body", "upper_body", "-excluded_tag"]
            if interaction.channel.nsfw:
                results += ["rating:general", "rating:sensitive", "rating:questionable", "rating:explicit"]
        else:
            if ' ' in current:
                previous, last = current.rsplit(' ', maxsplit=1)
            else:
                previous, last = "", current
            try:
                if "rating" in last.lower():
                    results = ["rating:general"]
                    if interaction.channel.nsfw:
                        results += ["rating:sensitive", "rating:questionable", "rating:explicit"]
                else:
                    excluded = last.startswith("-")
                    last = last.lstrip("-")
                    response = await self.gel.find_tags(query=f"*{last}*")
                    results = json.loads(response)[:20]
                    if excluded:
                        results = [f"-{res}" for res in results]
            except Exception as e:
                log.error("Failed to load Gelbooru tags", exc_info=e)
                results = ["Error"]
            else:
                if previous:
                    results = [f"{previous} {res}" for res in results]
        return [discord.app_commands.Choice(name=i, value=i) for i in results]
