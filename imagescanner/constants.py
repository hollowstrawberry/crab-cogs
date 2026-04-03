import re
import logging

log = logging.getLogger("red.crab-cogs.imagescanner")

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
VIEW_TIMEOUT = 10*60

RESOURCE_HASH_REGEX = re.compile(r"\b(?:0x)?[0-9a-f]{10,64}\b", re.IGNORECASE)
RESOURCE_FILE_REGEX = re.compile(r"\"[^\"]+\.(?:safetensors|ckpt|pth|pt|bin)\"", re.IGNORECASE)


HEADERS = {
    "User-Agent": "crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}
