import os
import re

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from . import filebrowser
from . import permissions as perms
from . import project as luaproject
from .mdui import (BG, ERROR, PRIMARY_CONTAINER, TEXT, TEXT_DIM,
                   TEXT_FAINT, IconTile, PickTile, Swatch, lbl, md_button,
                   icon_button, rgba, surface_card, wrap_label)

GLYPHS = ["@initial"] + list(luaproject.ICON_GLYPHS)


class NewProjectScreen(MDScreen):
    def __init__(self, app, home, **kw):
        MDScreen.__init__(self, name="new_project", **kw)
        self.app = app
        self.home = home
        self.md_bg_color = rgba(BG)
        self.mode = None
        self.template = "draw"
        self.icon_state = {"glyph": "@initial",
                           "color": luaproject.ICON_COLORS[0], "image": None}
        self.root_box = BoxLayout(orientation="vertical",
                                  padding=(dp(14), dp(12), dp(14), dp(12)),
                                  spacing=dp(12))
        self.add_widget(self.root_box)
        self._show_chooser()

    def reset(self):
        self.icon_state = {"glyph": "@initial",
                           "color": luaproject.ICON_COLORS[0], "image": None}
        self._show_chooser()

    def go_home(self):
        if self.manager is not None:
            self.manager.current = "home"

    def _header(self, title, back):
        row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(6))
        btn = icon_button(icon="arrow-left", size_hint=(None, None),
                           size=(dp(48), dp(48)))
        btn.bind(on_release=lambda *_a: back())
        row.add_widget(btn)
        row.add_widget(lbl(title, 22, TEXT, bold=True, shorten=True))
        return row

    def _show_chooser(self):
        self.mode = None
        self.root_box.clear_widgets()
        self.root_box.add_widget(self._header("Novo projeto", self.go_home))
        self.root_box.add_widget(lbl("Escolha o tipo de projeto", 14, TEXT_DIM,
                                     size_hint_y=None, height=dp(24)))
        self.root_box.add_widget(self._type_card(
            "gamepad-variant", "Projeto normal",
            "Jogo em Lua rodando na engine do LuaStudio. Você escreve os "
            "scripts e testa direto no celular.",
            lambda: self._show_form("normal")))
        self.root_box.add_widget(self._type_card(
            "nintendo-game-boy", "Projeto GBA",
            "Jogo em C compilado numa ROM .gba para Game Boy Advance, com o "
            "editor GBA.",
            lambda: self._show_form("gba")))
        self.root_box.add_widget(Widget())

    def _type_card(self, icon, title, desc, on_pick):
        card = surface_card(orientation="vertical", size_hint_y=None,
                            spacing=dp(12),
                            padding=(dp(16), dp(16), dp(16), dp(16)), radius=28)
        card.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        top = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(14))
        top.add_widget(IconTile({"glyph": "@initial", "color": PRIMARY_CONTAINER},
                                md_icon=icon, size_px=dp(56)))
        top.add_widget(lbl(title, 22, TEXT, bold=True, shorten=True))
        card.add_widget(top)
        card.add_widget(wrap_label(desc, 14, TEXT_DIM))
        card.add_widget(md_button("Continuar", on_pick, style="filled",
                                  icon="arrow-right", size_hint_y=None,
                                  height=dp(46)))
        return card

    def _show_form(self, mode):
        self.mode = mode
        self.root_box.clear_widgets()
        title = "Projeto normal" if mode == "normal" else "Projeto GBA"
        self.root_box.add_widget(self._header(title, self._show_chooser))

        scroll = ScrollView(bar_width=dp(3))
        self.form = BoxLayout(orientation="vertical", spacing=dp(14),
                              size_hint_y=None,
                              padding=(dp(2), dp(4), dp(2), dp(8)))
        self.form.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        scroll.add_widget(self.form)
        self.root_box.add_widget(scroll)

        self.name_in = MDTextField(MDTextFieldHintText(text="ex: meu_jogo"),
                                   mode="outlined", size_hint_y=None,
                                   height=dp(58))
        self.name_in.bind(text=self._on_name)
        self.name_in.bind(on_text_validate=lambda *_a: self._safe(self._create))
        self.form.add_widget(self._field_label("NOME DO PROJETO"))
        self.form.add_widget(self.name_in)

        self.path_label = wrap_label("", 12, TEXT_FAINT)
        self.err_label = wrap_label("", 13, ERROR)
        if mode == "normal":
            self._normal_fields()
        else:
            self._gba_fields()
        self.form.add_widget(self.path_label)
        self.form.add_widget(self.err_label)

        footer = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        footer.add_widget(md_button("Criar projeto", lambda: self._safe(self._create), style="filled",
                                    icon="check", size_hint_y=None,
                                    height=dp(50)))
        self.root_box.add_widget(footer)
        self._refresh_path()

    def _field_label(self, text):
        return lbl(text, 11, TEXT_FAINT, bold=True, size_hint_y=None,
                   height=dp(18))

    def _normal_fields(self):
        top = BoxLayout(size_hint_y=None, height=dp(76), spacing=dp(14))
        self.preview = IconTile(self.icon_state, size_px=dp(72))
        top.add_widget(self.preview)
        top.add_widget(lbl("Ícone do projeto", 14, TEXT_DIM, shorten=True))
        self.form.add_widget(top)

        self.form.add_widget(self._field_label("ÍCONE"))
        cols = 6
        rows = (len(GLYPHS) + cols - 1) // cols
        grid = GridLayout(cols=cols, spacing=dp(8), size_hint_y=None,
                          height=rows * dp(46) + (rows - 1) * dp(8))
        self.pick_tiles = {}
        for g in GLYPHS:
            t = PickTile(icon={"glyph": g, "color": self.icon_state["color"]},
                         size_px=dp(46))
            t.bind(on_release=lambda *_a, v=g: self._safe(self._pick_glyph, v))
            self.pick_tiles[g] = t
            grid.add_widget(t)
        self.form.add_widget(grid)

        self.form.add_widget(self._field_label("COR"))
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
        self.swatches = {}
        for c in luaproject.ICON_COLORS:
            s = Swatch(c, size_px=dp(32))
            s.bind(on_release=lambda *_a, v=c: self._safe(self._pick_color, v))
            self.swatches[c] = s
            row.add_widget(s)
        row.add_widget(Widget())
        self.form.add_widget(row)

        self.form.add_widget(self._field_label("IMAGEM (OPCIONAL)"))
        img_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.img_btn = md_button("Escolher imagem", self._choose_image,
                                 style="tonal", icon="image-outline",
                                 size_hint_y=None, height=dp(44))
        self.img_clear = icon_button(icon="close", size_hint=(None, None),
                                      size=(dp(44), dp(44)))
        self.img_clear.bind(on_release=lambda *_a: self._clear_image())
        img_row.add_widget(self.img_btn)
        img_row.add_widget(self.img_clear)
        self.form.add_widget(img_row)

        self._pick_color(self.icon_state["color"])
        self._pick_glyph(self.icon_state["glyph"])

    def _gba_fields(self):
        from .gba import toolchain
        self._template_keys = list(toolchain.TEMPLATES.keys())
        if self.template not in self._template_keys and self._template_keys:
            self.template = self._template_keys[0]
        self.form.add_widget(self._field_label("MODELO DO CÓDIGO"))
        self.template_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                      spacing=dp(8))
        self.template_box.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        self.form.add_widget(self.template_box)
        self._build_templates()
        self.form.add_widget(wrap_label(
            "O editor GBA abre o projeto assim que ele é criado.", 13, TEXT_DIM))

    def _build_templates(self):
        self.template_box.clear_widgets()
        for k in self._template_keys:
            style = "filled" if k == self.template else "tonal"
            self.template_box.add_widget(md_button(
                k, lambda k=k: self._pick_template(k), style=style,
                icon="code-braces", size_hint_y=None, height=dp(46)))

    def _pick_template(self, k):
        self.template = k
        self._build_templates()

    def _on_name(self, *_a):
        if self.mode == "normal":
            name = self.name_in.text
            self.preview.set_name(name)
            self.pick_tiles["@initial"].set_name(name)
        self._refresh_path()
        self.err_label.text = ""

    def _refresh_preview(self):
        name = self.name_in.text
        self.preview.set_icon(self.icon_state, name=name,
                              image_abs=self.icon_state["image"])
        self.pick_tiles["@initial"].set_icon(
            {"glyph": "@initial", "color": self.icon_state["color"]}, name=name)

    def _refresh_path(self):
        name = self.name_in.text.strip()
        if self.mode == "gba":
            from .gba.editor_app import gba_root
            folder = re.sub(r"[^\w\- ]", "", name) or "<nome>"
            root = gba_root()
        else:
            folder = luaproject.folder_name(name) if name else "<nome>"
            root = luaproject.projects_root()
        self.path_label.text = "Salvo em %s" % os.path.join(root, folder)

    def _pick_glyph(self, g):
        self.icon_state["glyph"] = g
        self.icon_state["image"] = None
        self._sync_glyph_ui()
        self._refresh_preview()

    def _pick_color(self, c):
        self.icon_state["color"] = c
        for hx, sw in self.swatches.items():
            sw.set_selected(hx == c)
        for g, t in self.pick_tiles.items():
            t.set_color(c)
        self._refresh_preview()

    def _sync_glyph_ui(self):
        has_image = bool(self.icon_state["image"])
        for k, t in self.pick_tiles.items():
            t.set_selected(k == self.icon_state["glyph"] and not has_image)
        if has_image:
            self.img_btn.label_widget.text = "Imagem: %s" % os.path.basename(
                self.icon_state["image"])
            self.img_clear.opacity = 1
            self.img_clear.disabled = False
        else:
            self.img_btn.label_widget.text = "Escolher imagem"
            self.img_clear.opacity = 0
            self.img_clear.disabled = True

    def _choose_image(self):
        def on_pick(path):
            self.icon_state["image"] = path
            self._sync_glyph_ui()
            self._refresh_preview()
        filebrowser.open_picker(
            title="Escolher imagem do ícone", mode="file",
            start=perms.storage_dir(),
            extensions=list(luaproject.ICON_IMAGE_EXTS),
            shortcuts=filebrowser.default_shortcuts(),
            on_select=on_pick)

    def _clear_image(self):
        self.icon_state["image"] = None
        self._sync_glyph_ui()
        self._refresh_preview()

    def _safe(self, fn, *a):
        try:
            fn(*a)
        except Exception as ex:
            import traceback
            print(traceback.format_exc())
            self._error("Erro: %s" % ex)

    def _error(self, msg):
        self.err_label.text = msg

    def _create(self):
        name = self.name_in.text.strip()
        if not name:
            return self._error("Dê um nome ao projeto.")
        if self.mode == "gba":
            return self._create_gba(name)
        return self._create_normal(name)

    def _create_normal(self, name):
        if luaproject.project_exists(name):
            return self._error("Já existe uma pasta “%s” em Documents. "
                               "Escolha outro nome." % luaproject.folder_name(name))
        try:
            perms.request(["storage"])
        except Exception:
            pass
        icon = {"glyph": self.icon_state["glyph"], "color": self.icon_state["color"]}
        try:
            proj = luaproject.create_project(name, icon=icon,
                                             image_src=self.icon_state["image"])
        except FileExistsError:
            return self._error("Já existe uma pasta com esse nome em Documents.")
        except Exception as ex:
            return self._error("Não consegui criar a pasta do projeto: %s\n"
                               "Confira a permissão de armazenamento (cadeado "
                               "no topo da tela inicial)." % ex)
        self.app.open_project(proj)

    def _create_gba(self, name):
        from .gba import toolchain
        from .gba.editor_app import gba_root
        folder = re.sub(r"[^\w\- ]", "", name)
        if not folder:
            return self._error("Use letras, números, espaço ou traço no nome.")
        path = os.path.join(gba_root(), folder)
        if os.path.isfile(os.path.join(path, toolchain.CONFIG_NAME)):
            return self._error("Já existe um projeto GBA com esse nome.")
        try:
            perms.request(["storage"])
        except Exception:
            pass
        try:
            toolchain.create_project(path, self.template)
        except Exception as ex:
            return self._error("Não consegui criar o projeto GBA: %s" % ex)
        self.app.open_gba_editor()
        self.app.sm.get_screen("gba").open_project(path)
