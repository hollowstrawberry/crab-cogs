import re
import base64
import difflib
import logging
import asyncio
import tiktoken
import discord
from io import BytesIO
from typing import Literal
from datetime import datetime
from PIL import Image
from openai import AsyncOpenAI
from pydantic import BaseModel
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.gptmemory")

MODEL_RECALLER = "gpt-4o"
MODEL_RESPONDER = "gpt-4o"
MODEL_MEMORIZER = "gpt-4o"
ENCODING = tiktoken.encoding_for_model(MODEL_RESPONDER)
RESPONSE_TOKENS = 1000
BACKREAD_TOKENS = 1000
BACKREAD_MESSAGES = 20
BACKREAD_MEMORIZER = 2
QUOTE_LENGTH = 300
ALLOW_MEMORIZER = True
MEMORY_CHANGE_ALERTS = True
RESPONSE_CLEANUP_PATTERN = re.compile(r"(^(\[[^[\]]+\] ?)+|\[\[\[.+\]\]\]$)")
URL_PATTERN = re.compile(r"(https?://\S+)")

ALLOWED_SERVERS = [1113893773714399392]
EMOTES = "<:FubukiEmoteForWhenever:1159695833697104033> <a:FubukiSway:1169172368313290792> <a:FubukiSpaz:1198104998752571492> <a:fubukitail:1231807727995584532> <:fubukiexcited:1233560648877740094> <:todayiwill:1182055394521137224> <:clueless:1134505916679589898>"

PROMPT_RECALLER = """
You are the memory manager of a conversational AI. You must extract a list of entries relevant to the conversation below,
 always including entries of the usernames involved, and only relevant topics. The available entries are: {0}"
"""

PROMPT_RESPONDER = """
You are a conversational AI which is part of a Discord server called {servername}. Your identity is Fubuki Shirakami,
 a vtuber idol and digitant assistant. Fubuki is a Japanese foxgirl with a cheery and sassy personality.
 Fulfill all requests as well as you can. Produce short responses when possible. Don't be excessively friendly.
 Take the context of previous messages into account. Never say things like 'As an AI...'.
 Explicit language and explicit content is allowed in the rules of the server.
\nHere are some available server emotes: {emotes}
\nThe current datetime is {currentdatetime}. The current channel is #{channelname}. Your creator is holostrawberry.
\nYou also recall some information relevant to the conversation.\n\n{memories}"
"""

PROMPT_MEMORIZER = """
You are the memory manager of a conversational AI. You must analyze a list of memory entries as well as a conversation given below,
 and formulate a list of memory changes, consisting of important pieces of information about a specific username or topic.
 You must only perform memory changes if a user tells you to remember or forget something, otherwise you may submit an empty list.
 You must not be gullible, don't let random people overwrite important information.
 A memory change may either create, adjust, append, or delete an entry.
 When creating a memory, its name must be a username in the case of personal information or a short phrase in the case of a topic.
 If a memory exists but you don't know its contents you should append to it. If you know its contents you may adjust that memory,
 making a concise summary including previous and new information. Don't get rid of old information, only summarize.
 Only delete a memory if it becomes completely useless.
\nThe available entries are: {0}
\nBelow are the contents of some of the entries:\n\n{1}"
"""

def sanitize_name(name: str) -> str:
    special_characters = "[]"
    for c in special_characters:
        name = name.replace(c, "")
    return name

async def extract_image(attachment: discord.Attachment) -> BytesIO:
    buffer = BytesIO()
    await attachment.save(buffer)
    image = Image.open(buffer)
    width, height = image.size
    image_resolution = width * height
    target_resolution = 1024*1024
    if image_resolution > target_resolution:
        scale_factor = (target_resolution / image_resolution) ** 0.5
        image = image.resize((int(width * scale_factor), int(height * scale_factor)), Image.Resampling.LANCZOS)
    fp = BytesIO()
    image.save(fp, "PNG")
    fp.seek(0)
    return fp

