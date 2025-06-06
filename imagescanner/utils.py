import json
import PIL.Image
import discord
from io import BytesIO
from PIL.Image import Image
from PIL import PngImagePlugin
from typing import Any, Dict, Optional
from collections import OrderedDict
from sd_prompt_reader.constants import SUPPORTED_FORMATS
from sd_prompt_reader.image_data_reader import ImageDataReader

from imagescanner.constants import log, NAIV3_PARAMS, PARAM_REGEX, PARAM_GROUP_REGEX, PARAMS_BLACKLIST, METADATA_REGEX


def get_params_from_string(param_str: str) -> "OrderedDict[str, Any]":
    output_dict = OrderedDict()

    match = METADATA_REGEX.match(param_str)
    if not match:
        output_dict["Metadata"] = "Invalid"
        return output_dict

    if prompt := match.group("Prompt"):
        output_dict["Prompt"] = prompt
    if negative_prompt := match.group("NegativePrompt"):
        output_dict["Negative Prompt"] = negative_prompt

    params = match.group("Params")
    params = PARAM_GROUP_REGEX.sub("", params)
    param_list = PARAM_REGEX.findall(params)
    is_novelai = False
    for key, value in param_list:
        if key == "Source" and value == "NovelAI":
            is_novelai = True
        if is_novelai:
            if key in NAIV3_PARAMS:
                key = NAIV3_PARAMS[key]
            else:
                continue
        if len(output_dict) >= 25 or key in output_dict:
            continue
        if any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
            continue
        if len(key) > 255:
            key = key[:252] + "..."
        output_dict[key] = value

    for key in output_dict:
        if len(output_dict[key]) > 1000:
            output_dict[key] = output_dict[key][:1000] + "..."

    return output_dict


def get_embed(embed_dict: Dict[str, Any], author: discord.Member) -> discord.Embed:
    embed = discord.Embed(title="Here's your image!", color=author.color)
    for key, value in embed_dict.items():
        if "hashes" in key:
            continue
        embed.add_field(name=key, value=value, inline='Prompt' not in key)
    embed.set_footer(text=f'Posted by {author}', icon_url=author.display_avatar.url)
    return embed


def convert_novelai_info(img_info: Dict[str, Any]) -> str:
    info = json.loads(img_info["Comment"])
    prompt = info.pop('prompt')
    negative_prompt = "Negative prompt: " + info.pop('uc')
    return f"{prompt}\n{negative_prompt}\nNovelAI3 Parameters: {json.dumps(info)}"


def convert_metadata(metadata: ImageDataReader) -> Optional[str]:
    if metadata.status.name == "COMFYUI_ERROR":
        return f"Source: {metadata._tool}, Metadata: Workflow too complex,"
    elif metadata.status.name == "READ_SUCCESS":
        if "A1111" in metadata._tool:
            return metadata.raw + ","
        else:
            positive = metadata.positive or str(metadata.positive_sdxl) or "(None)"
            negative = metadata.negative or str(metadata.negative_sdxl) or "(None)"
            fixed_setting = metadata.setting
            if positive and len(positive.strip()) > 10:
                fixed_setting = fixed_setting.replace(positive, "(Prompt)")
            if negative and len(negative.strip()) > 10:
                fixed_setting = fixed_setting.replace(negative, "(Negative Prompt)")
            return f"{positive}\nNegative prompt: {negative}\nSource: {metadata._tool}, {fixed_setting},"
    else:
        return None


async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: Dict[int, str], image_bytes: Dict[int, bytes]) -> None:
    if not any(attachment.filename.endswith(ext) for ext in SUPPORTED_FORMATS):
        return
    try:
        image_data = await attachment.read()
        b = BytesIO(image_data)
        img = PIL.Image.open(b)
        if (img.mode == "RGBA"):  # in rare cases, when ImageDataReader reads an RGBA image, it gets stuck in an infinite loop
            b = remove_transparency(img)
        del img
        b.seek(0)
        image_metadata = ImageDataReader(b)
    except (discord.DiscordException, PIL.Image.UnidentifiedImageError):
        log.exception("Processing attachment")
        return
    metadata_str = convert_metadata(image_metadata)
    if metadata_str:
        image_bytes[i] = image_data
        metadata[i] = metadata_str

def remove_transparency(img: Image):
    info = img.info.copy()
    new = PIL.Image.new("RGB", img.size, (0, 0, 0))
    new.paste(img, mask=img.split()[-1])
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in info.items():
        pnginfo.add_text(key, str(value))
    b = BytesIO()
    img.save(b, format="PNG", pnginfo=pnginfo)
    return b

def remove_field(embed: discord.Embed, field_name: str):
    for i, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.remove_field(i)
            return
