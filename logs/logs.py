import discord
import aiofiles
from datetime import datetime, timezone
from redbot.core import commands, Config
from redbot.core.bot import Red

from logs.logs_view import LogsView
from logs.utils import get_logs_file, MAX_PAGE_LENGTH, BACKTICK_PATTERN, LOG_LINES


class Logs(commands.Cog):
    """Owner cog to show the latest logs."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=66677363)
        self.config.register_global()

    @commands.is_owner()
    @commands.command(name="logs")
    async def logs(self, ctx: commands.Context):
        """Lets the bot owner view the bot's latest logs."""
        try:
            pages: list[str] = []
            logs_file = await get_logs_file()
            if logs_file:
                async with aiofiles.open(logs_file, 'r', encoding="utf8") as f:
                    f_lines = await f.readlines()
                    result = [line.strip() for line in f_lines[-LOG_LINES:]]
                while result:
                    page = ""
                    while result:
                        if len(page) + 1 + len(result[-1]) <= MAX_PAGE_LENGTH:
                            page = result.pop() + "\n" + page
                        elif not page:  # cuts up a huge line
                            page, result[-1] = "..." + result[-1][-MAX_PAGE_LENGTH:], result[-1][:-MAX_PAGE_LENGTH] + "...",
                        else:
                            break
                    pages.append(f"```py\n{BACKTICK_PATTERN.sub('`', page).strip()}\n```")
            
            if not pages:
                return await ctx.send("*No logs*")
            
            pages.reverse()
            timestamp = int(datetime.now(timezone.utc).timestamp())

            for i in range(len(pages)):
                if len(pages) > 1:
                    pages[i] += f"`Page {i+1}/{len(pages)}` "
                pages[i] += f"<t:{timestamp}:R>"

            view = LogsView(logs_file or "", pages, self.bot)
            view.message = await ctx.send(view=view)
            if ctx.bot_permissions.manage_messages:
                try:
                    await ctx.message.delete()
                except discord.DiscordException:
                    pass

        except Exception as ex:  # Since logs is an important command, all possible errors should be covered
            await ctx.send(f"{type(ex).__name__}: {ex}")
