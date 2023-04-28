"""
https://github.com/hollowstrawberry/OB13-Cogs/blob/main/translate/translate.py

MIT License
Copyright (c) 2021-present Obi-Wan3
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import re
import functools
import googletrans
import discord
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
from typing import Union
from googletrans.models import Translated

MISSING_INPUTS = "Please provide some text to translate, or reply to a message to translate it."
MISSING_MESSAGE = "`Nothing to translate.`"
LANGUAGE_NOT_FOUND = "`That's not an available language, please try again.`"
TRANSLATION_FAILED = "`Something went wrong while translating. If this keeps happening, contact the bot owner.`"

CUSTOM_EMOJI = re.compile("<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>")  # Thanks R.Danny


class EasyTranslate(commands.Cog):
    """Translate messages using Google Translate for free. Supports context menu commands."""

    def __init__(self, bot):
        super().__init__()
        self.bot: Red = bot
        self.translator = googletrans.Translator()
        self.config = Config.get_conf(self, identifier=14000606, force_registration=True)
        self.config.register_user(preferred_language="english")
        self.context_menu = app_commands.ContextMenu(name='Translate', callback=self.translate_slash)
        self.bot.tree.add_command(self.context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @staticmethod
    def convert_language(language: str):
        language = googletrans.LANGUAGES.get(language, language).lower()
        if language in ("zh", "ch", "chinese"):
            language = "chinese (simplified)"
        if language not in googletrans.LANGUAGES.values():
            language = None
        return language

    @staticmethod
    def convert_input(user_input: str):
        return CUSTOM_EMOJI.sub("", user_input).strip()

    async def translate(self, ctx: Union[commands.Context, discord.Interaction],
                        language: str, *, content: str = None, message: discord.Message = None):
        """Translates a message or string and responds in the provided context."""
        if not (language := self.convert_language(language)):
            return await ctx.send(LANGUAGE_NOT_FOUND)
        if not content and not message:
            reference = ctx.message.reference
            if not reference:
                return await ctx.send(MISSING_INPUTS)
            message = reference.resolved or reference.cached_message or await ctx.channel.fetch_message(reference.message_id)
            if not message:
                return await ctx.send(MISSING_INPUTS)
        if not content:
            content = message.content
        content = self.convert_input(content)
        try:
            task = functools.partial(self.translator.translate, text=content, dest=language)
            result: Translated = await self.bot.loop.run_in_executor(None, task)
        except:
            fail_embed = discord.Embed(description=TRANSLATION_FAILED, color=discord.Color.red())
            if isinstance(ctx, discord.Interaction):
                return await ctx.response.send_message(embed=fail_embed, ephemeral=True)
            else:
                return await ctx.send(embed=fail_embed)

        embed = discord.Embed(description=result.text[:3990], color=await self.bot.get_embed_color(ctx.channel))
        source_language_name = googletrans.LANGUAGES.get(result.src.lower(), result.src).title()
        dest_language_name = googletrans.LANGUAGES.get(result.dest.lower(), result.dest).title()
        embed.set_footer(text=f"{source_language_name} → {dest_language_name}")

        if isinstance(ctx, discord.Interaction):
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            await ctx.response.send_message(embed=embed, ephemeral=True)
        elif message:
            await message.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(embed=embed)

    @commands.bot_has_permissions(embed_links=True)
    @commands.group(name="translate", invoke_without_command=True)
    async def translate_automatic(self, ctx: commands.Context, *, optional_input: str = ""):
        """Translate something into your preferred language. Can also reply to a message to translate it."""
        language = await self.config.user(ctx.author).preferred_language()
        await self.translate(ctx, language, content=optional_input)

    async def translate_slash(self, ctx: discord.Interaction, message: discord.Message):
        language = await self.config.user(message.author).preferred_language()
        await self.translate(ctx, language, message=message)

    @commands.bot_has_permissions(embed_links=True)
    @translate_automatic.command(name="to")
    async def translate_to(self, ctx: commands.Context, to_language: str, *, optional_input: str = ""):
        """Translate something into a specific language. Can also reply to a message to translate it."""
        await self.translate(ctx, to_language, content=optional_input)

    @commands.hybrid_command(name="setmylanguage")
    async def set_my_language(self, ctx: commands.Context, *, language: str):
        """Set your preferred language when translating."""
        language = self.convert_language(language)
        if not language:
            return await ctx.send(LANGUAGE_NOT_FOUND)
        await self.config.user(ctx.author).preferred_language.set(language)
        # Success message in target language
        try:
            success = f"✅ When you translate a message, its language will be {language}"
            task = functools.partial(self.translator.translate, text=success, dest=language)
            result: Translated = await self.bot.loop.run_in_executor(None, task)
            await ctx.send(result.text)
        except:
            await ctx.send("✅")
