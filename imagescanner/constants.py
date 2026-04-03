import re
import logging

log = logging.getLogger("red.crab-cogs.imagescanner")

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
VIEW_TIMEOUT = 10*60

RESOURCE_HASH_REGEX = re.compile(r"\b(?:0x)?[0-9a-f]{10,64}\b", re.IGNORECASE)
RESOURCE_FILE_REGEX = re.compile(r"\"[^\"]+\.(?:safetensors|ckpt|pth|pt|bin)\"", re.IGNORECASE)

METADATA_REGEX = re.compile(r"(?:(?P<Prompt>[\S\s]+?)\n)?(?:Negative prompt: ?(?P<NegativePrompt>[\S\s]*)\n)?(?P<Params>[^\n:]+: .+)", re.IGNORECASE)
LOOKAHEAD_PATTERN = r'(?=(?:[^"]*"[^"]*")*[^"]*$)'  # ensures the characters surrounding the lookahead are not inside quotes
PARAM_REGEX = re.compile(rf" ?([^:]+): (.+?),{LOOKAHEAD_PATTERN}")
PARAM_GROUP_REGEX = re.compile(rf", [^:]+: {{.+?{LOOKAHEAD_PATTERN}}}")

HEADERS = {
    "User-Agent": "crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}
