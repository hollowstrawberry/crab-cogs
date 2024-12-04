from redbot.core import commands, Config
from redbot.core.bot import Red


class GptMemoryCogBase(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=19475820)
        self.config.register_guild(**{
            "prompt_recaller": "",
            "prompt_responder": "",
            "prompt_memorizer": "",
            "memory": {},
        })
        self.prompt_recaller: dict[int, str] = {}
        self.prompt_responder: dict[int, str] = {}
        self.prompt_memorizer: dict[int, str] = {}
        self.memory: dict[int, dict[str, str]] = {}
