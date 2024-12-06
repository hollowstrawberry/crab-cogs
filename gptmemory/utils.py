from io import BytesIO
from re import Match
from PIL import Image
from base64 import b64encode
from typing import TypeVar


def sanitize(text: str) -> str:
    special_characters = "[]"
    for c in special_characters:
        text = text.replace(c, "")
    return text

def farenheit_to_celsius(match: Match) -> str:
    f = float(match.group(1))
    c = (f - 32) * 5.0/9.0
    return f"{round(c)}°C/{round(f)}°F"

def make_image_content(fp: BytesIO) -> dict:
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{b64encode(fp.read()).decode()}"
        }
    }

def process_image(buffer: BytesIO) -> BytesIO:
    image = Image.open(buffer)
    width, height = image.size
    image_resolution = width * height
    target_resolution = 1024*1024
    if image_resolution > target_resolution:
        scale_factor = (target_resolution / image_resolution) ** 0.5
        image = image.resize((int(width * scale_factor), int(height * scale_factor)), Image.Resampling.LANCZOS)
    fp = BytesIO()
    image.save(fp, "PNG")
    fp.seek(0)
    return fp

def get_text_contents(messages: list[dict]):
    temp_messages = []
    for msg in messages:
        if isinstance(msg["content"], str):
            temp_messages.append(msg)
        else:
            for cnt in msg["content"]:
                if "text" in cnt:
                    temp_messages.append({
                        "role": msg["role"],
                        "content": cnt["text"]
                    })
                break
    return temp_messages

T = TypeVar("T", bound=type)

def get_subclasses(glob: dict, base_cls: T) -> list[T]:
    return [cls for cls in glob.values()
            if isinstance(cls, type) and issubclass(cls, base_cls) and cls is not base_cls]
