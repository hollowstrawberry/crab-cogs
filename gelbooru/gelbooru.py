import io
import re
import html
import random
import logging
import aiohttp
import discord
from typing import Optional, List, Union
from redbot.core import commands, app_commands

from gelbooru.base import BooruBase
from gelbooru.constants import EMBED_COLOR, EMBED_ICON, HEADERS, IMAGE_TYPES, MAX_OPTION_SIZE, MAX_OPTIONS, URL_PATTERN
from gelbooru.constants import RATING_EXPLICIT, RATING_GENERAL, RATING_QUESTIONABLE, RATING_SENSITIVE
from gelbooru.image_view import ImageView
from gelbooru.utils import is_nsfw, prepare_query

log = logging.getLogger("red.crab-cogs.gelbooru")


class Booru(BooruBase):
    """Searches images on Gelbooru with slash command and tag completion support."""

    async def cog_load(self):
        self.tag_cache = await self.config.tag_cache()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.is_owner()
    @commands.command()
    async def boorudeletecache(self, ctx: commands.Context):
        del self.tag_cache
        self.tag_cache = {}
        async with self.config.tag_cache() as tag_cache:
            tag_cache.clear()
        await ctx.tick(message="Booru cache deleted")


    @commands.hybrid_command(name="booru", aliases=["gelbooru"])  # type: ignore
    @app_commands.describe(tags="Will suggest tags with autocomplete. Separate tags with spaces.")
    async def booru_cmd(self, ctx: commands.Context, *, tags: str):
        """Finds an image on Gelbooru. Type tags separated by spaces.

        As a slash command, will provide suggestions for the latest tag typed.
        Won't repeat the same post until all posts with the same search have been exhausted.
        Will be limited to safe searches in non-NSFW channels.
        Type - before a tag to exclude it.
        You can add score:>NUMBER to have a minimum score above a number.
        You can add rating:general / rating:sensitive / rating:questionable / rating:explicit"""
        await self.booru(ctx, tags)
        

    async def booru(self, ctx: Union[discord.Interaction, commands.Context], query: str):
        assert isinstance(ctx.channel, Union[discord.TextChannel, discord.Thread])

        send = ctx.send if isinstance(ctx, commands.Context) else  ctx.followup.send
        user = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        query = prepare_query(query, is_nsfw(ctx.channel))

        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer(thinking=True)

        try:
            result = await self.grab_image(query, ctx.channel.id)
        except (aiohttp.ClientError, KeyError):
            log.exception("Failed to grab image from Gelbooru")
            return await send("Sorry, there was an error trying to grab an image from Gelbooru! Please try again or contact the bot owner.")

        if not result:
            description = "💨 No results..."
            if not is_nsfw(ctx.channel):
                description += " (safe mode)"
            embed = discord.Embed(description=description, color=EMBED_COLOR)
            view = ImageView(self, ctx.channel, user, query, None)
            return await send(embed=embed, view=view)

        image_url = result.get("sample_url", "") or result["file_url"]
        post_url = f"https://gelbooru.com/index.php?page=post&s=view&id={result['id']}"
        try:
            async with self.session.get(image_url, allow_redirects=False, headers=HEADERS) as resp:
                image_data = await resp.read()
            filename = image_url.split("/")[-1]
            file = discord.File(io.BytesIO(image_data), filename=filename)
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_author(name="Booru Post", url=post_url, icon_url=EMBED_ICON)
            embed.set_image(url=f"attachment://{filename}")
            if result.get("source", ""):
                if URL_PATTERN.match(result["source"]):
                    embed.description = f"[🔗 Original Source]({result['source']})"
                else:
                    embed.description = f"🔗 Original Source: {result['source']}"
            embed.set_footer(text=f"⭐ {result.get('score', 0)}")
            view = ImageView(self, ctx.channel, user, query, result.get("tags", ""))
            msg = await send(embed=embed, view=view, file=file)
            if msg and msg.embeds:
                view.image_url = msg.embeds[0].image.url
        except Exception as error:
            log.error(f"{type(error).__name__}: {error} {post_url=}")
            await send("Sorry, there was an error trying to grab the image from Gelbooru! Please try again or contact the bot owner.")


    @commands.hybrid_command(aliases=["boorutags"])  # type: ignore
    async def boorutag(self, ctx: commands.Context, *, tag_search: str):
        """Searches for tags on Gelbooru."""
        tag_search = tag_search.replace(" ", "_").strip()
        results = await self.tags_autocomplete(None, tag_search)
        if results:
            results_str = ", ".join([f"`{choice.name}`" for choice in results])
            await ctx.send(f"> Matches for `{tag_search}` in order of popularity:\n{results_str}")
        else:
            await ctx.send(f"No matches for `{tag_search}`")


    @booru_cmd.autocomplete("tags")
    async def booru_tags_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.tags_autocomplete(interaction, current)

    async def tags_autocomplete(self, interaction: Optional[discord.Interaction], current: str):
        if current is None:
            current = ""
        if ' ' in current:
            previous, last = [x.strip() for x in current.rsplit(' ', maxsplit=1)]
        else:
            previous, last = "", current.strip()

        excluded = last.startswith('-')
        last = last.lstrip('-')
        nsfw = interaction and isinstance(interaction.channel, discord.abc.Messageable) and is_nsfw(interaction.channel)

        if not last and not excluded:
            # suggestions
            results = []
            if "full_body" not in previous:
                results.append("full_body")
            if "-" not in previous:
                results.append("-excluded_tag")
            if "score" not in previous:
                results += ["score:>10", "score:>100"]
            if nsfw and "rating" not in previous:
                results += [RATING_GENERAL, RATING_SENSITIVE, RATING_QUESTIONABLE, RATING_EXPLICIT]

        elif "rating" in last.lower():
            if nsfw:
                ratings = [RATING_GENERAL, RATING_SENSITIVE, RATING_QUESTIONABLE, RATING_EXPLICIT]
                results = []
                for r in tuple(ratings):
                    if r.startswith(last.lower()):
                        results.append(r)
                        ratings.remove(r)
                        break
                for r in ratings:
                    results.append(r)
            else:
                results = [RATING_GENERAL]
                excluded = False

        elif "score" in last.lower():
            excluded = False
            results = ["score:>10", "score:>100", "score:>1000"]
            if re.match(r"score:>(\d+)", last):
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
            max_len_result = max(results, key=lambda r: len(r))
            while len(f"{previous} {max_len_result}") > MAX_OPTION_SIZE and ' ' in previous:
                previous = previous.split(' ', maxsplit=1)[1]
            results = [f"{previous} {res}" for res in results]

        return [discord.app_commands.Choice(name=i, value=i) for i in results]


    async def grab_tags(self, query) -> List[str]:
        if query in self.tag_cache:
            return self.tag_cache[query].split(' ')

        params = {
            "page": "dapi",
            "s": "tag",
            "q": "index",
            "json": 1,
            "sort": "desc",
            "order_by": "index_count",
            "name_pattern": f"%{query.lower()}%"
        }

        api = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = api.get("api_key"), api.get("user_id")
        if api_key and user_id:
            params.update({"api_key": api_key, "user_id": user_id})

        async with self.session.get("https://gelbooru.com/index.php", params=params, headers=HEADERS) as resp:
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


    async def grab_image(self, query: str, channel_id: int) -> dict:
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "limit": 100,
            "tags": query,
        }

        api = await self.bot.get_shared_api_tokens("gelbooru")
        api_key, user_id = api.get("api_key"), api.get("user_id")
        if api_key and user_id:
            params.update({"api_key": api_key, "user_id": user_id})

        async with self.session.get("https://gelbooru.com/index.php", params=params, headers=HEADERS) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data or "post" not in data:
            return {}
        images = [img for img in data["post"] if img["file_url"].endswith(IMAGE_TYPES)]

        # prevent duplicates
        if channel_id not in self.image_cache:
            self.image_cache[channel_id] = []
        if all(img["id"] in self.image_cache[channel_id] for img in images):
            self.image_cache[channel_id] = self.image_cache[channel_id][-1:]
        if len(images) > 1:
            images = [img for img in images if img["id"] not in self.image_cache[channel_id]]

        choice = random.choice(images)
        self.image_cache[channel_id].append(choice["id"])
        return choice
