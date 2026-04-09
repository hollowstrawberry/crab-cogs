import json
import asyncio
import discord
import PIL.Image
from io import BytesIO
from typing import Any, Dict

from imagescanner.comfy import ComfyMetadataReader
from imagescanner.metadata import Metadata, WebuiMetadata
from imagescanner.constants import SUPPORTED_FORMATS, log


def build_embed(embed_dict: Dict[str, Any], author: discord.Member) -> discord.Embed:
    embed = discord.Embed(title="Here's your image!", color=author.color)
    for key in embed_dict.keys():
        if len(str(embed_dict[key])) > 1000:
            embed_dict[key] = str(embed_dict[key])[:997] + "..."
        elif isinstance(embed_dict[key], float):
            embed_dict[key] = f"{embed_dict[key]:.4f}".rstrip("0")
    for key, value in embed_dict.items():
        if "hashes" in key:
            continue
        embed.add_field(name=key, value=value, inline="Prompt" not in key)
    embed.set_footer(text=f"Posted by {author}", icon_url=author.display_avatar.url)
    return embed

def read_metadata(image_data: bytes) -> Metadata | None:
    b = BytesIO(image_data)
    img = PIL.Image.open(b)
    raw = img.info.get("parameters") or img.getexif().get(0x9286)
    metadata = WebuiMetadata(raw)
    if metadata.as_dict():
        return metadata
    metadata = ComfyMetadataReader.from_info(img.info, img.width, img.height)
    if metadata.is_comfy:
        return metadata
    return None

async def grab_attachment_metadata(i: int, attachment: discord.Attachment, metadata: Dict[int, Metadata], image_bytes: Dict[int, bytes]) -> None:
    if not attachment.filename.endswith(SUPPORTED_FORMATS):
        return
    try:
        current_image_bytes = await attachment.read()
        current_image_metadata = await asyncio.to_thread(read_metadata, current_image_bytes)
    except Exception:
        log.exception("Processing attachment")
        return
    if current_image_metadata:
        image_bytes[i] = current_image_bytes
        metadata[i] = current_image_metadata

def remove_field(embed: discord.Embed, field_name: str):
    for i, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.remove_field(i)
            return
