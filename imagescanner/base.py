import aiohttp
from typing import Any
from expiringdict import ExpiringDict
from redbot.core import commands
from redbot.core.bot import Red, Config

from imagescanner.metadata import Metadata
from imagescanner.constants import HEADERS

ImageCacheData = dict[int, bytes]
ImageCacheMetadata = dict[int, Metadata]
ImageCache = dict[int, tuple[ImageCacheMetadata, ImageCacheData]]


class ImageScannerBase(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7072707469)
        self.scan_channels = set()
        self.scan_limit = 10 * 1024**2
        self.attach_images = True
        self.use_civitai = True
        self.civitai_emoji = ""
        self.use_arcenciel = True
        self.arcenciel_emoji = ""
        self.model_cache_civitai: dict[str, tuple[Any, Any]] = {}
        self.model_cache_arcenciel: dict[str, str] = {}
        self.model_not_found_cache_civitai: dict[str, bool] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.model_not_found_cache_arcenciel: dict[str, bool] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.image_cache: ImageCache | None = None
        self.image_cache_size = 100
        self.always_scan_generated_images = False
        self.session = aiohttp.ClientSession(headers=HEADERS)
        defaults = {
            "channels": [],
            "scanlimit": self.scan_limit,
            "attach_images": self.attach_images,
            "use_civitai": self.use_civitai,
            "civitai_emoji": self.civitai_emoji,
            "use_arcenciel": self.use_arcenciel,
            "arcenciel_emoji": self.arcenciel_emoji,
            "model_cache_v2": {},
            "model_cache_arcenciel": {},
            "image_cache_size": self.image_cache_size,
            "always_scan_generated_images": self.always_scan_generated_images
        }
        self.config.register_global(**defaults)
