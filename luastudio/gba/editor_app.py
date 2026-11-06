# -*- coding: utf-8 -*-
"""Editor GBA (tela Kivy): escreve C, compila com arm-none-eabi-gcc (via Python) e gera a ROM .gba.

Pode rodar sozinho (gba_editor_main.py) ou como tela dentro do LuaStudio
(GbaEditorScreen(on_back=...)). A logica de build fica em toolchain.py (sem Kivy).
"""
import os
import re
import shutil
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from .. import filebrowser
from .. import project as luaproject
from .. import theme
from . import toolchain
from . import bridge_client


def _lbl(text, size=13, color=theme.TEXT, **kw):
    lb = Label(text=text, font_size=size, color=color, **kw)
    lb.bind(size=lambda w, _v: setattr(w, "text_size", (w.width, None)))
    return lb


def _btn(text, cb, color=theme.SURFACE_2, **kw):
    kw.setdefault("font_size", 13)
    b = theme.RoundButton(text=text, bg_color=color, **kw)
    b.bind(on_release=lambda *_a: cb())
    return b


def gba_root():
    root = os.path.join(luaproject.projects_root(), "GBA")
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root


def list_gba_projects():
    root = gba_root()
    out = []
    try:
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if os.path.isfile(os.path.join(p, toolchain.CONFIG_NAME)):
                out.append(p)
    except Exception:
        pass
    return out


