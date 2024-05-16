import re
from redbot.core.app_commands import Choice
from collections import OrderedDict

VIEW_TIMEOUT = 5 * 60

MAX_FREE_IMAGE_SIZE = 1024*1024
MAX_UPLOADED_IMAGE_SIZE = 1920*1080

DEFAULT_PROMPT = "best quality, amazing quality, very aesthetic, absurdres"

DEFAULT_FURRY_PROMPT = "{best quality}, {amazing quality}"

DEFAULT_NEGATIVE_PROMPT = "{bad}, text, error, missing, extra, fewer, cropped, jpeg artifacts, " \
                          "worst quality, bad quality, watermark, signature, username, logo, " \
                          "displeasing, unfinished, chromatic aberration, scan, scan artifacts, simple background"
                          
DEFAULT_FURRY_NEGATIVE_PROMPT = "{{worst quality}}, [displeasing], {unusual pupils}, guide lines, {{unfinished}}, " \
                                "{bad}, url, artist name, {{tall image}}, mosaic, {sketch page}, comic panel, " \
                                "impact (font), [dated], {logo}, ych, {what}, {where is your god now}, " \
                                "{distorted text}, repeated text, {floating head}, {1994}, {widescreen}, " \
                                "absolutely everyone, sequence, {compression artifacts}, hard translated, " \
                                "{cropped}, {commissioner name}, unknown text, high contrast"
                                
NSFW_TERMS = re.compile(r"\b(nsfw|explicit|questionable|sensitive|suggestive|nude|naked|sex|cum"
                        r"|topless|bottomless|no (panties|bra|clothes|underwear)"
                        r"|anus|penis|pussy|nipples?|labia|vulva|cleft|clit(oris|oral)?"
                        r"|anal|oral|vaginal?|[pn]aizuri|miss?ionary|cowgirl|hetero|fell?atio|cunn?ilingus"
                        r"|futa(nari)?|undressing|gore|guro|ass juice|scat|poop(ing)?|pee(ing)?"
                        r"|pant(y|ies)|(?<!sports )bra|underwear|lingerie)\b")

TOS_TERMS = re.compile(r"\b(loli(con)?s?|shota(con)?s?|child(ren|s)?)\b")

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

MODELS = OrderedDict({
    "nai-diffusion-3": "Anime v3",
    "nai-diffusion-furry-3": "Furry v3",
})

INPAINTING_MODELS = OrderedDict({
    "nai-diffusion-3-inpainting": "Anime v3 Inpainting",
    "nai-diffusion-furry-3-inpainting": "Furry v3 Inpainting",
})

NOISE_SCHEDULES = [
    "Always pick recommended", "native", "karras", "exponential", "polyexponential",
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
    "noise_schedule": "The recommended option is based on the sampler.",
    "decrisper": "Reduces artifacts caused by high guidance.",
    "model": "The model to use for generation.",
}
PARAMETER_DESCRIPTIONS_IMG2IMG = PARAMETER_DESCRIPTIONS.copy()
PARAMETER_DESCRIPTIONS_IMG2IMG.pop("resolution")

PARAMETER_CHOICES = {
    "resolution": [Choice(name=title, value=value) for value, title in RESOLUTION_TITLES.items()],
    "sampler": [Choice(name=title, value=value) for value, title in SAMPLER_TITLES.items()],
    "sampler_version": [Choice(name=ver, value=ver) for ver in SAMPLER_VERSIONS],
    "noise_schedule": [Choice(name=sch, value=sch) for sch in NOISE_SCHEDULES],
    "model": [Choice(name=title, value=value) for value, title in MODELS.items()],
}

PARAMETER_CHOICES_IMG2IMG = PARAMETER_CHOICES.copy()
PARAMETER_CHOICES_IMG2IMG.pop("resolution")

PARAMETER_DESCRIPTIONS_VIBE = {
    "reference_image1": "Vibe transfer: Image to use as a reference.",
    "reference_image_strength1": "Vibe transfer: How strongly the reference image is used.",
    "reference_image_info_extracted1": "Vibe transfer: The amount of information to extract.",
    "reference_image2": "Vibe transfer: Image to use as a reference.",
    "reference_image_strength2": "Vibe transfer: How strongly the reference image is used.",
    "reference_image_info_extracted2": "Vibe transfer: The amount of information to extract.",
    "reference_image3": "Vibe transfer: Image to use as a reference.",
    "reference_image_strength3": "Vibe transfer: How strongly the reference image is used.",
    "reference_image_info_extracted3": "Vibe transfer: The amount of information to extract.",
}
