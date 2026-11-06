"""Gravador AVI/MJPEG em Python puro (+ Pillow para JPEG).

Estrutura do arquivo:
RIFF 'AVI '
 ├─ LIST 'hdrl' (avih + LIST 'strl' (strh + strf))
 ├─ LIST 'movi' (chunks '00dc', um JPEG por frame)
 └─ 'idx1' (índice)
Os tamanhos são gravados como 0 e corrigidos no close() (seek).
"""
import io
import queue
import struct
import threading
import time

from PIL import Image

from .image import rgba_to_pil


def _chunk(fourcc, payload):
    pad = b"\x00" if len(payload) & 1 else b""
    return fourcc + struct.pack("<I", len(payload)) + payload + pad


class AviMjpegWriter:
    """Escreve frames JPEG num .avi. Frames repetidos (quando a captura
    atrasa) reaproveitam o mesmo chunk via índice, sem gastar espaço."""

    def __init__(self, path, width, height, fps=30, quality=80):
        self.path, self.w, self.h = str(path), int(width), int(height)
        self.fps, self.quality = int(fps), int(quality)
        self._f = open(self.path, "wb")
        self._index = []          # (offset_rel_movi, size)
        self._count = 0           # frames no vídeo (incluindo repetidos)
        self._max_chunk = 0
        self._last = None         # (offset, size) do último chunk real
        self._write_headers()

    # ---------- cabeçalhos ----------
    def _write_headers(self):
        f, us = self._f, 1_000_000 // self.fps
        f.write(b"RIFF" + struct.pack("<I", 0) + b"AVI ")
        # --- hdrl ---
        avih = struct.pack("<14I", us, 0, 0, 0x10, 0, 0, 1, 0,
                           self.w, self.h, 0, 0, 0, 0)
        strh = struct.pack("<4s4sIHHIIIIIIII4H", b"vids", b"MJPG", 0, 0, 0, 0,
                           1, self.fps, 0, 0, 0, 0xFFFFFFFF, 0, 0, 0, self.w, self.h)
        strf = struct.pack("<IiiHH4sIiiII", 40, self.w, self.h, 1, 24, b"MJPG",
                           self.w * self.h * 3, 0, 0, 0, 0)
        strl = b"strl" + _chunk(b"strh", strh) + _chunk(b"strf", strf)
        hdrl = b"hdrl" + _chunk(b"avih", avih) + _chunk(b"LIST", strl)
        f.write(b"LIST" + struct.pack("<I", len(hdrl)) + hdrl)
        # --- início do movi ---
        self._movi_size_pos = f.tell() + 4
        f.write(b"LIST" + struct.pack("<I", 0) + b"movi")
        self._movi_data_start = f.tell() - 4   # posição do fourcc 'movi'
        # posições para correção posterior
        self._avih_frames_pos = 12 + 8 + 4 + 8 + 16   # total_frames em avih
        self._avih_buf_pos = self._avih_frames_pos + 12
        self._strh_len_pos = 12 + 8 + 4 + 8 + 56 + 8 + 4 + 8 + 32
        self._strh_buf_pos = self._strh_len_pos + 4

    # ---------- escrita ----------
    def write_jpeg(self, jpeg_bytes, repeat=1):
        """Adiciona um frame JPEG já codificado; 'repeat' duplica via índice."""
        f = self._f
        off = f.tell() - self._movi_data_start
        f.write(_chunk(b"00dc", jpeg_bytes))
        self._last = (off, len(jpeg_bytes))
        self._max_chunk = max(self._max_chunk, len(jpeg_bytes))
        for _ in range(max(1, repeat)):
            self._index.append(self._last)
            self._count += 1

    def repeat_last(self, n=1):
        if self._last:
            for _ in range(n):
                self._index.append(self._last)
                self._count += 1

    def write_rgba(self, data, width, height, bottom_up=True, place=None, req=None):
        img = rgba_to_pil(data, width, height, bottom_up).convert("RGB")
        if place is not None and req and (width, height) != tuple(req):
            bg = Image.new("RGB", tuple(req), (0, 0, 0))   # parte fora da tela = preto
            bg.paste(img, place)
            img = bg
        if img.size != (self.w, self.h):
            img = img.resize((self.w, self.h), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.quality)
        self.write_jpeg(buf.getvalue())

    @property
    def frame_count(self):
        return self._count

    # ---------- fechamento ----------
    def close(self):
        if self._f.closed:
            return
        f = self._f
        movi_end = f.tell()
        idx = b"".join(struct.pack("<4sIII", b"00dc", 0x10, o, s)
                       for o, s in self._index)
        f.write(_chunk(b"idx1", idx))
        end = f.tell()
        f.seek(4);                      f.write(struct.pack("<I", end - 8))
        f.seek(self._movi_size_pos);    f.write(struct.pack("<I", movi_end - self._movi_size_pos - 4))
        f.seek(self._avih_frames_pos);  f.write(struct.pack("<I", self._count))
        f.seek(self._avih_buf_pos);     f.write(struct.pack("<I", self._max_chunk))
        f.seek(self._strh_len_pos);     f.write(struct.pack("<I", self._count))
        f.seek(self._strh_buf_pos);     f.write(struct.pack("<I", self._max_chunk))
        f.close()


class AsyncVideoRecorder:
    """Fila + thread: a interface só enfileira pixels; a codificação JPEG
    e a escrita em disco acontecem fora da thread do Kivy."""

    def __init__(self, path, width, height, fps=30, quality=80, max_queue=6):
        self.fps = fps
        self._writer = AviMjpegWriter(path, width, height, fps, quality)
        self._q = queue.Queue(maxsize=max_queue)
        self._t0 = None
        self.dropped = 0
        self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push(self, rgba, w, h, bottom_up=True, place=None, req=None):
        """Chamar na thread principal. Descarta o frame se a fila encher."""
        now = time.perf_counter()
        if self._t0 is None:
            self._t0 = now
        try:
            self._q.put_nowait((now - self._t0, rgba, w, h, bottom_up, place, req))
        except queue.Full:
            self.dropped += 1

    def _run(self):
        wr = self._writer
        while True:
            item = self._q.get()
            if item is None:
                break
            if self._error is not None:
                continue
            t, rgba, w, h, bu, place, req = item
            try:
                target = int(round(t * self.fps))
                if wr.frame_count and target > wr.frame_count:
                    wr.repeat_last(target - wr.frame_count)
                wr.write_rgba(rgba, w, h, bu, place, req)
            except Exception as e:
                self._error = e

    def stop(self):
        self._q.put(None)
        self._thread.join()
        self._writer.close()
        if self._error is not None:
            raise RuntimeError("falha ao gravar o vídeo: %s" % (self._error,)) from self._error
        return self._writer.frame_count