class GbaEditorScreen(Screen):
    def __init__(self, on_back=None, **kw):
        Screen.__init__(self, name=kw.pop("name", "gba"), **kw)
        self.on_back = on_back
        self.project = None
        self.cfg = None
        self.cur_file = None
        self.dirty = False
        self._building = False
        self.last = None
        self.expanded_dirs = {"src", "assets"}
        self.selected_dir = "src"
        self.file_clipboard = None
        self.file_clipboard_cut = False
        self._loading_file = False
        self._undo_fallback = []

        root = BoxLayout(orientation="vertical", spacing=10, padding=10)
        # M3: app bar flutuante em card tonal
        self.bar = theme.Card(orientation="horizontal", size_hint_y=None,
                              height=58, spacing=6, padding=(10, 7))
        root.add_widget(self.bar)
        self._make_bar()

        work = BoxLayout(orientation="horizontal", spacing=10)
        self.tree_panel = theme.Card(orientation="vertical", size_hint_x=None, width=176,
                                     spacing=4, padding=(8, 8, 8, 8))
        tree_head = BoxLayout(size_hint_y=None, height=34, spacing=3)
        tree_head.add_widget(_lbl("ARQUIVOS", 11, theme.TEXT_DIM, bold=True, halign="left"))
        tree_head.add_widget(_btn("+", self.new_file_dialog, theme.ACCENT, size_hint_x=None, width=30))
        tree_head.add_widget(_btn("📁", self.new_folder_dialog, theme.SURFACE_2, size_hint_x=None, width=32))
        tree_head.add_widget(_btn("↓", self.paste_file, theme.SURFACE_2, size_hint_x=None, width=30))
        self.tree_panel.add_widget(tree_head)
        self.tree_scroll = ScrollView(bar_width=3, do_scroll_x=False)
        self.tree_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2, padding=(1, 2))
        self.tree_box.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        self.tree_scroll.add_widget(self.tree_box)
        self.tree_panel.add_widget(self.tree_scroll)
        work.add_widget(self.tree_panel)

        editor_col = theme.Card(orientation="vertical", spacing=6, padding=(10, 10, 10, 10))
        self.tabs_scroll = ScrollView(size_hint_y=None, height=34, do_scroll_y=False, bar_width=0)
        self.tabs = BoxLayout(size_hint_x=None, spacing=3)
        self.tabs.bind(minimum_width=lambda w, v: setattr(w, "width", v))
        self.tabs_scroll.add_widget(self.tabs)
        editor_col.add_widget(self.tabs_scroll)

        tools = BoxLayout(size_hint_y=None, height=36, spacing=3)
        for text, cb in (("Salvar", self.save_current), ("Desfazer", self.undo_edit),
                         ("Refazer", self.redo_edit), ("Tab +", self.indent_line),
                         ("Tab -", self.outdent_line), ("Copiar", self.copy_selection),
                         ("Colar", self.paste_clipboard), ("Selecionar", self.select_all)):
            tools.add_widget(_btn(text, cb, theme.SURFACE_2, font_size=11))
        editor_col.add_widget(tools)
        find_row = BoxLayout(size_hint_y=None, height=34, spacing=4)
        self.find_input = theme.make_input(hint_text="Buscar no arquivo...", size_hint_x=1, height=34, font_size=12)
        find_row.add_widget(self.find_input)
        find_row.add_widget(_btn("Buscar", self.find_next, theme.SURFACE_2, size_hint_x=None, width=62, font_size=11))
        editor_col.add_widget(find_row)

        self.code = TextInput(multiline=True, font_size=14, background_color=theme.MONO_BG,
                              foreground_color=theme.MONO_FG, cursor_color=theme.CURSOR,
                              background_normal="", background_active="", padding=(10, 10),
                              do_wrap=False, size_hint_y=1, write_tab=False)
        try:
            self.code.font_name = "RobotoMono-Regular"
        except Exception:
            pass
        self.code.bind(text=self._on_edit)
        editor_col.add_widget(self.code)
        work.add_widget(editor_col)
        root.add_widget(work)

        self.out_scroll = ScrollView(size_hint_y=0.25, bar_width=4)
        theme.paint_rounded(self.out_scroll, theme.SURFACE, radius=theme.SHAPE_XL)
        self.out = BoxLayout(orientation="vertical", size_hint_y=None, spacing=3, padding=(12, 10))
        self.out.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        self.out_scroll.add_widget(self.out)
        root.add_widget(self.out_scroll)

        self.status = _lbl("Nenhum projeto aberto", 12, theme.TEXT_DIM, size_hint_y=None, height=22)
        root.add_widget(self.status)
        self.add_widget(root)

    # ------------------------------------------------------------ barra
    def _make_bar(self):
        self.bar.clear_widgets()
        self.bar.add_widget(_btn("‹", self._back, size_hint_x=None, width=34))
        self.title_lbl = _lbl("GBA", 14, theme.TEXT, bold=True, halign="left", valign="middle")
        self.bar.add_widget(self.title_lbl)
        for text, cb, col, width in (("Projetos", self.open_projects, theme.SURFACE_2, 66),
                                     ("Assets", self.open_assets, theme.SURFACE_2, 54),
                                     ("Config", self.open_settings, theme.SURFACE_2, 56),
                                     ("Build", self.build_clicked, theme.PLAY, 52),
                                     ("Rodar", self.run_clicked, theme.ACCENT, 54)):
            self.bar.add_widget(_btn(text, cb, col, size_hint_x=None, width=width, font_size=11))

    def _back(self):
        self.save_current()
        if self.on_back:
            self.on_back()

    # -------------------------------------------------------- mensagens
    def log(self, msg, color=theme.TEXT_DIM):
        def add(*_a):
            lb = _lbl(str(msg), 12, color, size_hint_y=None, halign="left", valign="top")
            lb.bind(texture_size=lambda w, v: setattr(w, "height", max(18, v[1] + 2)))
            self.out.add_widget(lb)
            Clock.schedule_once(lambda *_b: setattr(self.out_scroll, "scroll_y", 0), 0.05)
        Clock.schedule_once(add, 0)

    def clear_out(self):
        self.out.clear_widgets()

    def set_status(self, text, color=theme.TEXT_DIM):
        self.status.text = text
        self.status.color = color

    # ---------------------------------------------------------- projeto
    def open_project(self, path):
        self.save_current()
        self.project = path
        self.cfg = toolchain.load_config(path)
        self.title_lbl.text = "GBA - " + os.path.basename(path)
        self.refresh_tabs()
        files = self.source_files()
        self.load_file(files[0] if files else None)
        self.clear_out()
        tc = toolchain.find_toolchain(self.cfg.get("toolchain_dir", ""))
        if tc:
            self.log("Toolchain: %s" % tc["gcc"], theme.PLAY)
        else:
            if self.cfg.get("bridge_enabled", True):
                self.log("GCC local nao encontrado. Build remoto habilitado: inicie a ponte GBA no Termux.", theme.WARN)
                self.log("Endereco da ponte: %s" % self.cfg.get("bridge_url", bridge_client.DEFAULT_BRIDGE_URL))
            else:
                self.log("arm-none-eabi-gcc NAO encontrado. Instale o devkitARM / GNU Arm Embedded e "
                         "informe a pasta bin em Config > Toolchain.", theme.WARN)
        self.set_status(path)

    def source_files(self):
        d = os.path.join(self.project, "src")
        out = []
        for base, dirs, files in os.walk(d):
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            for name in sorted(files):
                if name.endswith((".c", ".h")):
                    out.append(os.path.relpath(os.path.join(base, name), d).replace(os.sep, "/"))
        return sorted(out)

    def _project_rel(self, path):
        rel = os.path.relpath(path, self.project).replace(os.sep, "/")
        return rel

    def _safe_project_path(self, rel):
        rel = str(rel or "").replace("\\", "/").strip(" /")
        if not rel or rel.startswith("../") or "/../" in ("/" + rel + "/"):
            raise ValueError("Caminho invalido")
        root = os.path.realpath(self.project)
        full = os.path.realpath(os.path.join(root, *rel.split("/")))
        if full != root and not full.startswith(root + os.sep):
            raise ValueError("Caminho fora do projeto")
        return full

    def refresh_tabs(self):
        self.tabs.clear_widgets()
        for f in self.source_files():
            active = f == self.cur_file
            label = os.path.basename(f)
            b = _btn(label, lambda f=f: self.load_file(f), theme.ACCENT if active else theme.SURFACE_2,
                     size_hint_x=None, width=max(76, 9 * len(label) + 26), font_size=11)
            self.tabs.add_widget(b)
        self.refresh_tree()

    def refresh_tree(self):
        if not hasattr(self, "tree_box"):
            return
        self.tree_box.clear_widgets()
        if not self.project or not os.path.isdir(self.project):
            return
        ignored = {"build", "__pycache__", ".git"}
        def add_dir(abs_dir, rel_dir, depth=0):
            try:
                entries = sorted(os.listdir(abs_dir), key=lambda x: (not os.path.isdir(os.path.join(abs_dir, x)), x.lower()))
            except Exception:
                return
            for name in entries:
                if name.startswith(".") or name in ignored:
                    continue
                full = os.path.join(abs_dir, name)
                rel = (rel_dir + "/" + name).strip("/")
                is_dir = os.path.isdir(full)
                if is_dir:
                    opened = rel in self.expanded_dirs
                    label = ("▾ " if opened else "▸ ") + name
                    folder_row = BoxLayout(size_hint_y=None, height=29, spacing=2)
                    b = _btn(label, lambda r=rel: self.toggle_dir(r), theme.SURFACE_2,
                             font_size=11, halign="left")
                    b.padding = (6 + depth * 8, 4)
                    folder_row.add_widget(b)
                    folder_row.add_widget(_btn("⋮", lambda r=rel: self.folder_actions(r), theme.SURFACE_2,
                                               size_hint_x=None, width=27, font_size=12))
                    self.tree_box.add_widget(folder_row)
                    if opened:
                        add_dir(full, rel, depth + 1)
                else:
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in (".c", ".h", ".txt", ".md", ".json", ".lua", ".py", ".s", ".ld", ".asm"):
                        continue
                    active = self.cur_file == rel or (self.cur_file and self.cur_file == rel[4:] if rel.startswith("src/") else False)
                    row = BoxLayout(size_hint_y=None, height=28, spacing=2)
                    prefix = "   " * depth
                    label = prefix + ("C  " if ext == ".c" else "H  " if ext == ".h" else "·  ") + name
                    row.add_widget(_btn(label, lambda r=rel: self.load_project_file(r),
                                        theme.ACCENT if active else theme.BG,
                                        font_size=10, halign="left"))
                    row.add_widget(_btn("⋮", lambda r=rel: self.file_actions(r), theme.SURFACE_2,
                                        size_hint_x=None, width=27, font_size=12))
                    self.tree_box.add_widget(row)
        add_dir(self.project, "", 0)

    def toggle_dir(self, rel):
        self.selected_dir = rel
        if rel in self.expanded_dirs:
            self.expanded_dirs.remove(rel)
        else:
            self.expanded_dirs.add(rel)
        self.refresh_tree()

    def load_project_file(self, rel):
        try:
            full = self._safe_project_path(rel)
            if not os.path.isfile(full):
                return
            self.save_current()
            self.cur_file = rel
            self.selected_dir = os.path.dirname(rel).replace(os.sep, "/") or "src"
            self._loading_file = True
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                self.code.text = fh.read()
            self._loading_file = False
            self.dirty = False
            self.refresh_tabs()
            self.set_status(rel)
        except Exception as ex:
            self._loading_file = False
            self.log("Nao foi possivel abrir: %s" % ex, theme.STOP)

    def load_file(self, name):
        if not name:
            self.save_current()
            self.cur_file = None
            self._loading_file = True
            self.code.text = ""
            self._loading_file = False
            self.dirty = False
            self.refresh_tabs()
            return
        rel = name if name.startswith("src/") else "src/" + name
        self.load_project_file(rel)

    def _on_edit(self, *_a):
        if not self._loading_file:
            self.dirty = True
            if self.cur_file:
                self.set_status("● " + self.cur_file + " (nao salvo)", theme.WARN)

    def save_current(self):
        if self.project and self.cur_file and self.dirty:
            try:
                full = self._safe_project_path(self.cur_file)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8", newline="") as fh:
                    fh.write(self.code.text)
                self.dirty = False
                self.set_status(self.cur_file + " - salvo", theme.PLAY)
            except Exception as ex:
                self.log("Erro ao salvar: %s" % ex, theme.STOP)

    def goto_line(self, fname, line):
        if not fname:
            return
        rel = fname.replace("\\", "/")
        if not rel.startswith("src/"):
            rel = "src/" + rel
        if rel != self.cur_file:
            self.load_project_file(rel)
        if rel == self.cur_file and line > 0:
            self.code.cursor = (0, line - 1)
            self.code.focus = True

    def undo_edit(self):
        try:
            self.code.do_undo()
        except Exception:
            self.log("Desfazer nao esta disponivel neste campo.", theme.WARN)

    def redo_edit(self):
        try:
            self.code.do_redo()
        except Exception:
            self.log("Refazer nao esta disponivel neste campo.", theme.WARN)

    def indent_line(self):
        lines = self.code.text.splitlines(True)
        if not lines:
            return
        row = max(0, self.code.cursor[1])
        if row < len(lines):
            lines[row] = "    " + lines[row]
            self.code.text = "".join(lines)
            self.code.cursor = (self.code.cursor[0] + 4, row)
            self.code.focus = True

    def outdent_line(self):
        lines = self.code.text.splitlines(True)
        if not lines:
            return
        row = max(0, self.code.cursor[1])
        if row < len(lines):
            old = lines[row]
            removed = len(old) - len(old.lstrip(" 	"))
            cut = min(4, removed)
            lines[row] = old[cut:]
            self.code.text = "".join(lines)
            self.code.cursor = (max(0, self.code.cursor[0] - cut), row)
            self.code.focus = True

    def copy_selection(self):
        try:
            if self.code.selection_text:
                Clipboard.copy(self.code.selection_text)
        except Exception:
            pass

    def paste_clipboard(self):
        try:
            self.code.insert_text(Clipboard.paste())
            self.code.focus = True
        except Exception:
            pass

    def select_all(self):
        self.code.select_all()
        self.code.focus = True

    def find_next(self):
        needle = self.find_input.text
        if not needle:
            return
        text = self.code.text
        start = self.code.cursor_index()
        pos = text.find(needle, start)
        if pos < 0:
            pos = text.find(needle, 0)
        if pos >= 0:
            self.code.select_text(pos, pos + len(needle))
            self.code.focus = True
        else:
            self.log("Texto nao encontrado: %s" % needle, theme.WARN)

    def _name_popup(self, title, hint, callback, default=""):
        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        pop = theme.styled_popup(title, box, size_hint=(0.9, 0.36))
        ti = theme.make_input(text=default, hint_text=hint, size_hint_y=None, height=46)
        box.add_widget(ti)
        row = BoxLayout(size_hint_y=None, height=44, spacing=8)
        row.add_widget(_btn("Cancelar", pop.dismiss))
        def accept():
            try:
                callback(ti.text.strip())
                pop.dismiss()
            except Exception as ex:
                self.log(str(ex), theme.STOP)
        row.add_widget(_btn("Confirmar", accept, theme.ACCENT))
        box.add_widget(row)
        pop.open()

    def _current_folder(self):
        if self.selected_dir:
            try:
                if os.path.isdir(self._safe_project_path(self.selected_dir)):
                    return self.selected_dir
            except Exception:
                pass
        if self.cur_file:
            return os.path.dirname(self.cur_file).replace("\\", "/")
        return "src"

    def new_folder_dialog(self):
        if not self.project:
            return
        def create(name):
            name = re.sub(r"[^\w .-]", "_", name).strip(" .")
            if not name:
                raise ValueError("Digite um nome para a pasta")
            rel = (self._current_folder() + "/" + name).strip("/")
            full = self._safe_project_path(rel)
            os.makedirs(full, exist_ok=False)
            self.expanded_dirs.add(os.path.dirname(rel))
            self.refresh_tree()
            self.log("Pasta criada: " + rel, theme.PLAY)
        self._name_popup("Nova pasta", "nome da pasta", create)

    def file_actions(self, rel):
        box = BoxLayout(orientation="vertical", spacing=5, padding=9)
        pop = theme.styled_popup(os.path.basename(rel), box, size_hint=(0.88, 0.72))
        def action(label, fn):
            box.add_widget(_btn(label, lambda: (pop.dismiss(), fn()), theme.SURFACE_2,
                                size_hint_y=None, height=40))
        action("Abrir", lambda: self.load_project_file(rel))
        action("Renomear", lambda: self.rename_path(rel))
        action("Duplicar", lambda: self.duplicate_path(rel))
        action("Copiar", lambda: self.set_file_clipboard(rel, False))
        action("Recortar / mover", lambda: self.set_file_clipboard(rel, True))
        action("Colar nesta pasta", lambda: self.paste_file(rel))
        action("Excluir", lambda: self.confirm_delete(rel))
        box.add_widget(_btn("Fechar", pop.dismiss, size_hint_y=None, height=38))
        pop.open()

    def folder_actions(self, rel):
        box = BoxLayout(orientation="vertical", spacing=5, padding=9)
        pop = theme.styled_popup("Pasta: " + os.path.basename(rel), box, size_hint=(0.88, 0.62))
        def action(label, fn):
            box.add_widget(_btn(label, lambda: (pop.dismiss(), fn()), theme.SURFACE_2,
                                size_hint_y=None, height=40))
        action("Abrir / selecionar pasta", lambda: self.select_folder(rel))
        action("Nova pasta aqui", lambda: self.create_folder_in(rel))
        action("Renomear", lambda: self.rename_path(rel))
        action("Duplicar pasta", lambda: self.duplicate_path(rel))
        action("Colar nesta pasta", lambda: self.paste_file(rel))
        action("Excluir pasta", lambda: self.confirm_delete(rel))
        box.add_widget(_btn("Fechar", pop.dismiss, size_hint_y=None, height=38))
        pop.open()

    def select_folder(self, rel):
        self.selected_dir = rel
        self.expanded_dirs.add(rel)
        self.refresh_tree()
        self.set_status("Pasta selecionada: " + rel)

    def create_folder_in(self, parent_rel):
        def create(name):
            name = re.sub(r"[^\w .-]", "_", name).strip(" .")
            if not name:
                raise ValueError("Digite um nome para a pasta")
            rel = parent_rel.rstrip("/") + "/" + name
            os.makedirs(self._safe_project_path(rel), exist_ok=False)
            self.selected_dir = rel
            self.expanded_dirs.add(parent_rel)
            self.expanded_dirs.add(rel)
            self.refresh_tree()
        self._name_popup("Nova pasta", "nome da pasta", create)

    def set_file_clipboard(self, rel, cut=False):
        self.file_clipboard = rel
        self.file_clipboard_cut = bool(cut)
        self.log(("Recortado: " if cut else "Copiado: ") + rel, theme.PLAY)

    def paste_file(self, target_rel=None):
        if not self.file_clipboard:
            return self.log("Nenhum arquivo copiado.", theme.WARN)
        src = self._safe_project_path(self.file_clipboard)
        if target_rel:
            target = self._safe_project_path(target_rel)
            dest_dir = target if os.path.isdir(target) else os.path.dirname(target)
        else:
            dest_dir = self._safe_project_path(self._current_folder())
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.abspath(src) == os.path.abspath(dest):
            stem, ext = os.path.splitext(os.path.basename(src))
            i = 2
            while os.path.exists(os.path.join(dest_dir, "%s_copy%d%s" % (stem, i, ext))):
                i += 1
            dest = os.path.join(dest_dir, "%s_copy%d%s" % (stem, i, ext))
        elif os.path.exists(dest):
            stem, ext = os.path.splitext(os.path.basename(src))
            i = 2
            while os.path.exists(os.path.join(dest_dir, "%s_copy%d%s" % (stem, i, ext))):
                i += 1
            dest = os.path.join(dest_dir, "%s_copy%d%s" % (stem, i, ext))
        if self.file_clipboard_cut:
            shutil.move(src, dest)
            if self.cur_file == self.file_clipboard:
                self.cur_file = None
                self.code.text = ""
                self.dirty = False
        else:
            shutil.copy2(src, dest)
        self.file_clipboard = None
        self.file_clipboard_cut = False
        self.refresh_tabs()
        self.log("Arquivo colado: " + self._project_rel(dest), theme.PLAY)

    def rename_path(self, rel):
        def rename(new_name):
            new_name = re.sub(r"[^\w .-]", "_", new_name).strip(" .")
            if not new_name:
                raise ValueError("Nome invalido")
            old = self._safe_project_path(rel)
            dest = os.path.join(os.path.dirname(old), new_name)
            if os.path.exists(dest):
                raise ValueError("Ja existe um arquivo/pasta com esse nome")
            self.save_current()
            os.rename(old, dest)
            old_rel, new_rel = rel, self._project_rel(dest)
            if self.cur_file == old_rel:
                self.cur_file = new_rel
            elif self.cur_file and self.cur_file.startswith(old_rel.rstrip("/") + "/"):
                self.cur_file = new_rel.rstrip("/") + self.cur_file[len(old_rel.rstrip("/")):]
            if self.selected_dir == old_rel:
                self.selected_dir = new_rel
            elif self.selected_dir.startswith(old_rel.rstrip("/") + "/"):
                self.selected_dir = new_rel.rstrip("/") + self.selected_dir[len(old_rel.rstrip("/")):]
            self.refresh_tabs()
            self.log("Renomeado para " + new_rel, theme.PLAY)
        self._name_popup("Renomear", "novo nome", rename, os.path.basename(rel))

    def duplicate_path(self, rel):
        src = self._safe_project_path(rel)
        stem, ext = os.path.splitext(os.path.basename(src))
        i = 2
        dest = os.path.join(os.path.dirname(src), "%s_copy%d%s" % (stem, i, ext))
        while os.path.exists(dest):
            i += 1
            dest = os.path.join(os.path.dirname(src), "%s_copy%d%s" % (stem, i, ext))
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        self.refresh_tabs()
        self.log("Duplicado: " + self._project_rel(dest), theme.PLAY)

    def confirm_delete(self, rel):
        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        pop = theme.styled_popup("Excluir?", box, size_hint=(0.88, 0.32))
        box.add_widget(_lbl("Excluir permanentemente %s?" % rel, 13, theme.TEXT))
        row = BoxLayout(size_hint_y=None, height=44, spacing=8)
        row.add_widget(_btn("Cancelar", pop.dismiss))
        def delete():
            try:
                self.save_current()
                full = self._safe_project_path(rel)
                if os.path.isdir(full):
                    shutil.rmtree(full)
                elif os.path.exists(full):
                    os.remove(full)
                if self.cur_file == rel or (self.cur_file and self.cur_file.startswith(rel.rstrip("/") + "/")):
                    self.cur_file = None
                    self.code.text = ""
                    self.dirty = False
                pop.dismiss()
                self.refresh_tabs()
                self.log("Excluido: " + rel, theme.PLAY)
            except Exception as ex:
                self.log("Falha ao excluir: %s" % ex, theme.STOP)
        row.add_widget(_btn("Excluir", delete, theme.STOP))
        box.add_widget(row)
        pop.open()

    def new_file_dialog(self):
        if not self.project:
            return
        def create(name):
            name = re.sub(r"[^\w .-]", "_", name).strip(" .")
            if not name:
                raise ValueError("Digite um nome de arquivo")
            if not os.path.splitext(name)[1]:
                name += ".c"
            rel = (self._current_folder() + "/" + name).strip("/")
            full = self._safe_project_path(rel)
            if os.path.exists(full):
                raise ValueError("Esse arquivo ja existe")
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                if name.endswith(".c"):
                    fh.write('#include "gba.h"\n\nint main(void)\n{\n    gba_init();\n    gfx_init(3);\n\n    while (1) {\n        vsync();\n        key_poll();\n    }\n}\n')
                elif name.endswith(".h"):
                    guard = re.sub(r"\W", "_", name.upper())
                    fh.write("#ifndef %s\n#define %s\n\n#endif\n" % (guard, guard))
            self.load_project_file(rel)
            self.log("Arquivo criado: " + rel, theme.PLAY)
        self._name_popup("Novo arquivo", "ex.: player.c ou config.h", create)

    # ---------------------------------------------------------- projetos
    def open_projects(self):
        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        pop = theme.styled_popup("Projetos GBA", box, size_hint=(0.92, 0.85))
        name_in = theme.make_input(hint_text="nome do novo projeto", size_hint_y=None, height=48)
        box.add_widget(name_in)
        spin = Spinner(text="draw", values=list(toolchain.TEMPLATES.keys()), size_hint_y=None, height=44,
                       background_normal="", background_color=theme.SURFACE_2, color=theme.TEXT)
        box.add_widget(spin)

        def create():
            n = re.sub(r"[^\w\- ]", "", name_in.text.strip()) or "MeuJogo"
            path = os.path.join(gba_root(), n)
            toolchain.create_project(path, spin.text)
            pop.dismiss()
            self.open_project(path)
        box.add_widget(_btn("Criar projeto", create, theme.ACCENT, size_hint_y=None, height=46))
        sv = ScrollView()
        lst = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        lst.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        for p in list_gba_projects():
            lst.add_widget(_btn(os.path.basename(p), lambda p=p: (pop.dismiss(), self.open_project(p)),
                                size_hint_y=None, height=44))
        sv.add_widget(lst)
        box.add_widget(sv)
        box.add_widget(_btn("Fechar", pop.dismiss, size_hint_y=None, height=42))
        pop.open()

    # ------------------------------------------------------------ config
    def open_settings(self):
        if not self.project:
            return self.log("Abra um projeto primeiro.", theme.WARN)
        cfg = self.cfg
        box = BoxLayout(orientation="vertical", spacing=6, padding=10)
        pop = theme.styled_popup("Configuracao GBA", box, size_hint=(0.94, 0.92))
        sv = ScrollView()
        form = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        form.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        fields = {}

        def text_field(key, label, hint=""):
            form.add_widget(_lbl(label, 12, theme.TEXT_DIM, size_hint_y=None, height=20))
            ti = theme.make_input(text=str(cfg.get(key, "")), hint_text=hint, size_hint_y=None, height=44,
                                  font_size=14, padding=(10, 10))
            form.add_widget(ti)
            fields[key] = ti

        def spin_field(key, label, values):
            form.add_widget(_lbl(label, 12, theme.TEXT_DIM, size_hint_y=None, height=20))
            sp = Spinner(text=str(cfg.get(key)), values=[str(v) for v in values], size_hint_y=None,
                         height=42, background_normal="", background_color=theme.SURFACE_2, color=theme.TEXT)
            form.add_widget(sp)
            fields[key] = sp

        text_field("title", "Titulo da ROM (ate 12 caracteres)")
        text_field("game_code", "Codigo do jogo (4 letras)")
        spin_field("mode", "Modo de video dos assets (3 = 15 bits, 4 = paleta, 0 = tiles)", [3, 4, 0])
        spin_field("opt", "Otimizacao", ["-O2", "-O3", "-Os"])
        spin_field("lto", "LTO (menor/mais rapido, build mais lento)", [False, True])
        spin_field("allow_float", "Permitir float/double (avisa em vez de erro)", [False, True])
        spin_field("thumb", "Codigo da ROM em Thumb", [True, False])
        text_field("toolchain_dir", "Pasta bin do arm-none-eabi-gcc", "/opt/devkitpro/devkitARM/bin")
        spin_field("bridge_enabled", "Usar compilador Termux/Debian se GCC local nao existir", [True, False])
        text_field("bridge_url", "Endereco da ponte local", "http://127.0.0.1:8765")
        text_field("emulator", "Emulador (mGBA etc.) para o botao Rodar")
        sv.add_widget(form)
        box.add_widget(sv)
        row = BoxLayout(size_hint_y=None, height=46, spacing=8)

        def save():
            for k, w in fields.items():
                v = w.text
                if k in ("mode",):
                    v = int(v)
                elif k in ("lto", "allow_float", "thumb", "bridge_enabled"):
                    v = v == "True"
                cfg[k] = v
            toolchain.save_config(self.project, cfg)
            pop.dismiss()
            self.log("Configuracao salva.", theme.PLAY)
        row.add_widget(_btn("Cancelar", pop.dismiss))
        row.add_widget(_btn("Salvar", save, theme.ACCENT))
        box.add_widget(row)
        pop.open()

    # ------------------------------------------------------------ assets
    ASSET_KINDS = ["Sprite 4bpp", "Tileset + mapa", "Imagem tela cheia", "Efeito (WAV)", "Musica (MIDI)"]

    def open_assets(self):
        if not self.project:
            return self.log("Abra um projeto primeiro.", theme.WARN)
        filebrowser.open_picker(
            "Importar asset (PNG / WAV / MID)", mode="file", start=self.project,
            extensions=[".png", ".wav", ".mid", ".midi"], on_select=self._asset_picked)

    def _asset_picked(self, path):
        ext = os.path.splitext(path)[1].lower()
        stem = re.sub(r"[^\w]", "_", os.path.splitext(os.path.basename(path))[0]).lower()
        kinds = {".png": self.ASSET_KINDS[:3], ".wav": [self.ASSET_KINDS[3]],
                 ".mid": [self.ASSET_KINDS[4]], ".midi": [self.ASSET_KINDS[4]]}[ext]
        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        pop = theme.styled_popup("Como usar %s?" % os.path.basename(path), box, size_hint=(0.92, 0.5))
        sp = Spinner(text=kinds[0], values=kinds, size_hint_y=None, height=44, background_normal="",
                     background_color=theme.SURFACE_2, color=theme.TEXT)
        box.add_widget(sp)
        size_in = theme.make_input(text="16x16", hint_text="tamanho do quadro (sprites)", size_hint_y=None, height=44)
        box.add_widget(size_in)

        def ok():
            k = sp.text
            if k == self.ASSET_KINDS[0]:
                m = re.match(r"^(\d+)\s*x\s*(\d+)$", size_in.text.strip())
                dest = "spr_%s_%sx%s.png" % (stem, m.group(1), m.group(2)) if m else "spr_%s_16x16.png" % stem
            elif k == self.ASSET_KINDS[1]:
                dest = "bg_%s.png" % stem
            elif k == self.ASSET_KINDS[2]:
                dest = "img_%s.png" % stem
            else:
                dest = stem + (".wav" if ext == ".wav" else ".mid")
            os.makedirs(os.path.join(self.project, "assets"), exist_ok=True)
            shutil.copyfile(path, os.path.join(self.project, "assets", dest))
            pop.dismiss()
            self.log("Asset importado: assets/%s (vira dado C no proximo Build; veja build/assets.h)" % dest, theme.PLAY)
        box.add_widget(_btn("Importar", ok, theme.ACCENT, size_hint_y=None, height=46))
        box.add_widget(_btn("Cancelar", pop.dismiss, size_hint_y=None, height=42))
        pop.open()

    # ------------------------------------------------------------- build
    def build_clicked(self):
        if not self.project:
            return self.log("Abra um projeto primeiro.", theme.WARN)
        if self._building:
            return
        self.save_current()
        self._building = True
        self.clear_out()
        self.set_status("compilando...", theme.WARN)
        threading.Thread(target=self._build_thread, daemon=True).start()

    def _build_thread(self):
        try:
            cfg = toolchain.load_config(self.project)
            local_tools = toolchain.find_toolchain(cfg.get("toolchain_dir", ""))
            if local_tools:
                self.log("Build local: %s" % local_tools["gcc"])
                res = toolchain.build(self.project, log=lambda m: self.log(m), tools=local_tools)
            elif cfg.get("bridge_enabled", True):
                self.log("Solicitando compilacao ao Termux/Debian...")
                res = bridge_client.build_via_bridge(
                    self.project,
                    log=lambda m: self.log(m),
                    url=cfg.get("bridge_url", bridge_client.DEFAULT_BRIDGE_URL))
            else:
                res = toolchain.build(self.project, log=lambda m: self.log(m))
            err = None
        except Exception as ex:  # BuildError, falha da ponte ou falha inesperada
            res, err = None, ex
        Clock.schedule_once(lambda *_a: self._build_done(res, err), 0)

    def _build_done(self, res, err):
        self._building = False
        self.last = res
        if err is not None:
            self.set_status("erro", theme.STOP)
            self.log("ERRO: %s" % err, theme.STOP)
            return
        for f, line, col, sev, msg in res.diagnostics:
            color = theme.STOP if sev == "error" else theme.WARN
            if line and f and f not in ("link", "memoria"):
                b = _btn("%s:%d  %s" % (f, line, msg), lambda f=f, line=line: self.goto_line(f, line),
                         theme.SURFACE, size_hint_y=None, height=34, halign="left", font_size=12)
                b.color = color
                b.bind(size=lambda w, _v: setattr(w, "text_size", (w.width - 12, None)))
                self.out.add_widget(b)
            else:
                self.log("%s: %s" % (sev, msg), color)
        if res.ok:
            s = res.sizes
            mem = ""
            if s:
                mem = "  ROM %dKB  IWRAM %d/32768  EWRAM %d/262144" % (s["rom"] // 1024, s["iwram"], s["ewram"])
            self.set_status("OK %s%s" % (os.path.basename(res.rom), mem), theme.PLAY)
        else:
            self.set_status("falhou: %d erro(s)" % len(res.errors()), theme.STOP)

    def run_clicked(self):
        if not self.last or not self.last.ok:
            return self.log("Compile primeiro (Build).", theme.WARN)
        try:
            toolchain.run_emulator(self.last.rom, self.cfg.get("emulator", ""))
            self.log("Emulador iniciado.", theme.PLAY)
        except Exception as ex:
            self.log("ROM em %s  (%s)" % (self.last.rom, ex), theme.WARN)


class GbaEditorApp(App):
    title = "LuaStudio - Editor GBA"

    def build(self):
        try:
            Window.clearcolor = theme.BG
        except Exception:
            pass
        self.screen = GbaEditorScreen()
        Clock.schedule_once(lambda *_a: self._first(), 0.2)
        return self.screen

    def _first(self):
        projs = list_gba_projects()
        if projs:
            self.screen.open_project(projs[0])
        else:
            self.screen.open_projects()


def main():
    GbaEditorApp().run()
