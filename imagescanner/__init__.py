from .imagescanner import ImageScanner
from redbot.core.utils import get_end_user_data_statement

import logging
logging.getLogger("SD_Prompt_Reader.ImageDataReader").setLevel(logging.ERROR)

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

async def setup(bot):
    await bot.add_cog(ImageScanner(bot))
