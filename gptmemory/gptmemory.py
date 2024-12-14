import json
import logging
import asyncio
import aiohttp
import discord
from io import BytesIO
from datetime import datetime
from difflib import get_close_matches
from expiringdict import ExpiringDict
from openai import AsyncOpenAI
from tiktoken import encoding_for_model
from redbot.core import commands
from redbot.core.bot import Red

import gptmemory.defaults as defaults
from gptmemory.commands import GptMemoryBase
from gptmemory.utils import sanitize, make_image_content, process_image, get_text_contents
from gptmemory.schema import MemoryRecall, MemoryChangeList
from gptmemory.function_calling import all_function_calls
from gptmemory.constants import URL_PATTERN, RESPONSE_CLEANUP_PATTERN, IMAGE_EXTENSIONS, DISCORD_MESSAGE_LENGTH

log = logging.getLogger("red.crab-cogs.gptmemory")


class GptMemory(GptMemoryBase):
    """OpenAI-powered user with persistent memory."""

    def __init__(self, bot: Red):
        super().__init__(bot)
        self.openai_client = None
        self.image_cache = ExpiringDict(max_len=50, max_age_seconds=24*60*60)


    async def cog_load(self):
        await self.initialize_openai_client()
        all_config = await self.config.all_guilds()
        for guild_id, config in all_config.items():
            self.memory[guild_id] = config["memory"]


    async def cog_unload(self):
        if self.openai_client:
            await self.openai_client.close()


    async def initialize_openai_client(self):
        api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
        if not api_key:
            return
        self.openai_client = AsyncOpenAI(api_key=api_key)


    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openai":
            await self.initialize_openai_client()


    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        ctx: commands.Context = await self.bot.get_context(message)  # noqa
        if not await self.is_valid_trigger(ctx):
            return
        
        if URL_PATTERN.search(message.content):
            ctx = await self.wait_for_embed(ctx)

        await self.run_response(ctx) 


    async def is_valid_trigger(self, ctx: commands.Context) -> bool:
        if self.bot.user not in ctx.message.mentions:
            return False
        if ctx.author.bot:
            return False
        
        if await self.config.guild(ctx.guild).channel_mode() == "blacklist" \
                and ctx.channel.id in await self.config.guild(ctx.guild).channels():
            return False
        elif await self.config.guild(ctx.guild).channel_mode() == "whitelist" \
                and ctx.channel.id not in await self.config.guild(ctx.guild).channels():
            return False

        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return False
        if not await self.bot.ignored_channel_or_guild(ctx):
            return False
        if not await self.bot.allowed_by_whitelist_blacklist(ctx.author):
            return False
        
        if not self.openai_client:
            await self.initialize_openai_client()
        if not self.openai_client:
            return False
        
        return True


    @staticmethod
    async def wait_for_embed(ctx: commands.Context) -> commands.Context:
        for n in range(2):
            if ctx.message.embeds:
                return ctx
            await asyncio.sleep(1)
            ctx.message = await ctx.channel.fetch_message(ctx.message.id)
        return ctx


    async def run_response(self, ctx: commands.Context):
        if ctx.guild.id not in self.memory:
            self.memory[ctx.guild.id] = {}
        memories = ", ".join(self.memory[ctx.guild.id].keys()) or "[None]"

        async with ctx.channel.typing():
            messages = await self.get_message_history(ctx)
            recalled_memories = await self.execute_recaller(ctx, messages, memories)
            response_message = await self.execute_responder(ctx, messages, recalled_memories)
        messages.append(response_message)
        await self.execute_memorizer(ctx, messages, memories, recalled_memories)


    async def execute_recaller(self, ctx: commands.Context, messages: list[dict], memories: str) -> str:
        """
        Runs an openai completion with the chat history and a list of memories from the database
        and returns a parsed string of memories and their contents as chosen by the LLM.
        """
        system_prompt = {
            "role": "system",
            "content": (await self.config.guild(ctx.guild).prompt_recaller()).format(memories)
        }
        temp_messages = get_text_contents(messages)
        temp_messages.insert(0, system_prompt)
        response = await self.openai_client.beta.chat.completions.parse(
            model=defaults.MODEL_RECALLER, 
            messages=temp_messages,
            response_format=MemoryRecall,
        )
        completion = response.choices[0].message
        memories_to_recall = list(set(completion.parsed.memory_names)) if not completion.refusal else []
        log.info(f"{memories_to_recall=}")
        recalled_memories = {k: v for k, v in self.memory[ctx.guild.id].items() if k in memories_to_recall}
        recalled_memories_str = "\n".join(f"[Memory of {k}:] {v}" for k, v in recalled_memories.items())
        return recalled_memories_str or "[None]"


    async def execute_responder(self, ctx: commands.Context, messages: list[dir], recalled_memories: str) -> dict:
        """
        Runs an openai completion with the chat history and the contents of memories
        and returns a response message after sending it to the user.
        """
        tools = [t for t in all_function_calls if t.schema.function.name not in await self.config.guild(ctx.guild).disabled_functions()]
        system_prompt = {
            "role": "system",
            "content": (await self.config.guild(ctx.guild).prompt_responder()).format(
                botname=self.bot.user.name,
                servername=ctx.guild.name,
                channelname=ctx.channel.name,
                emotes=(await self.config.guild(ctx.guild).emotes()) or "[None]",
                currentdatetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z"),
                memories=recalled_memories,
            )}
        temp_messages = [msg for msg in messages]
        temp_messages.insert(0, system_prompt)

        response = await self.openai_client.chat.completions.create(
            model=defaults.MODEL_RESPONDER, 
            messages=temp_messages,
            max_tokens=await self.config.guild(ctx.guild).response_tokens(),
            tools=[t.asdict() for t in tools],
        )

        if response.choices[0].message.tool_calls:
            temp_messages.append(response.choices[0].message)
            for call in response.choices[0].message.tool_calls:
                try:
                    cls = next(t for t in tools if t.schema.function.name == call.function.name)
                    args = json.loads(call.function.arguments)
                    tool_result = await cls(ctx).run(args)
                except:
                    tool_result = "Error"
                    log.exception("Calling tool")

                tool_result = tool_result.strip()
                if len(tool_result) > defaults.TOOL_CALL_LENGTH:
                    tool_result = tool_result[:defaults.TOOL_CALL_LENGTH-3] + "..."
                log.info(f"{tool_result=}")

                temp_messages.append({
                    "role": "tool",
                    "content": tool_result,
                    "tool_call_id": call.id,
                })

            response = await self.openai_client.chat.completions.create(
                model=defaults.MODEL_RESPONDER, 
                messages=temp_messages,
                max_tokens=await self.config.guild(ctx.guild).response_tokens(),
            )

        completion = response.choices[0].message.content
        log.info(f"{completion=}")

        reply_content = RESPONSE_CLEANUP_PATTERN.sub("", completion)[:DISCORD_MESSAGE_LENGTH]
        discord_reply = await ctx.reply(reply_content, mention_author=False)
        response_message = {
            "role": "assistant",
            "content": await self.parse_discord_message(discord_reply)
        }
        return response_message


    async def execute_memorizer(self, ctx: commands.Context, messages: list[dict], memories: str, recalled_memories: str) -> None:
        """
        Runs an openai completion with the chat history, a list of memories, and the contents of some memories,
        and executes database operations as decided by the LLM.
        """
        if not await self.config.guild(ctx.guild).allow_memorizer():
            return
        
        system_prompt = {
            "role": "system",
            "content": (await self.config.guild(ctx.guild).prompt_memorizer()).format(memories, recalled_memories)
        }
        temp_messages = get_text_contents(messages)
        num_backread = await self.config.guild(ctx.guild).backread_memorizer()
        if len(temp_messages) > num_backread:
            temp_messages = temp_messages[-num_backread:]
        temp_messages.insert(0, system_prompt)

        response = await self.openai_client.beta.chat.completions.parse(
            model=defaults.MODEL_MEMORIZER, 
            messages=temp_messages,
            response_format=MemoryChangeList,
        )
        completion = response.choices[0].message
        if completion.refusal:
            log.warning(completion.refusal)
            return
        if not completion.parsed or not completion.parsed.memory_changes:
            return
        
        memory_changes = []
        async with self.config.guild(ctx.guild).memory() as memory:
            for change in completion.parsed.memory_changes:
                action, name, content = change.action_type, change.memory_name, change.memory_content

                if name not in memory and action != "create":
                    matches = get_close_matches(name, memory)
                    if not matches:
                        continue
                    name = matches[0]

                if action == "delete":
                    del memory[name]
                    del self.memory[ctx.guild.id][name]
                    log.info(f"memory {name} deleted")
                elif action == "append" and name in memory:
                    memory[name] = memory[name] + " ... " + content
                    self.memory[ctx.guild.id][name] = memory[name]
                    log.info(f"memory {name} = \"{memory[name]}\"")
                elif name in memory and memory[name] == content:
                    continue
                else:
                    memory[name] = content
                    self.memory[ctx.guild.id][name] = content
                    log.info(f"memory {name} = \"{content}\"")

                memory_changes.append(name)

        if memory_changes and await self.config.guild(ctx.guild).memorizer_alerts():
            await ctx.send(f"`Revised memories: {', '.join(memory_changes)}`")


    async def get_message_history(self, ctx: commands.Context) -> list[dict]:
        backread = [message async for message in ctx.channel.history(
            limit=await self.config.guild(ctx.guild).backread_messages(),
            before=ctx.message,
            oldest_first=False
        )]
        backread.insert(0, ctx.message)

        messages = []
        processed_attachments = []
        tokens = 0
        encoding = encoding_for_model(defaults.MODEL_RESPONDER)

        for n, backmsg in enumerate(backread):
            try:
                quote = backmsg.reference.cached_message or await backmsg.channel.fetch_message(backmsg.reference.message_id)
                if len(backread) > n+1 and quote == backread[n+1]:
                    quote = None
            except:
                quote = None

            image_contents = await self.extract_images(backmsg, quote, processed_attachments)
            text_content = await self.parse_discord_message(backmsg, quote=quote)
            if image_contents:
                image_contents.insert(0, {"type": "text", "text": text_content})
                messages.append({
                    "role": "user",
                    "content": image_contents
                })
            else:
                messages.append({
                    "role": "assistant" if backmsg.author.id == self.bot.user.id else "user",
                    "content": text_content
                })

            tokens += len(encoding.encode(text_content)) + 255 * len(image_contents)
            if n > 0 and tokens > await self.config.guild(ctx.guild).response_tokens():
                break

        log.info(f"{len(messages)=} / {tokens=}")
        return list(reversed(messages))


    async def extract_images(self, message: discord.Message, quote: discord.Message, processed_attachments: list[discord.Attachment]) -> list[dict]:
        if message.id in self.image_cache:
            log.info("Retrieving cached image(s)")
            return self.image_cache[message.id]

        image_contents = []

        # Attachments
        if message.attachments or quote and quote.attachments:
            attachments = (message.attachments or []) + (quote.attachments if quote and quote.attachments else [])
            images = [att for att in attachments if att.content_type.startswith('image/')]

            for image in images[:defaults.IMAGES_PER_MESSAGE]:
                if image in processed_attachments:
                    continue
                processed_attachments.append(image)
                try:
                    buffer = BytesIO()
                    await image.save(buffer, seek_begin=True)
                    fp = process_image(buffer)
                    del buffer
                    image_contents.append(make_image_content(fp))
                    del fp
                    log.info(image.filename)
                except:
                    log.warning("Processing image attachment", exc_info=True)

        if image_contents:
            self.image_cache[message.id] = [cnt for cnt in image_contents]
            return image_contents

        # URLs
        image_url = []

        if message.embeds and message.embeds[0].image:
            image_url.append(message.embeds[0].image.url)
        if message.embeds and message.embeds[0].thumbnail:
            image_url.append(message.embeds[0].thumbnail.url)

        matches = URL_PATTERN.findall(message.content)
        for match in matches:
            if match.endswith(IMAGE_EXTENSIONS):
                image_url.append(match)

        if not image_url:
            return image_contents
        
        async with aiohttp.ClientSession() as session:
            for url in image_url[:defaults.IMAGES_PER_MESSAGE]:
                try:
                    fp = None
                    async with session.get(url) as response:
                        response.raise_for_status()
                        fp = BytesIO(await response.read())
                    processed_image = process_image(fp)
                    del fp
                    image_contents.append(make_image_content(processed_image))
                    del processed_image
                    log.info(url)
                except:
                    log.warning("Processing image URL", exc_info=True)

        if image_contents:
            self.image_cache[message.id] = [cnt for cnt in image_contents]

        return image_contents
    

    async def parse_discord_message(self, message: discord.Message, quote: discord.Message = None, recursive=True) -> str:
        content = f"[Username: {sanitize(message.author.name)}]"
        if isinstance(message.author, discord.Member) and message.author.nick:
            content += f" [Alias: {sanitize(message.author.nick)}]"
        starting_len = len(content)
        
        if message.is_system():
            if message.type == discord.MessageType.new_member:
                content += " [Joined the server]"
            else:
                content += f" {message.system_content}"
        elif message.content:
            content += f" [said:] {message.content}"
        
        for attachment in message.attachments:
            content += f" [Attachment: {attachment.filename}]"
        for sticker in message.stickers:
            content += f" [Sticker: {sticker.name}]"
        for embed in message.embeds:
            if embed.title:
                content += f" [Embed Title: {sanitize(embed.title)}]"
            if embed.description:
                content += f" [Embed Content: {sanitize(embed.description)}]"
        
        if quote and recursive:
            quote_content = (await self.parse_discord_message(quote, recursive=False)).replace("\n", " ")
            if len(quote_content) > defaults.QUOTE_LENGTH:
                quote_content = quote_content[:defaults.QUOTE_LENGTH-3] + "..."
            content += f"\n[[[Replying to: {quote_content}]]]"

        if len(content) == starting_len:
            content += " [Message empty or not supported]"

        mentions = message.mentions + message.role_mentions + message.channel_mentions  # noqa
        for mentioned in mentions:
            if mentioned in message.channel_mentions:
                content = content.replace(mentioned.mention, f'#{mentioned.name}')
            elif mentioned in message.role_mentions:
                content = content.replace(mentioned.mention, f'@{mentioned.name}')
            else:
                content = content.replace(mentioned.mention, f'@{mentioned.name}')

        return content.strip()
