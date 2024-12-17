import json
import discord
from io import BytesIO
from PIL import Image
from typing import Any, Dict
from collections import OrderedDict

from imagescanner.constants import log, NAIV3_PARAMS, PARAM_REGEX, PARAM_GROUP_REGEX, PARAMS_BLACKLIST


def get_params_from_string(param_str: str) -> OrderedDict[str, Any]:
    output_dict = OrderedDict()
    if "NovelAI3 Parameters: " in param_str:
        prompts, params = param_str.rsplit("NovelAI3 Parameters: ", 1)
        output_dict["NovelAI3 Prompt"], output_dict["Negative Prompt"] = prompts.rsplit("Negative prompt: ", 1)
        param_dict = json.loads(params)
        for key, new_key in NAIV3_PARAMS.items():
            if key in param_dict:
                output_dict[new_key] = str(param_dict[key])
    else:
        prompts, params = param_str.rsplit("Steps: ", 1)
        try:
            output_dict["Prompt"], output_dict["Negative Prompt"] = prompts.rsplit("Negative prompt: ", 1)
        except ValueError:
            output_dict["Prompt"] = prompts

        params = f"Steps: {params},"
        params = PARAM_GROUP_REGEX.sub("", params)
        param_list = PARAM_REGEX.findall(params)
        for key, value in param_list:
            if len(output_dict) > 24 or any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                continue
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


async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: Dict[int, str], image_bytes: Dict[int, bytes]) -> None:
    try:
        image_data = await attachment.read()
        with Image.open(BytesIO(image_data)) as img:
            try:
                if attachment.filename.endswith(".png"):
                    info = img.info['parameters']
                else:  # jpeg jank
                    info = img._getexif().get(37510).decode('utf8')[7:]
                if info and "Steps" in info:
                    metadata[i] = info
                    image_bytes[i] = image_data
            except (KeyError, ValueError, IndexError, UnicodeDecodeError):  # novelai
                if "Title" in img.info and img.info["Title"] == "AI generated image":
                    metadata[i] = convert_novelai_info(img.info)
                    image_bytes[i] = image_data
    except (discord.DiscordException, Image.UnidentifiedImageError):
        log.exception("Downloading attachment")


def remove_field(embed: discord.Embed, field_name: str):
    for i, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.remove_field(i)
            return
