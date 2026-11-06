import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _png(head):
    if len(head) < 24 or head[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return {"Format": "png", "Width": w, "Height": h}


def _jpeg(data):
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in SOF_MARKERS:
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return {"Format": "jpg", "Width": w, "Height": h}
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg
    return None


def read_image_info(path):
    with open(path, "rb") as handle:
        data = handle.read(262144)
    if data[:8] == PNG_SIGNATURE:
        return _png(data)
    if data[:2] == b"\xff\xd8":
        return _jpeg(data)
    return None
