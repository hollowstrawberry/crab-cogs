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
            converted_message: discord.Message = await commands.MessageConverter().convert(ctx=context, argument=user_input)
            to_translate = converted_message.content
            to_reply = converted_message
        except commands.BadArgument:
            if user_input:
                to_translate = user_input
                to_reply = context.message
            elif context.message.reference and isinstance(context.message.reference.resolved, discord.Message):
                to_translate = context.message.reference.resolved.content
                to_reply = context.message.reference.resolved

        if to_reply and to_reply.channel.id != context.channel.id:
            to_reply = context.message

        return CUSTOM_EMOJI.sub("", to_translate or "").strip(), to_reply

    @staticmethod
    def result_embed(res: googletrans.models.Translated, color: discord.Color):
        embeds: typing.List[discord.Embed] = []
        for p in pagify(res.text, delims=["\n", " "]):
            embeds.append(discord.Embed(description=p, color=color))
        embeds[-1].set_footer(text=f"{googletrans.LANGUAGES[res.src.lower()].title()} → {googletrans.LANGUAGES[res.dest.lower()].title()}")
        return embeds

    @commands.bot_has_permissions(embed_links=True)
    @commands.group(name="translate", invoke_without_command=True)
    async def translate_automatic(self, ctx: commands.Context, *, optional_input: str = ""):
        """Translate something into your preferred language. Can also reply to a message to translate it."""
        message = ctx.message
        if not optional_input and ctx.message.reference:
            message = ctx.message.reference.cached_message or await ctx.channel.fetch_message(ctx.message.reference.message_id)
            optional_input = message.content if message else None
        if not optional_input:
            return await ctx.send(MISSING_MESSAGE)
        language = await self.config.user(ctx.author).preferred_language()
        await self.translate_to(ctx, language, optional_input=optional_input)
        
    @commands.command(name="translateslash", hidden=True)
    async def translate_slash(self, ctx: commands.Context, *, msg: str):
        """Translate a message into your preferred language."""
        id = msg.split(' ')[1].split('=')[1]
        language = await self.config.user(ctx.author).preferred_language()
        await self.translate_to(ctx, language, optional_input=id)
        
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
            return await ctx.channel.send(embed=discord.Embed(description=TRANSLATION_FAILED, color=discord.Color.red()))

        result_embeds = self.result_embed(result, await ctx.embed_color())

        if optional_input.isnumeric(): # probably a slash command
            return await ctx.send(embed=result_embeds[0], mention_author=False)

        try:
            await to_reply.reply(embed=result_embeds[0], mention_author=False)
        except discord.HTTPException:
            await to_reply.channel.send(embed=result_embeds[0])
        for e in result_embeds[1:]:
            await to_reply.channel.send(embed=e)
