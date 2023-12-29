import re
from redbot.core.app_commands import Choice
from collections import OrderedDict

VIEW_TIMEOUT = 5 * 60

DEFAULT_PROMPT = "best quality, amazing quality, very aesthetic, absurdres"

DEFAULT_NEGATIVE_PROMPT = "{bad}, fewer, extra, missing, worst quality, bad quality, " \
                          "watermark, signature, username, logo, jpeg artifacts, unfinished, displeasing, " \
                          "chromatic aberration, artistic error, scan, [abstract], {simple background}"

NSFW_TERMS = re.compile(r"\b(nsfw|explicit|questionable|sensitive|nude|naked|sex|cum|pussy|cleft|clit(oris|oral)?"
                        r"|penis|nipples?|topless|bottomless|no panties|no bra|anus|anal|oral|vaginal?|paizuri"
                        r"|missionary|cowgirl|hetero|fellatio|cunnilingus|futa(nari)?)\b")

TOS_TERMS = re.compile(r"\b(lolis?|shotas?|child(ren|s)?)\b")

SAMPLER_TITLES = OrderedDict({
    "k_euler": "Euler",
    "k_euler_ancestral": "Euler Ancestral",
    "k_dpmpp_2s_ancestral": "DPM++ 2S Ancestral",
    "k_dpmpp_2m": "DPM++ 2M",
    "k_dpmpp_sde": "DPM++ SDE",
    "ddim": "DDIM",
})

RESOLUTION_TITLES = OrderedDict({
    "832,1216": "Portrait (832x1216)",
    "1216,832": "Landscape (1216x832)",
    "1024,1024": "Square (1024x1024)",
    "960,1088": "Portrait (960x1088)",
    "896,1152": "Portrait (896x1152)",
    "768,1280": "Portrait (768x1280)",
    "704,1344": "Portrait (704x1344)",
    "640,1408": "Portrait (640x1408)",
    "576,1472": "Portrait (576x1472)",
    "512,1536": "Portrait (512x1536)",
    "1088,960": "Landscape (1088x960)",
    "1152,896": "Landscape (1152x896)",
    "1280,768": "Landscape (1280x768)",
    "1344,704": "Landscape (1344x704)",
    "1408,640": "Landscape (1408x640)",
    "1472,576": "Landscape (1472x576)",
    "1536,512": "Landscape (1536x512)",
})

NOISE_SCHEDULES = [
    "native", "karras", "exponential", "polyexponential",
]

SAMPLER_VERSIONS = [
    "Regular", "SMEA", "SMEA+DYN",
]

PARAMETER_DESCRIPTIONS = {
    "resolution": "The aspect ratio of your image.",
    "guidance": "The intensity of the prompt.",
    "guidance_rescale": "Adjusts the guidance somehow.",
    "sampler": "The algotithm that guides image generation.",
    "sampler_version": "SMEA samplers are modified to perform better at higher resolutions.",
    "decrisper": "Reduces artifacts caused by high guidance.",
}

PARAMETER_CHOICES = {
    "resolution": [Choice(name=title, value=value) for value, title in RESOLUTION_TITLES.items()],
    "sampler": [Choice(name=title, value=value) for value, title in SAMPLER_TITLES.items()],
    "sampler_version": [Choice(name=ver, value=ver) for ver in SAMPLER_VERSIONS],
    "noise_schedule": [Choice(name=sch, value=sch) for sch in NOISE_SCHEDULES],
}
