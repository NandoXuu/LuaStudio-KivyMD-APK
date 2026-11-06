"""Leitura de pixels do OpenGL usado pelo Kivy.
Todas as funções devem rodar na thread principal (contexto GL)."""

GL_PACK_ALIGNMENT = 0x0D05


def _pack_align():
    """Linhas sem padding (RGBA já é múltiplo de 4, então é só precaução)."""
    try:
        from kivy.graphics.opengl import glPixelStorei
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
    except Exception:
        pass


def window_size_px():
    """Tamanho do framebuffer em pixels. Usa Window.size (como o próprio
    Window.screenshot do Kivy); não multiplica por densidade, o que podia
    fazer a leitura passar do framebuffer."""
    from kivy.core.window import Window
    w, h = Window.size
    return int(w), int(h)


def read_rect(gl_x, gl_y, width, height):
    """Lê só um retângulo (coordenadas GL: origem embaixo-esquerda).
    Mais rápido que ler a tela toda e recortar depois."""
    from kivy.graphics.opengl import glReadPixels
    _pack_align()
    GL_RGBA, GL_UNSIGNED_BYTE = 0x1908, 0x1401
    return bytes(glReadPixels(int(gl_x), int(gl_y), int(width), int(height),
                              GL_RGBA, GL_UNSIGNED_BYTE))


def read_framebuffer(width, height):
    """Lê RGBA do framebuffer atual (origem embaixo-esquerda).
    Chame durante o evento Window.on_flip, antes do swap de buffers."""
    return read_rect(0, 0, width, height)


def read_widget(widget):
    """Renderiza um widget (e filhos) em textura própria e devolve
    (rgba_bytes, w, h). Pixels vêm com origem embaixo-esquerda."""
    img = widget.export_as_image()
    tex = img.texture
    return bytes(tex.pixels), tex.width, tex.height
