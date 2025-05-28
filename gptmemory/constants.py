import re

DISCORD_MESSAGE_LENGTH = 4000
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

RESPONSE_CLEANUP_PATTERN = re.compile(r"(^(\[[^[\]]+\]\s?)+|\[\[\[.+\]\]\])")
URL_PATTERN = re.compile(r"(https?://\S+)")
FARENHEIT_PATTERN = re.compile(r"(-?\d+)\s?°[fF]")

VISION_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
]
