import discord
import booru
import json
import re
import logging
from redbot.core import commands

log = logging.getLogger("red.crab-cogs.boorucog")

IMAGE_TYPES = (".png", ".jpeg", ".jpg", ".webp")
TAG_BLACKLIST = "loli guro video"

class Booru(commands.Cog):
    """Searches images on Gelbooru with slash command and tag completion support."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.gel = booru.Gelbooru()

    async def cog_load(self):
        pass

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.hybrid_command(aliases=["gelbooru"])
    async def booru(self, ctx: commands.Context, tags: str):
        """Finds an image on Gelbooru. Type tags separated by spaces.

        As a slash command, will provide autocomplete for the latest tag typed.
        Will be limited to safe searches in non-NSFW channels.
        Type - before a tag to exclude it.
        You can add score:>10 to set a minimum image score (10 in this case)
        You can add rating:general / rating:sensitive / rating:questionable / rating:explicit"""

        tags = tags.strip()
        if tags.lower() == "none":
            tags = ""

        if not ctx.channel.nsfw:
            tags = re.sub(" ?rating:[^ ]+", "", tags)
            tags += " rating:general"

        result = {}
        while not result.get("file_url", "").endswith(IMAGE_TYPES):
            try:
                response = await self.gel.search(query=tags, block=TAG_BLACKLIST, gacha=True)
                result = json.loads(response)
            except Exception as e:
                log.error("Failed to grab image from Gelbooru", exc_info=e)
                await ctx.send("Sorry, there was an error trying to grab an image from Gelbooru. Please try again or contact the bot owner.")
                return

        embed = discord.Embed(color=0xD7598B)
        embed.set_author(name="Gelbooru Post", url=result.get("post_url", None), icon_url="https://i.imgur.com/FeRu6Pw.png")
        embed.set_image(url=result.get("file_url", result.get("sample_url", result["preview_url"])))
        if result.get("source", ""):
            embed.description = f"[🔗 Original Source]({result['source']})"
        embed.set_footer(text=f"⭐ {result.get('score', 0)}")
        await ctx.send(embed=embed)

    @booru.autocomplete("tags")
    async def tags_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.strip()
        if not current:
            results = ["None"]
        else:
            previous, last = current.rsplit(' ', maxsplit=1)
            response = await self.gel.find_tags(query=f"*{last}*")
            results = json.loads(response)
            results = [f"{previous} {res}" for res in results][:10]
            log.info(results)
        return [discord.app_commands.Choice(name=i, value=i) for i in results]
