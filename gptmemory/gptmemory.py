import discord
import logging
import tiktoken
import re
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import Literal
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.gptmemory")

GPT_MODEL = "gpt-4o"
RESPONSE_TOKENS = 1000
BACKREAD_TOKENS = 1000
BACKREAD_MESSAGES = 20

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
 A memory change may either create, adjust, append, or delete an entry. You can submit an empty list if no new important information is found.
 If you're told to remember something or you think it's important you should save it. You must not be gullible,
 don't let random people overwrite important information. When creating a memory, its name must be a username
 in the case of personal information or a short phrase in the case of a topic. When adjusting a memory,
 you must make a concise summary of previous and new information. You may append to a memory if it already exists
 but you don't see its contents. Only delete a memory if it becomes completely useless.
\nThe available entries are: {0}
\nBelow are the contents of some of the entries:\n\n{1}"
"""

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
        async with ctx.channel.typing():
            pass
        await self.create_response(ctx) 

    async def is_common_valid_reply(self, ctx: commands.Context) -> bool:
        """Run some common checks to see if a message is valid for the bot to reply to"""
        if not ctx.guild:
            return False
        #if any(ctx.guild.id not in prompt for prompt in [self.prompt_manager, self.prompt_responder, self.prompt_memorizer]):
        if ctx.guild.id != 1113893773714399392:
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

    async def initialize_openai_client(self, ctx: commands.Context = None):
        api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
        if not api_key:
            return
        self.openai_client = AsyncOpenAI(api_key=api_key)
        
    async def create_response(self, ctx: commands.Context):
        # MESSAGE HISTORY SETUP
        if ctx.guild.id not in self.memory:
            self.memory[ctx.guild.id] = {}
        backread = [message async for message in ctx.channel.history(limit=BACKREAD_MESSAGES, before=ctx.message, oldest_first=False)]
        if ctx.message.reference:
            try:
                quote = ctx.message.reference.cached_message or await ctx.fetch_message(ctx.message.reference.message_id)
            except:
                quote = None
            if quote and quote not in backread:
                backread.append(quote)
        backread.append(ctx.message)
        messages = []
        tokens = 0
        encoding = tiktoken.encoding_for_model(GPT_MODEL)
        for n, backmsg in enumerate(reversed(backread)):
            msg_content = self.parse_message(backmsg)
            messages.append({
                "role": "assistant" if backmsg.author.id == self.bot.user.id else "user",
                "content": msg_content
            })
            tokens += len(encoding.encode(msg_content))
            if tokens > BACKREAD_TOKENS and n >= 1:
                break
        messages = list(reversed(messages))

        # RECALLER
        memories_str = ", ".join(self.memory[ctx.guild.id].keys())
        recaller_messages = [msg for msg in messages]
        recaller_messages.insert(0, {"role": "system", "content": self.prompt_recaller[ctx.guild.id].format(memories_str)})
        recaller_response = await self.openai_client.beta.chat.completions.parse(
            model=GPT_MODEL, 
            messages=recaller_messages,
            response_format=MemoryRecall,
        )
        recaller_completion = recaller_response.choices[0].message
        memories_to_recall = recaller_completion.parsed.memory_names if not recaller_completion.refusal else []
        log.info(f"{memories_to_recall=}")
        recalled_memories = {k: v for k, v in self.memory[ctx.guild.id].items() if k in memories_to_recall}
        recalled_memories_str = "\n".join(f"[Memory of {k}:] {v}" for k, v in recalled_memories.items())

        # RESPONDER
        responder_messages = [msg for msg in messages]
        responder_messages.insert(0, {
            "role": "system",
            "content": self.prompt_responder[ctx.guild.id].format(
                servername=ctx.guild.name,
                channelname=ctx.channel.name,
                emotes=EMOTES,
                currentdatetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z"),
                memories=recalled_memories_str,
            )
        })
        responder_response = await self.openai_client.chat.completions.create(
            model=GPT_MODEL, 
            messages=responder_messages,
            max_tokens=RESPONSE_TOKENS
        )
        responder_completion = responder_response.choices[0].message.content
        log.info(f"{responder_completion=}")
        responder_completion = re.sub(r"^(\[.+\] ?)+", "", responder_completion)
        responder_reply = await ctx.reply(responder_completion[:4000], mention_author=False)

        # MEMORIZER
        messages.append({"role": "assistant", "content": self.parse_message(responder_reply)})
        memorizer_messages = [msg for msg in messages]
        memorizer_messages.insert(0, {"role": "system", "content": self.prompt_memorizer[ctx.guild.id].format(memories_str, recalled_memories_str)})
        memorizer_response = await self.openai_client.beta.chat.completions.parse(
            model=GPT_MODEL, 
            messages=memorizer_messages,
            response_format=MemoryChangeList,
        )
        memorizer_completion = memorizer_response.choices[0].message
        if memorizer_completion.refusal:
            return
        async with self.config.guild(ctx.guild).memory() as memory:
            for change in memorizer_completion.parsed.memory_changes:
                action, name, content = change.action_type, change.memory_name, change.memory_content
                if action == "delete":
                    del memory[name]
                    del self.memory[ctx.guild.id][name]
                    log.info(f"memory {name} deleted")
                elif action == "append" and name in memory:
                    memory[name] = memory[name] + " ... " + content
                    self.memory[ctx.guild.id][name] = memory[name]
                    log.info(f"memory {name} = {memory[name]}")
                else:
                    memory[name] = content
                    self.memory[ctx.guild.id][name] = content
                    log.info(f"memory {name} = {content}")
        
    def parse_message(self, message: discord.Message) -> str:
        content = f"[Username: {backmsg.author.name}]"
        if backmsg.author.nick:
            content += f" [Alias: {backmsg.author.nick}]"
        content += f" [said:] {message.content}"
        for attachment in message.attachments:
            content += f"\n[Attachment: {attachment.filename}]"
        for sticker in message.stickers:
            content += f"\n[Sticker: {sticker.name}]"
        
        mentions = message.mentions + message.role_mentions + message.channel_mentions
        if not mentions:
            return content.strip()
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
        if ctx.guild.id in self.memory and name in self.memory[ctx.guild.id]:
            await ctx.send(f"`[Memory of {name}]`\n>>> {self.memory[ctx.guild.id][name]}")
        else:
            await ctx.send(f"No memory of {name}")
    
    @commands.command()
    async def memories(self, ctx: commands.Context):
        """View a list of memories, for GPT"""
        if ctx.guild.id in self.memory and self.memory[ctx.guild.id]:
            await ctx.send(f"```{', '.join(self.memory[ctx.guild.id])}```")
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
        if ctx.guild.id not in self.memory:
            return
        async with self.config.guild(ctx.guild).memory() as memory:
            memory[name] = content
        self.memory[ctx.guild.id][name] = content
        await ctx.send("✅")

