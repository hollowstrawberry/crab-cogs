import re

EMBED_COLOR = 0xD7598B
EMBED_ICON = "https://i.imgur.com/FeRu6Pw.png"
IMAGE_TYPES = (".png", ".jpeg", ".jpg", ".webp", ".gif")
TAG_BLACKLIST = ["loli", "shota", "guro", "video"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Referer": "https://gelbooru.com/",
}
RATING_GENERAL = "rating:general"
RATING_SENSITIVE = "rating:sensitive"
RATING_QUESTIONABLE = "rating:questionable"
RATING_EXPLICIT = "rating:explicit"

URL_PATTERN = re.compile(r"(https?://\S+)")
RATING_PATTERN = re.compile(r"\s?rating:\S+", re.IGNORECASE)

VIEW_TIMEOUT = 600
MAX_OPTIONS = 25
MAX_OPTION_SIZE = 100