from io import BytesIO
from PIL import Image
from base64 import b64encode


def sanitize(text: str) -> str:
    special_characters = "[]"
    for c in special_characters:
        text = text.replace(c, "")
    return text

def farenheit_to_celsius(match) -> str:
    f = float(match.group(1))
    c = (f - 32) * 5.0/9.0
    return f"{round(f)}°F/{round(c)}°C"

def make_image_content(fp: BytesIO) -> dict:
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{b64encode(fp.read()).decode()}"
        }
    }

def process_image(buffer: BytesIO) -> BytesIO | None:
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
