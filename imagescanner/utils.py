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

from imagescanner.constants import log, NAIV3_PARAMS, PARAM_REGEX, PARAM_GROUP_REGEX, PARAMS_BLACKLIST, METADATA_REGEX


def get_params_from_metadata(metadata: ImageDataReader) -> "OrderedDict[str, Any]":
    output_dict = OrderedDict()

    if "A1111" in metadata._tool or "NovelAI" in metadata._tool:
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

    else:
        output_dict["Prompt"] = metadata.positive or metadata.positive_sdxl
        output_dict["Negative Prompt"] = metadata.negative or metadata.negative_sdxl
        
        if "Comfy" in metadata._tool:
            try:
                workflow = json.loads("{" + metadata.raw.split("{", 1)[1])
                for node_id, node in workflow.items():
                    if node["class_type"] == "LoraLoader":
                        lora_name = node.get("inputs", {}).get("lora_name", "").replace(".safetensors", "")
                        lora_weight = node.get("inputs", {}).get("strength_model", 1.0)
                        if lora_name:
                            output_dict["Prompt"] = output_dict["Prompt"] + f" <lora:{lora_name}:{lora_weight}>"  # type: ignore
                    elif node_id == "extra_seed_extra_noise":
                        output_dict["Extra Seed"] = node.get("inputs", {}).get("noise_seed", -1)
                    elif node_id == "extra_seed_noised_latent_blend":
                        output_dict["Extra Seed Strength"] = round(1.0 - node.get("inputs", {}).get("blend_factor", 1.0), 4)

            except Exception:
                log.warning("Loading comfy metadata", exc_info=True)

        for key, value in metadata.parameter.items():
            if len(output_dict) > 24 or any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                continue
            output_dict[key.title()] = value

        return output_dict

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
        img = await asyncio.to_thread(PIL.Image.open, b)
        if (img.mode == "RGBA"):  # in rare cases, when ImageDataReader reads an RGBA image, it gets stuck in an infinite loop
            b = await asyncio.to_thread(remove_transparency, img)
        del img
        b.seek(0)
        image_metadata = await asyncio.to_thread(ImageDataReader, b)
    except Exception: # previously (discord.DiscordException, PIL.Image.UnidentifiedImageError, PIL.Image.DecompressionBombError, SyntaxError)
        log.exception("Processing attachment")
        return
    if image_metadata.status.name == "READ_SUCCESS":
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
