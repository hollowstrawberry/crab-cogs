import re
import logging

log = logging.getLogger("red.crab-cogs.imagescanner")

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
VIEW_TIMEOUT = 5*60

# language=RegExp
LOOKAHEAD_PATTERN = rf'(?=(?:[^"]*"[^"]*")*[^"]*$)'  # ensures the characters surrounding the lookahead are not inside quotes
PARAM_REGEX = re.compile(rf" ?([^:]+): (.+?),{LOOKAHEAD_PATTERN}")
PARAM_GROUP_REGEX = re.compile(rf", [^:]+: {{.+?{LOOKAHEAD_PATTERN}}}")
HASHES_GROUP_REGEX = re.compile(rf", Hashes: ({{.+?{LOOKAHEAD_PATTERN}}})")

PARAMS_BLACKLIST = [
    "Template", "hashes",
    "ADetailer confidence", "ADetailer mask", "ADetailer dilate", "ADetailer denoising",
    "ADetailer inpaint", "ADetailer version", "ADetailer prompt", "ADetailer use", "ADetailer checkpoint",
    "RP Divide", "RP Ma", "RP Prompt", "RP Calc", "RP Ratio", "RP Base", "RP Use", "RP LoRA", "RP Options", "RP Flip", "RP threshold",
    "FreeU Stages", "FreeU Schedule",
    "Mimic", "Separate Feature Channels", "Scaling Startpoint", "Variability Measure",  # Dynamic thresholding
    "Interpolate Phi", "Threshold percentile", "CFG mode", "CFG scale min",
]
NAIV3_PARAMS = {
    "steps": "Steps",                       "width": "Width",                   "height": "Height",
    "seed": "Seed",                         "scale": "Guidance",                "cfg_rescale": "Guidance Rescale",
    "sampler": "Sampler",                   "sm": "SMEA",                       "sm_dyn": "DYN",
    "uncond_scale": "Undesired Strength",   "noise_schedule": "Noise Schedule", "request_type": "Operation",
}

HEADERS = {
    "User-Agent": f"crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}