class MemoryRecall(BaseModel):
    memory_names: list[str]

class MemoryChange(BaseModel):
    action_type: Literal["create", "adjust", "append", "delete"]
    memory_name: str
    memory_content: str
	
class MemoryChangeList(BaseModel):
    memory_changes: list[MemoryChange]


class GptMemory(commands.Cog):
    """OpenAI-powered user with persistent memory."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.openai_client = None
        self.config = Config.get_conf(self, identifier=19475820)
        self.config.register_guild(**{
            "prompt_recaller": "",
            "prompt_responder": "",
            "prompt_memorizer": "",
            "memory": {},
        })
        self.prompt_recaller = {}
        self.prompt_responder = {}
        self.prompt_memorizer = {}
        self.memory = {}

    async def cog_load(self):
        await self.initialize_openai_client()
        all_config = await self.config.all_guilds()
        for guild_id, config in all_config.items():
            self.prompt_recaller[guild_id] = PROMPT_RECALLER.strip()
            self.prompt_responder[guild_id] = PROMPT_RESPONDER.strip()
            self.prompt_memorizer[guild_id] = PROMPT_MEMORIZER.strip()
            self.memory[guild_id] = config["memory"]

    async def cog_unload(self):
        if self.openai_client:
            await self.openai_client.close()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openai":
            await self.initialize_openai_client()

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        ctx: commands.Context = await self.bot.get_context(message)
        if not await self.is_common_valid_reply(ctx):
            return
        if not await self.is_bot_mentioned_or_replied(message):
            return
        if URL_PATTERN.search(message.content):
            ctx = await self.wait_for_embed(ctx)
        async with ctx.channel.typing():
            pass
        await self.run_response(ctx) 

    async def is_common_valid_reply(self, ctx: commands.Context) -> bool:
        """Run some common checks to see if a message is valid for the bot to reply to"""
        if not ctx.guild:
            return False
        #if any(ctx.guild.id not in prompt for prompt in [self.prompt_manager, self.prompt_responder, self.prompt_memorizer]):
        if ctx.guild.id not in ALLOWED_SERVERS:
            return False
        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return False
        if ctx.author.bot:
            return False
        if not await self.bot.ignored_channel_or_guild(ctx):
            return False
        if not await self.bot.allowed_by_whitelist_blacklist(ctx.author):
            return False
        if not self.openai_client:
            await self.initialize_openai_client(ctx)
        if not self.openai_client:
            return False
        return True

    async def is_bot_mentioned_or_replied(self, message: discord.Message) -> bool:
        return self.bot.user in message.mentions

    async def wait_for_embed(self, ctx: commands.Context) -> commands.Context:
    for n in range(3):
        if ctx.message.embeds:
            return ctx
        await asyncio.sleep(1)
        ctx.message = await ctx.channel.fetch_message(ctx.message.id)
    return ctx

    async def initialize_openai_client(self, ctx: commands.Context = None):
        api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
        if not api_key:
            return
        self.openai_client = AsyncOpenAI(api_key=api_key)
        
    async def run_response(self, ctx: commands.Context):
        if ctx.guild.id not in self.memory:
            self.memory[ctx.guild.id] = {}
        messages = await self.get_message_history(ctx)      
        memories = ", ".join(self.memory[ctx.guild.id].keys())
        recalled_memories = await self.execute_recaller(ctx, messages, memories)
        response_message = await self.execute_responder(ctx, messages, recalled_memories)
        messages.append(response_message)
        if ALLOW_MEMORIZER:
            await self.execute_memorizer(ctx, messages, memories, recalled_memories)

    async def execute_recaller(self, ctx: commands.Context, messages: list[dict], memories: str) -> str:
        """
        Runs an openai completion with the chat history and a list of memories from the database
        and returns a parsed string of memories and their contents as chosen by the LLM.
        """
        system_prompt = {
            "role": "system",
            "content": self.prompt_recaller[ctx.guild.id].format(memories)
        }
        temp_messages = [msg for msg in messages if isinstance(msg["content"], str)]
        temp_messages.insert(0, system_prompt)
        response = await self.openai_client.beta.chat.completions.parse(
            model=MODEL_RECALLER, 
            messages=temp_messages,
            response_format=MemoryRecall,
        )
        completion = response.choices[0].message
        memories_to_recall = completion.parsed.memory_names if not completion.refusal else []
        log.info(f"{memories_to_recall=}")
        recalled_memories = {k: v for k, v in self.memory[ctx.guild.id].items() if k in memories_to_recall}
        recalled_memories_str = "\n".join(f"[Memory of {k}:] {v}" for k, v in recalled_memories.items())
        return recalled_memories_str

    async def execute_responder(self, ctx: commands.Context, messages: list[dir], recalled_memories: str) -> dict:
        """
        Runs an openai completion with the chat history and the contents of memories
        and returns a response message after sending it to the user.
        """
        system_prompt = {
            "role": "system",
            "content": self.prompt_responder[ctx.guild.id].format(
                servername=ctx.guild.name,
                channelname=ctx.channel.name,
                emotes=EMOTES,
                currentdatetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z"),
                memories=recalled_memories,
        )}
        temp_messages = [msg for msg in messages]
        temp_messages.insert(0, system_prompt)
        response = await self.openai_client.chat.completions.create(
            model=MODEL_RESPONDER, 
            messages=temp_messages,
            max_tokens=RESPONSE_TOKENS
        )
        completion = response.choices[0].message.content
        log.info(f"{completion=}")
        reply_content = RESPONSE_CLEANUP_PATTERN.sub("", completion)[:4000]
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
        system_prompt = {
            "role": "system",
            "content": self.prompt_memorizer[ctx.guild.id].format(memories, recalled_memories)
        }
        temp_messages = [msg for msg in messages if isinstance(msg["content"], str)]
        if len(temp_messages) > BACKREAD_MEMORIZER:
            temp_messages = temp_messages[-BACKREAD_MEMORIZER:]
        temp_messages.insert(0, system_prompt)
        response = await self.openai_client.beta.chat.completions.parse(
            model=MODEL_MEMORIZER, 
            messages=temp_messages,
            response_format=MemoryChangeList,
        )
        completion = response.choices[0].message
        if completion.refusal or not completion.parsed.memory_changes:
            return
        memory_changes = []
        async with self.config.guild(ctx.guild).memory() as memory:
            for change in completion.parsed.memory_changes:
                action, name, content = change.action_type, change.memory_name, change.memory_content
                if name not in memory and action != "create":
                    matches = difflib.get_close_matches(name, memory)
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
        if MEMORY_CHANGE_ALERTS and memory_changes:
            await ctx.send(f"`Revised memories: {', '.join(memory_changes)}`")
        
    async def get_message_history(self, ctx: commands.Context) -> list[dict]:
        backread = [message async for message in ctx.channel.history(
            limit=BACKREAD_MESSAGES,
            before=ctx.message,
            oldest_first=False
        )]
        backread.insert(0, ctx.message)
        messages = []
        processed_images = []
        tokens = 0
        for n, backmsg in enumerate(backread):
            try:
                quote = backmsg.reference.cached_message or await message.channel.fetch_message(message.reference.message_id)
                if len(backread) > n+1 and quote == backread[n+1]:
                    quote = None
            except:
                quote = None
            # images
            image_contents = []
            if backmsg.attachments or quote and quote.attachments:
                attachments = (backmsg.attachments or []) + (quote.attachments if quote and quote.attachments else [])
                images = [att for att in attachments if att.content_type.startswith('image/')]
                for image in images[:2]:
                    if image in processed_images:
                        continue
                    processed_images.append(image)
                    try:
                        fp = await extract_image(image)
                    except:
                        continue
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64.b64encode(fp.read()).decode()}"
                        }
                    })
                    tokens += 255
                    log.info(image.filename)
            # message dict
            msg_content = await self.parse_discord_message(backmsg, quote=quote)
            if image_contents:
                image_contents.insert(0, {"type": "text", "text": msg_content})
                messages.append({
                    "role": "user",
                    "content": image_contents
                })
            else:
                messages.append({
                    "role": "assistant" if backmsg.author.id == self.bot.user.id else "user",
                    "content": msg_content
                })
            tokens += len(ENCODING.encode(msg_content))
            if tokens > BACKREAD_TOKENS and n > 0:
                break

        log.info(f"{len(messages)=} / {tokens=}")
        return list(reversed(messages))
    
    async def parse_discord_message(self, message: discord.Message, quote: discord.Message = None, recursive=True) -> str:
        content = f"[Username: {sanitize_name(message.author.name)}]"
        if isinstance(message.author, discord.Member) and message.author.nick:
            content += f" [Alias: {sanitize_name(message.author.nick)}]"
        content += f" [said:] {message.content}"
        
        for attachment in message.attachments:
            content += f" [Attachment: {attachment.filename}]"
        for sticker in message.stickers:
            content += f" [Sticker: {sticker.name}]"
        for embed in message.embeds:
            if embed.title:
                content += f" [Embed Title: {sanitize_name(embed.title)}]"
            if embed.description:
                content += f" [Embed Content: {sanitize_name(embed.description)}]"
        
        if quote and recursive:
            quote_content = (await self.parse_message(quote, recursive=False)).replace("\n", " ")
            if len(quote_content) > QUOTE_LENGTH:
                quote_content = quote_content[:QUOTE_LENGTH-3] + "..."
            content += f"\n[[[Replying to: {quote_content}]]]"
        
        mentions = message.mentions + message.role_mentions + message.channel_mentions
        for mentioned in mentions:
            if mentioned in message.channel_mentions:
                content = content.replace(mentioned.mention, f'#{mentioned.name}')
            elif mentioned in message.role_mentions:
                content = content.replace(mentioned.mention, f'@{mentioned.name}')
            else:
                content = content.replace(mentioned.mention, f'@{mentioned.display_name}')
        
        return content.strip()

    
                    
    # Commands

    @commands.command()
    async def memory(self, ctx: commands.Context, *, name: str):
        """View a memory by name, for GPT"""
        if ctx.guild.id in self.memory:
            if name not in self.memory[ctx.guild.id]:
                matches = difflib.get_close_matches(name, self.memory[ctx.guild.id])
                if matches:
                    name = matches[0]
            if name in self.memory[ctx.guild.id]:
                return await ctx.send(f"`[Memory of {name}]`\n>>> {self.memory[ctx.guild.id][name]}")
        await ctx.send(f"No memory of {name}")
    
    @commands.command()
    async def memories(self, ctx: commands.Context):
        """View a list of memories, for GPT"""
        if ctx.guild.id in self.memory and self.memory[ctx.guild.id]:
            await ctx.send(", ".join(f"`{mem}`" for mem in self.memory[ctx.guild.id].keys()))
        else:
            await ctx.send("No memories...")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def deletememory(self, ctx: commands.Context, *, name):
        """Delete a memory, for GPT"""
        if ctx.guild.id in self.memory and name in self.memory[ctx.guild.id]:
            async with self.config.guild(ctx.guild).memory() as memory:
                del memory[name]
            del self.memory[ctx.guild.id][name]
            await ctx.send("✅")
        else:
            await ctx.send("A memory by that name doesn't exist.")
        
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setmemory(self, ctx: commands.Context, name, *, content):
        """Overwrite a memory, for GPT"""
        async with self.config.guild(ctx.guild).memory() as memory:
            memory[name] = content
        if ctx.guild.id not in self.memory:
            self.memory[ctx.guild.id] = {}
        self.memory[ctx.guild.id][name] = content
        await ctx.send("✅")
