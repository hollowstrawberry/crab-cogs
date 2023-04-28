from .imagelog import ImageLog
from redbot.core.utils import get_end_user_data_statement

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

async def setup(bot):
    cog = ImageLog(bot)
    await cog.load_config()
    await bot.add_cog(cog)
