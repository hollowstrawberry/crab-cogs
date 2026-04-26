import os
import re
import aiofiles
import aiofiles.os
from redbot.core.data_manager import core_data_path

LATEST_LOGS = os.path.join(core_data_path(), "logs/latest.log")
MAX_PAGE_LENGTH = 1970
LOG_LINES = 200
VIEW_TIMEOUT = 60*60
BACKTICK_PATTERN = re.compile(r"```+")

async def get_logs_file():
    if await aiofiles.os.path.exists(LATEST_LOGS):
        return LATEST_LOGS
    path = os.path.join(core_data_path(), "logs")
    files = await aiofiles.os.listdir(path)
    if not files:
        return None
    files.sort()
    return os.path.join(path, files[-1])
