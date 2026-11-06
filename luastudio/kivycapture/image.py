"""Conversão de pixels brutos e gravação PNG/JPEG via Pillow."""
from PIL import Image


def rgba_to_pil(data, width, height, bottom_up=True):
    """Bytes RGBA -> PIL.Image. O OpenGL entrega as linhas de baixo para cima;
    o argumento 'raw' com orientação -1 já inverte sem cópia extra."""
    orient = -1 if bottom_up else 1
    return Image.frombuffer("RGBA", (width, height), data, "raw", "RGBA", 0, orient)


def save_image(img, path, quality=92):
    """Salva por extensão. JPEG não tem alpha, então converte para RGB."""
    ext = str(path).lower().rsplit(".", 1)[-1]
    if ext in ("jpg", "jpeg"):
        img.convert("RGB").save(path, "JPEG", quality=quality)
    elif ext == "png":
        img.save(path, "PNG", optimize=False)
    else:
        img.save(path)
    return str(path)


def compose(data, w, h, place, req, out_size):
    """Pixels lidos -> imagem final: completa a área que saiu da tela
    (transparente) e redimensiona para o tamanho de saída."""
    img = rgba_to_pil(data, w, h)
    if place is not None and req and (w, h) != tuple(req):
        canvas = Image.new("RGBA", tuple(req), (0, 0, 0, 0))
        canvas.paste(img, place)
        img = canvas
    if out_size and img.size != tuple(out_size):
        img = img.resize(tuple(out_size), Image.LANCZOS)
    return img
