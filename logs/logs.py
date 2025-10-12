import os
import discord
import aiofiles
import aiofiles.os
from typing import Optional
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.views import SimpleMenu
from redbot.core.data_manager import core_data_path

LATEST_LOGS = os.path.join(core_data_path(), "logs/latest.log")
MAX_PAGE_LENGTH = 1970


async def get_logs_file():
    if await aiofiles.os.path.exists(LATEST_LOGS):
        return LATEST_LOGS
    path = os.path.join(core_data_path(), "logs")
    files = await aiofiles.os.listdir(path)
    if not files:
        return None
    files.sort()
    return os.path.join(path, files[-1])


class Logs(commands.Cog):
    """Owner cog to show the latest logs."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=66677363)
        self.config.register_global(private=True)


    @commands.group(invoke_without_command=True) # type: ignore
    @commands.is_owner()
    async def logs(self, ctx: commands.Context, lines: Optional[int]):
        """Sends the last n lines of the latest log file (default 100)."""
        try:
            private = await self.config.private()
            channel = ctx.channel if not private else (ctx.author.dm_channel or await ctx.author.create_dm())
            if not lines or lines < 0:
                lines = 100

            pages = []
            if logs_file := await get_logs_file():
                async with aiofiles.open(logs_file, 'r', encoding="utf8") as f:
                    f_lines = await f.readlines()
                    result = [line.strip() for line in f_lines[-lines:]]
                while result:
                    page = ""
                    while result:
                        if len(page) + 1 + len(result[-1]) <= MAX_PAGE_LENGTH:
                            page = result.pop() + "\n" + page
                        elif not page:  # cuts up a huge line
                            page, result[-1] = "..." + result[-1][-MAX_PAGE_LENGTH:], result[-1][:-MAX_PAGE_LENGTH] + "...",
                        else:
                            break
                    pages.append(f"```py\n{page.strip()}```")

            if not pages:
                await channel.send("*Empty*")
            elif len(pages) == 1:
                await channel.send(content=pages[0])
            else:
                pages.reverse()
                for i in range(len(pages)):
                    pages[i] += f"`Page {i+1}/{len(pages)}`"
                ctx.message.channel = channel
                ctx.message.guild = channel.guild
                new_ctx: commands.Context = await self.bot.get_context(ctx.message)
                await SimpleMenu(pages, timeout=3600, page_start=len(pages)-1).start(new_ctx)

        except Exception as ex:  # Since logs is an important command, all possible errors should be covered
            await ctx.send(f"{type(ex).__name__}: {ex}")


    @logs.command(name="file")
    async def logs_file(self, ctx: commands.Context):
        """Sends the entire latest log file."""
        private = await self.config.private()
        channel = ctx.channel if not private else (ctx.author.dm_channel or await ctx.author.create_dm())
        path = await get_logs_file()
        if not path:
            return await channel.send("No logs found.")
        file = discord.File(path)
        await channel.send(file=file)

    @logs.command(name="private")
    async def logs_private(self, ctx: commands.Context):
        """Whether logs should be sent to your DMs."""
        new_value = not await self.config.private()
        await self.config.private.set(new_value)
        await ctx.send("Logs will now be sent " + ("in your DMs" if new_value else "in the same channel"))
