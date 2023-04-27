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
import typing
import functools
import googletrans, googletrans.models

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify

MISSING_INPUTS = "Please provide a message ID/link, some text to translate, or reply to the original message."
MISSING_MESSAGE = "`Nothing to translate.`"
LANGUAGE_NOT_FOUND = "`That's not an available language, please try again.`"
TRANSLATION_FAILED = "`Something went wrong while translating. If this keeps happening, contact the bot owner.`"

CUSTOM_EMOJI = re.compile("<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>")  # Thanks R.Danny


class EasyTranslate(commands.Cog):
    """Translate messages using Google Translate for free. Supports context menu commands with slashtags:\n  [p]st global message "Translate" {c:translateslash {message} {hide}}"""

    def __init__(self, bot):
        self.bot = bot
        self.translator = googletrans.Translator()
        self.config = Config.get_conf(self, identifier=14000606, force_registration=True)
        self.config.register_user(preferred_language="english")

    @staticmethod
    def convert_language(language: str):
        language = googletrans.LANGUAGES.get(language, language).lower()
        if language in ("zh", "ch", "chinese"):
            language = "chinese (simplified)"
        if language not in googletrans.LANGUAGES.values():
            language = None
        return language

    @staticmethod
    async def convert_input(context: commands.Context, user_input: str):
        to_translate, to_reply = None, None
        try:
            if not user_input:
                raise commands.BadArgument
            # case 1: argument points to a message
            converted_message: discord.Message = await commands.MessageConverter().convert(ctx=context, argument=user_input)
            to_translate = converted_message.content
            to_reply = converted_message
        except commands.BadArgument:
            # case 2: argument is text to translate
            if user_input:
                to_translate = user_input
                to_reply = context.message
            # case 3: argument is empty but there is a message reference
            elif context.message.reference and isinstance(context.message.reference.resolved, discord.Message):
                to_translate = context.message.reference.resolved.content
                to_reply = context.message.reference.resolved

        if to_reply and to_reply.channel.id != context.channel.id:
            to_reply = context.message

        return CUSTOM_EMOJI.sub("", to_translate or "").strip(), to_reply

    @staticmethod
    def result_embed(res: googletrans.models.Translated, color: discord.Color, author: discord.Member):
        embed = discord.Embed(description=res.text[:3990], color=color)
        embed.set_footer(text=f"{googletrans.LANGUAGES.get(res.src.lower(), res.src).title()} → {googletrans.LANGUAGES.get(res.dest.lower(), res.dest).title()}")
        if author:
            embed.set_author(name=author.display_name, icon_url=str(author.avatar_url))
        return embed

    @commands.bot_has_permissions(embed_links=True)
    @commands.group(name="translate", invoke_without_command=True)
    async def translate_automatic(self, ctx: commands.Context, *, optional_input: str = ""):
        """Translate something into your preferred language. Can also reply to a message to translate it."""
        language = await self.config.user(ctx.author).preferred_language()
        await self.translate_to(ctx, language, optional_input=optional_input)

    @commands.bot_has_permissions(embed_links=True)
    @translate_automatic.command(name="to")
    async def translate_to(self, ctx: commands.Context, to_language: str, *, optional_input: str = ""):
        """Translate something into a specific language. Can also reply to a message to translate it."""
        if not (to_language := self.convert_language(to_language)):
            return await ctx.send(LANGUAGE_NOT_FOUND)
        if not optional_input.isnumeric(): # probably not a slash command
            await ctx.channel.trigger_typing()

        to_translate, to_reply = await self.convert_input(ctx, optional_input)
        if not to_translate or not to_reply:
            return await ctx.send(MISSING_INPUTS)
        
        try:
            task = functools.partial(self.translator.translate, text=to_translate, dest=to_language)
            result: googletrans.models.Translated = await self.bot.loop.run_in_executor(None, task)
        except Exception:
            return await ctx.send(embed=discord.Embed(description=TRANSLATION_FAILED, color=discord.Color.red()))

        embed = self.result_embed(result, await ctx.embed_color(), to_reply.author if (to_reply != ctx.message and not ctx.message.reference) else None)

        if optional_input.isnumeric(): # probably a slash command
            return await ctx.send(embed=embed)

        try:
            await to_reply.reply(embed=embed, mention_author=False)
        except discord.HTTPException:
            await ctx.send(embed=embed)

    @commands.command(name="translateslash", hidden=True)
    async def translate_slash(self, ctx: commands.Context, *, msg: str):
        """Translate a message into your preferred language."""
        id = msg.split(' ')[1].split('=')[1]
        await self.translate_automatic(ctx, optional_input=id)

    @commands.command(name="setmylanguage")
    async def set_my_language(self, ctx:commands.Context, *, language: str):
        """Set your preferred language when translating."""
        language = self.convert_language(language)
        if not language:
            return await ctx.send(LANGUAGE_NOT_FOUND)
        await self.config.user(ctx.author).preferred_language.set(language)
        # Success message in target language
        try:
            success = f"✅ When you translate a message, its language will be {language}"
            task = functools.partial(self.translator.translate, text=success, dest=language)
            result: googletrans.models.Translated = await self.bot.loop.run_in_executor(None, task)
            await ctx.send(result.text)
        except:
            await ctx.send("✅")
