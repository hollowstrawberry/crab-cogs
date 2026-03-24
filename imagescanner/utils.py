import json
import PIL.Image
import asyncio
import discord
from io import BytesIO
from PIL.Image import Image
from PIL import PngImagePlugin
from typing import Any, Dict
from collections import OrderedDict
from sd_prompt_reader.constants import SUPPORTED_FORMATS
from sd_prompt_reader.image_data_reader import ImageDataReader

from imagescanner.comfy import ComfyMetadataReader
from imagescanner.constants import log, NAIV3_PARAMS, PARAM_REGEX, PARAM_GROUP_REGEX, PARAMS_BLACKLIST, METADATA_REGEX


def get_params_from_metadata(metadata: ImageDataReader) -> OrderedDict[str, Any]:
    output_dict = OrderedDict()

    if "A1111" in metadata._tool:
        match = METADATA_REGEX.match(metadata.raw)
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
        for key, value in param_list:
            if len(output_dict) >= 25 or key in output_dict:
                continue
            if any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                continue
            if len(key) > 255:
                key = key[:252] + "..."
            output_dict[key] = value

    elif "Comfy" in metadata._tool:
        comfy_data = ComfyMetadataReader.from_info(metadata._info)
        if comfy_data:
            output_dict = comfy_data.as_dict()
    else:
        output_dict["Prompt"] = metadata.positive or metadata.positive_sdxl
        output_dict["Negative Prompt"] = metadata.negative or metadata.negative_sdxl
        
        for key, value in metadata.parameter.items():
            if len(output_dict) > 24 or any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                continue
            if "NovelAI" in metadata._tool:
                if key in NAIV3_PARAMS:
                    key = NAIV3_PARAMS[key]
                else:
                    continue
            if len(key) > 255:
                key = key[:252] + "..."
            output_dict[key.title()] = value

    return output_dict


def get_embed(embed_dict: Dict[str, Any], author: discord.Member) -> discord.Embed:
    embed = discord.Embed(title="Here's your image!", color=author.color)
    for key in embed_dict.keys():
        if len(str(embed_dict[key])) > 1000:
            embed_dict[key] = str(embed_dict[key])[:997] + "..."
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


async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: Dict[int, ImageDataReader], image_bytes: Dict[int, bytes]) -> None:
    if not any(attachment.filename.endswith(ext) for ext in SUPPORTED_FORMATS):
        return
    try:
        current_image_bytes = await attachment.read()
        b = BytesIO(current_image_bytes)
        img = PIL.Image.open(b)
        await asyncio.to_thread(img.load)
        if (img.mode == "RGBA"):  # in rare cases, when ImageDataReader reads an RGBA image, it gets stuck in an infinite loop
            b = await asyncio.to_thread(remove_transparency, img)
        del img
        b.seek(0)
        image_metadata = await asyncio.to_thread(ImageDataReader, b)
    except Exception:
        log.exception("Processing attachment")
        return
    if image_metadata and image_metadata.status.name != "FORMAT_ERROR":
        image_bytes[i] = current_image_bytes
        metadata[i] = image_metadata

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
