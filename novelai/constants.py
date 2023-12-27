from redbot.core.app_commands import Choice
from collections import OrderedDict
from novelai_api.ImagePreset import ImageResolution

VIEW_TIMEOUT = 5 * 60

DEFAULT_PROMPT = "best quality, amazing quality, very aesthetic, absurdres"

DEFAULT_NEGATIVE_PROMPT = "{bad}, fewer, extra, missing, worst quality, bad quality, " \
                          "watermark, jpeg artifacts, unfinished, displeasing, chromatic aberration, " \
                          "signature, extra digits, artistic error, username, scan, [abstract]"

KEY_NOT_SET_MESSAGE = "NovelAI username and password not set. The bot owner needs to set them like this:\n" \
                      "[p]set api novelai username,USERNAME\n" \
                      "[p]set api novelai password,PASSWORD"

NSFW_TERMS = "nsfw, explicit, nude, sex, cum, pussy, cleft, clit, penis, nipple, topless, anus, " \
             "paizuri, missionary, cowgirl, hetero, vaginal, anal, oral, fellatio, cunnilingus, futa"

SAMPLER_TITLES = OrderedDict({
    "k_euler": "Euler",
    "k_euler_ancestral": "Euler Ancestral",
    "k_dpmpp_2s_ancestral": "DPM++ 2S Ancestral",
    "k_dpmpp_2m": "DPM++ 2M",
    "k_dpmpp_sde": "DPM++ SDE",
    "ddim": "DDIM",
})

RESOLUTION_TITLES = OrderedDict({
    "portrait": "Portrait (832x1216)",
    "landscape": "Landscape (1216x832)",
    "square": "Square (1024x1024)",
})

RESOLUTION_OBJECTS = OrderedDict({
    "portrait": ImageResolution.Normal_Portrait_v3,
    "landscape": ImageResolution.Normal_Landscape_v3,
    "square": ImageResolution.Normal_Square_v3,
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
