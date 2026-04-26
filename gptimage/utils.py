from io import BytesIO
from PIL import Image
from typing import Tuple, Union

MIN_PIXELS = 700000
MAX_PIXELS = 1280*1280
MULTIPLE = 16

def round_to_nearest(value: Union[int, float], multiple: int) -> int:
    return int(multiple * round(value / multiple))

def scale_to_size(width: int, height: int, pixels: int) -> Tuple[int, int]:
    scale = (pixels / (width * height)) ** 0.5
    return int(width * scale), int(height * scale)

# Maximum edge length must be less than or equal to 3840px
# Both edges must be multiples of 16px
# Long edge to short edge ratio must not exceed 3:1
# Total pixels must be at least 655,360 and no more than 8,294,400
def normalize_image(b: bytes | BytesIO) -> Tuple[bytes, str]:
    b = b if isinstance(b, BytesIO) else BytesIO(b)
    b.seek(0)
    image = Image.open(b)
    width, height = image.width, image.height
    if width*height > MAX_PIXELS:
        width, height = scale_to_size(width, height, MAX_PIXELS)
    elif width*height < MIN_PIXELS:
        width, height = scale_to_size(width, height, MIN_PIXELS)
    if width % MULTIPLE != 0 or height % MULTIPLE != 0:
        width, height = round_to_nearest(width, MULTIPLE), round_to_nearest(height, MULTIPLE)
    if width > height * 3:
        width = round_to_nearest(height * 2.95, MULTIPLE)
    elif height > width * 3:
        height = round_to_nearest(width * 2.95, MULTIPLE)
    if image.width != width or image.height != height:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    fp = BytesIO()
    image.save(fp, "PNG")
    return fp.getvalue(), f"{width}x{height}"
