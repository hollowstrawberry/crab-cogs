import re

DISCORD_MESSAGE_LENGTH = 4000
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

RESPONSE_CLEANUP_PATTERN = re.compile(r"(^(\[[^[\]]+\] ?)+|\[\[\[.+\]\]\])")
URL_PATTERN = re.compile(r"(https?://\S+)")
