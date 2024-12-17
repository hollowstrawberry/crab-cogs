# https://github.com/Aedial/novelai-api/blob/main/example/boilerplate.py

import json
from logging import Logger, StreamHandler
from typing import Optional
from aiohttp import ClientSession
from novelai_api import NovelAIAPI
from novelai_api.utils import get_encryption_key


class NaiAPI:
    """Boilerplate for the NovelAIAPI"""

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._session: Optional[ClientSession] = None
        self.logger = Logger("NovelAI")
        self.logger.addHandler(StreamHandler())
        self.api = NovelAIAPI(logger=self.logger)

    @property
    def encryption_key(self):
        return get_encryption_key(self._username, self._password)

    async def __aenter__(self):
        self._session = ClientSession()
        await self._session.__aenter__()

        self.api.attach_session(self._session)
        await self.api.high_level.login(self._username, self._password)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._session.__aexit__(exc_type, exc_val, exc_tb)
