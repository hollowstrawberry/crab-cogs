from wand.image import Image
from wand.color import Color

def svg_to_png(svg: str):
    with Image(blob=svg, background=Color("transparent")) as img:
        img.format = "png"
        return img.make_blob()
