import time

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.dialog import (MDDialog, MDDialogButtonContainer,
                               MDDialogHeadlineText, MDDialogSupportingText)
from kivymd.uix.screen import MDScreen

from . import permissions as perms
from . import project as luaproject
from .mdui import (BG, ERROR, PRIMARY, TEXT, TEXT_DIM, TEXT_FAINT, IconTile,
                   dialog_btn, icon_button, lbl, md_button, rgba, surface_card)
from .newproject import NewProjectScreen

CARD_H = 150
CARD_MIN_W = 340


def _short_path(path, keep=38):
    if len(path) <= keep:
        return path
    return "…" + path[-(keep - 1):]


def _fmt_date(ts):
    try:
        return time.strftime("%d/%m/%Y", time.localtime(float(ts)))
    except Exception:
        return ""


class HomeScreen(MDScreen):
    def __init__(self, app, **kw):
        MDScreen.__init__(self, name="home", **kw)
        self.app = app
        self.md_bg_color = rgba(BG)
        self._last_refresh = 0.0
        self._asked_storage = False
        self._flash_ev = None
        self._sig = None
        self._empty = True

        root = BoxLayout(orientation="vertical",
                         padding=(dp(14), dp(12), dp(14), dp(8)),
                         spacing=dp(12))
        root.add_widget(self._header())
        root.add_widget(self._actions())
        root.add_widget(self._section_header())

        self.scroll = ScrollView(bar_width=dp(4), bar_color=(1, 1, 1, 0.14),
                                 bar_inactive_color=(1, 1, 1, 0.05),
                                 scroll_type=["bars", "content"])
        self.grid = GridLayout(cols=1, spacing=dp(12), size_hint_y=None,
                               padding=(0, dp(2), 0, dp(14)))
        self.grid.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        self.scroll.add_widget(self.grid)
        self.scroll.bind(width=self._on_scroll_width)
        root.add_widget(self.scroll)

        self.flash_label = lbl("", 13, TEXT_DIM, size_hint_y=None,
                               height=dp(24))
        root.add_widget(self.flash_label)
        self.add_widget(root)

    def _safe(self, fn, *a):
        try:
            fn(*a)
        except Exception as ex:
            import traceback
            self.app.log("[erro] %s" % ex)
            self.app.log(traceback.format_exc())
            self.flash("Erro: %s" % ex, ERROR)

    def _header(self):
        card = surface_card(orientation="horizontal", size_hint_y=None,
                            height=dp(80), spacing=dp(12),
                            padding=(dp(12), dp(10), dp(10), dp(10)), radius=28)
        card.add_widget(IconTile({"glyph": "🎮", "color": "#5B6EE1"},
                                 size_px=dp(56)))
        col = BoxLayout(orientation="vertical")
        col.add_widget(lbl("LuaStudio", 22, TEXT, bold=True, shorten=True))
        col.add_widget(lbl("Seus jogos em Lua", 13, TEXT_DIM, shorten=True))
        card.add_widget(col)
        plugin_btn = icon_button(icon="puzzle-outline", size_hint=(None, None),
                                  size=(dp(48), dp(48)),
                                  pos_hint={"center_y": 0.5})
        plugin_btn.bind(on_release=lambda *_a: self._safe(self.app.open_plugin_manager))
        lock_btn = icon_button(icon="lock-outline", size_hint=(None, None),
                                size=(dp(48), dp(48)),
                                pos_hint={"center_y": 0.5})
        lock_btn.bind(on_release=lambda *_a: self._safe(self._ask_perms))
        card.add_widget(plugin_btn)
        card.add_widget(lock_btn)
        return card

    def _actions(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        height=dp(106), spacing=dp(8))
        box.add_widget(md_button("Novo projeto",
                                 lambda: self._safe(self.open_new_project),
                                 style="filled", icon="plus",
                                 size_hint_y=None, height=dp(52)))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        row.add_widget(md_button("Importar .Lsp",
                                 lambda: self._safe(self.app.open_import_lsp),
                                 style="tonal", icon="file-import-outline",
                                 size_hint_y=None, height=dp(44)))
        row.add_widget(md_button("Editor GBA",
                                 lambda: self._safe(self.app.open_gba_editor),
                                 style="tonal", icon="nintendo-game-boy",
                                 size_hint_y=None, height=dp(44)))
        box.add_widget(row)
        return box

    def _section_header(self):
        row = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(8))
        self.count_label = lbl("Seus projetos", 14, PRIMARY, bold=True,
                               size_hint_x=0.5)
        self.path_label = lbl("", 11, TEXT_FAINT, halign="right", shorten=True)
        row.add_widget(self.count_label)
        row.add_widget(self.path_label)
        return row

    def flash(self, msg, color=TEXT_DIM, seconds=5.0):
        if self._flash_ev is not None:
            self._flash_ev.cancel()
        Animation.cancel_all(self.flash_label, "opacity")
        self.flash_label.opacity = 1
        self.flash_label.text = msg
        self.flash_label.color = rgba(color) if isinstance(color, str) else color
        self._flash_ev = Clock.schedule_once(self._clear_flash, seconds)

    def _clear_flash(self, *_a):
        self._flash_ev = None
        Animation(opacity=0, d=0.25).start(self.flash_label)

    def _ask_perms(self):
        self.flash("Os projetos são salvos na pasta privada do LuaStudio.")
        self.refresh(force=True)

    def on_pre_enter(self, *_a):
        self.refresh()

    def _cols(self):
        return max(1, int(self.scroll.width // dp(CARD_MIN_W)))

    def _on_scroll_width(self, _w, _v):
        if self.grid.children and not self._empty:
            self.grid.cols = self._cols()

    def refresh(self, force=False):
        now = time.time()
        if not force and now - self._last_refresh < 0.3:
            return
        self._last_refresh = now
        try:
            entries = luaproject.list_project_entries()
            root = luaproject.projects_root()
        except Exception as ex:
            entries, root = [], ""
            self.flash("Não consegui ler os projetos: %s" % ex, ERROR)
        self.count_label.text = "Seus projetos  ·  %d" % len(entries)
        self.path_label.text = _short_path(root)
        sig = tuple((e["path"], e["name"], e["modified"], e["scripts"],
                     repr(e["icon"])) for e in entries)
        if not force and sig == self._sig and self.grid.children:
            return
        self._sig = sig
        self.grid.clear_widgets()
        self._empty = not entries
        if not entries:
            self.grid.cols = 1
            self.grid.add_widget(self._empty_state())
            return
        self.grid.cols = self._cols()
        for i, e in enumerate(entries):
            self.grid.add_widget(self._make_card(e, i))

    def _empty_state(self):
        card = surface_card(orientation="vertical", size_hint_y=None,
                            spacing=dp(10), padding=(dp(20), dp(24), dp(20), dp(24)),
                            radius=28)
        card.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        row = BoxLayout(size_hint_y=None, height=dp(72))
        row.add_widget(Widget())
        row.add_widget(IconTile({"glyph": "🎮", "color": "#5B6EE1"},
                                size_px=dp(72)))
        row.add_widget(Widget())
        card.add_widget(row)
        card.add_widget(lbl("Nenhum projeto ainda", 18, TEXT, bold=True,
                            halign="center", size_hint_y=None, height=dp(30)))
        card.add_widget(lbl("Toque em “Novo projeto” para começar.",
                            13, TEXT_DIM, halign="center", size_hint_y=None,
                            height=dp(22)))
        return card

    def _make_card(self, e, index):
        card = surface_card(orientation="vertical", size_hint_y=None,
                            height=dp(CARD_H), spacing=dp(10),
                            padding=(dp(14), dp(12), dp(14), dp(12)), radius=28)
        top = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(12))
        top.add_widget(IconTile(e["icon"], name=e["name"], base_path=e["path"],
                                size_px=dp(60)))
        info = BoxLayout(orientation="vertical")
        info.add_widget(lbl(e["name"], 17, TEXT, bold=True, shorten=True))
        n = e["scripts"]
        meta = "%d script%s" % (n, "s" if n != 1 else "")
        date = _fmt_date(e["modified"])
        if date:
            meta += "  ·  %s" % date
        if e["legacy"]:
            meta += "  ·  pasta antiga"
        info.add_widget(lbl(meta, 12, TEXT_DIM, shorten=True))
        info.add_widget(lbl(_short_path(e["path"], 44), 11, TEXT_FAINT,
                            shorten=True))
        top.add_widget(info)
        card.add_widget(top)

        path = e["path"]
        bottom = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        bottom.add_widget(md_button("Play", lambda: self._safe(self._open, path, True),
                                    style="filled", icon="play",
                                    size_hint_y=None, height=dp(44)))
        bottom.add_widget(md_button("Editar", lambda: self._safe(self._open, path, False),
                                    style="tonal", icon="pencil-outline",
                                    size_hint_y=None, height=dp(44)))
        delete_btn = icon_button(icon="delete-outline", size_hint=(None, None),
                                  size=(dp(44), dp(44)))
        delete_btn.bind(on_release=lambda *_a: self._safe(self._confirm_delete, e))
        bottom.add_widget(delete_btn)
        card.add_widget(bottom)

        card.opacity = 0
        Clock.schedule_once(lambda *_a, c=card: Animation(opacity=1, d=0.22,
                                                           t="out_quad").start(c),
                            min(index, 5) * 0.04)
        return card

    def _open(self, path, play):
        try:
            proj = luaproject.load_project(path)
        except Exception as ex:
            self.flash("Erro ao abrir o projeto: %s" % ex, ERROR)
            return
        self.app.open_project(proj, play=play)

    def _confirm_delete(self, e):
        dialog = MDDialog(
            MDDialogHeadlineText(text="Apagar projeto?"),
            MDDialogSupportingText(
                text="A pasta inteira de “%s” será apagada do dispositivo:\n%s\n\n"
                     "Isso não pode ser desfeito." % (e["name"], e["path"])),
            MDDialogButtonContainer(
                Widget(),
                dialog_btn("Cancelar", lambda: dialog.dismiss(), style="text"),
                dialog_btn("Apagar", lambda: self._do_delete(e, dialog),
                          style="filled"),
            ),
        )
        dialog.open()

    def _do_delete(self, e, dialog):
        dialog.dismiss()
        ok = luaproject.delete_project(e["path"])
        if ok:
            self.flash("Projeto “%s” apagado" % e["name"], TEXT_DIM)
        else:
            self.flash("Não consegui apagar “%s”" % e["name"], ERROR)
        self.refresh(force=True)

    def open_new_project(self):
        if self.manager is None:
            return
        if not self.manager.has_screen("new_project"):
            self.manager.add_widget(NewProjectScreen(self.app, self))
        self.manager.get_screen("new_project").reset()
        self.manager.current = "new_project"
