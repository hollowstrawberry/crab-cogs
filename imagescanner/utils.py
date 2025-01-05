import json
import discord
from io import BytesIO
from PIL import Image
from typing import Any, Dict, Optional
from collections import OrderedDict
from sd_prompt_reader.constants import SUPPORTED_FORMATS
from sd_prompt_reader.image_data_reader import ImageDataReader

from imagescanner.constants import log, NAIV3_PARAMS, PARAM_REGEX, PARAM_GROUP_REGEX, PARAMS_BLACKLIST, METADATA_REGEX


def get_params_from_string(param_str: str) -> OrderedDict[str, Any]:
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
        return "(Unknown)\nNegative prompt: (Unknown)\nComfyUI Data: Too complex to display"
    elif metadata.status.name == "READ_SUCCESS":
        if "A1111" in metadata._tool:
            return metadata.raw
        else:
            positive = metadata.positive or metadata.positive_sdxl or "(None)"
            negative = metadata.negative or metadata.negative_sdxl or "(None)"
            fixed_setting = metadata.setting
            if positive and len(positive.strip()) > 10:
                fixed_setting = fixed_setting.replace(positive, "(Prompt)")
            if negative and len(negative.strip()) > 10:
                fixed_setting = fixed_setting.replace(negative, "(Negative Prompt)")
            return f"{positive}\nNegative prompt: {negative}\nSource: {metadata._tool}, {fixed_setting}"
    else:
        return None


async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: Dict[int, str], image_bytes: Dict[int, bytes]) -> None:
    if not any(attachment.filename.endswith(ext) for ext in SUPPORTED_FORMATS):
        return
    try:
        image_data = await attachment.read()
        image_metadata = ImageDataReader(BytesIO(image_data))
    except (discord.DiscordException, Image.UnidentifiedImageError):
        log.exception("Processing attachment")
        return
    metadata_str = convert_metadata(image_metadata)
    if metadata_str:
        image_bytes[i] = image_data
        metadata[i] = metadata_str


def remove_field(embed: discord.Embed, field_name: str):
    for i, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.remove_field(i)
            return
