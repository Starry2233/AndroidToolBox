# -*- coding: utf-8 -*-

"""AndroidToolkit settings UI - GNU nano style."""

import time
import json
import os
from typing import Dict, Any, List, Optional

from prompt_toolkit import Application, print_formatted_text, HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.shortcuts import clear, set_title
from prompt_toolkit.styles import Style
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.application import get_app


DEFAULT_SETTINGS = {
    "lang": "default",
    "skip_platform_check": False,
    "auto_clear": True,
    "logo_enabled": True,
    "timeout_adb": 0.3,
}

LANG_OPTIONS = ["default", "zh", "en"]

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

style = Style.from_dict({
    "top-bar": "fg:#ffffff bg:#3B78FF",
    "title": "fg:#ffffff bg:#3B78FF bold",
    "content": "fg:#e6edf3 bg:#0c1118",
    "key-hint": "fg:#3B78FF bg:#0c1118",
    "selected": "fg:#0c1118 bg:#67e0c2",
    "editing": "fg:#0c1118 bg:#f4a261",
    "option": "fg:#e6edf3",
    "option-selected": "fg:#0c1118 bg:#8ab4f8 bold",
    "cursor": "fg:#0c1118 bg:#e6edf3",
    "on": "fg:#7ad1a8",
    "off": "fg:#ff7b7b",
})

SETTING_LABELS = {
    "lang": ("语言 / Language", LANG_OPTIONS),
    "skip_platform_check": ("跳过平台检查 / Skip platform check", ""),
    "auto_clear": ("自动清屏 / Auto clear screen", ""),
    "logo_enabled": ("显示Logo / Show logo", ""),
    "timeout_adb": ("ADB超时(秒) / ADB timeout (s)", ""),
}


def load_settings() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**DEFAULT_SETTINGS, **cfg}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class SettingsControl(FormattedTextControl):
    def __init__(self, render_fn, handler):
        super().__init__(render_fn, focusable=True, show_cursor=False)
        self._handler = handler

    def mouse_handler(self, mouse_event):
        return self._handler(mouse_event)


class SettingsUI:
    def __init__(self):
        self.cfg = load_settings()
        self.keys = list(self.cfg.keys())
        self.selected = 0
        self.editing = False
        self.edit_idx = 0
        self.input_buffer = ""
        self.edit_type = None
        self._row_map = []
        self.last_click = {"idx": None, "t": 0.0}

    def _build_row_map(self):
        self._row_map = []
        for i, key in enumerate(self.keys):
            val = self.cfg[key]
            _, opts = SETTING_LABELS.get(key, (key, ""))
            if isinstance(val, bool):
                self._row_map.append(("main", i, -1))
                self._row_map.append(("value", i, -1))
            elif isinstance(opts, list) and len(opts) > 0:
                self._row_map.append(("main", i, -1))
                if self.editing and i == self.selected:
                    for j in range(len(opts)):
                        self._row_map.append(("option", i, j))
                else:
                    self._row_map.append(("value", i, -1))
            elif isinstance(val, (int, float)):
                self._row_map.append(("main", i, -1))
                self._row_map.append(("value", i, -1))
            else:
                self._row_map.append(("main", i, -1))
                self._row_map.append(("value", i, -1))

    def _get_top(self):
        title = "  AndroidToolkit Settings"
        return [("class:top-bar", " " * 78), ("class:title", title), ("class:top-bar", " " * 40)]

    def _get_content(self):
        self._build_row_map()
        lines = []
        for i, key in enumerate(self.keys):
            val = self.cfg[key]
            label, opts = SETTING_LABELS.get(key, (key, ""))
            prefix = "> " if i == self.selected else "  "
            cur_cls = "class:editing" if self.editing and i == self.selected else ("class:selected" if i == self.selected else "")

            if isinstance(val, bool):
                display = f"[{'ON' if val else 'OFF'}]"
                val_cls = "class:on" if val else "class:off"
                lines.append((cur_cls, f"{prefix}{label}\n"))
                lines.append((val_cls, f"   {display}\n"))
            elif isinstance(opts, list) and len(opts) > 0:
                lines.append((cur_cls, f"{prefix}{label}\n"))
                if self.editing and i == self.selected:
                    for j, opt in enumerate(opts):
                        is_sel = j == self.edit_idx
                        cls = "class:option-selected" if is_sel else "class:option"
                        lines.append((cls, f"   {'> ' if is_sel else '  '}{opt}\n"))
                else:
                    lines.append(("class:content", f"   [{val}]\n"))
            elif isinstance(val, (int, float)):
                lines.append((cur_cls, f"{prefix}{label}\n"))
                if self.editing and i == self.selected:
                    lines.append(("class:editing", f"   [{self.input_buffer}]\n"))
                else:
                    lines.append(("class:content", f"   [{val}]\n"))
            else:
                lines.append((cur_cls, f"{prefix}{label}\n"))
                lines.append(("class:content", f"   [{val}]\n"))

            lines.append(("", "\n"))

        return lines

    def _get_bottom(self):
        if self.editing:
            if self.edit_type == "options":
                return [
                    ("class:key-hint", " Enter "),
                    ("", "Confirm"),
                    ("class:key-hint", " Esc "),
                    ("", "Cancel"),
                    ("class:key-hint", " ↑↓ "),
                    ("", "Select"),
                ]
            elif self.edit_type == "numeric":
                return [
                    ("class:key-hint", " Enter "),
                    ("", "Confirm"),
                    ("class:key-hint", " Esc "),
                    ("", "Cancel"),
                    ("class:key-hint", " ↑↓ "),
                    ("", "+/-1"),
                    ("class:key-hint", " 0-9. "),
                    ("", "Input"),
                ]
        return [
            ("class:key-hint", " ^O "),
            ("", "Save"),
            ("class:key-hint", " Space "),
            ("", "Edit"),
            ("class:key-hint", " ↑↓ "),
            ("", "Navigate"),
        ]

    def _render(self):
        return HSplit([
            Window(content=SettingsControl(self._get_top, self._mouse_handler), height=1, style="class:top-bar"),
            Window(content=SettingsControl(self._get_content, self._mouse_handler), width=Dimension(min=78), style="class:content"),
            Window(content=SettingsControl(self._get_bottom, self._mouse_handler), height=1, style="class:key-hint"),
        ])

    def _mouse_handler(self, mouse_event):
        if mouse_event.event_type != MouseEventType.MOUSE_UP:
            return NotImplemented

        y = mouse_event.position.y

        if y == 0:
            return None

        content_y = y - 1
        if content_y < 0 or content_y >= len(self._row_map):
            return None

        row_type, row_idx, sub_idx = self._row_map[content_y]

        now = time.monotonic()
        if row_type == "main" or row_type == "value":
            click_key_idx = row_idx
            if click_key_idx == self.last_click["idx"] and (now - self.last_click["t"]) <= 0.5:
                self.selected = click_key_idx
                self._enter_edit_mode()
            else:
                self.selected = click_key_idx
            self.last_click["idx"] = click_key_idx
            self.last_click["t"] = now
        elif row_type == "option":
            self.edit_idx = sub_idx

        get_app().invalidate()
        return None

    def _enter_edit_mode(self):
        key = self.keys[self.selected]
        val = self.cfg[key]
        _, opts = SETTING_LABELS.get(key, (key, ""))
        if isinstance(opts, list) and len(opts) > 0:
            self.edit_type = "options"
            self.editing = True
            try:
                self.edit_idx = opts.index(val)
            except ValueError:
                self.edit_idx = 0
        elif isinstance(val, bool):
            self.cfg[key] = not val
        elif isinstance(val, (int, float)):
            self.edit_type = "numeric"
            self.editing = True
            self.input_buffer = str(val)

    def _exit_edit_mode(self, confirm: bool):
        if confirm:
            key = self.keys[self.selected]
            _, opts = SETTING_LABELS.get(key, (key, ""))
            if self.edit_type == "options" and isinstance(opts, list):
                self.cfg[key] = opts[self.edit_idx]
            elif self.edit_type == "numeric":
                try:
                    if isinstance(self.cfg[key], float):
                        self.cfg[key] = float(self.input_buffer)
                    else:
                        self.cfg[key] = int(self.input_buffer)
                except ValueError:
                    pass
        self.editing = False
        self.input_buffer = ""

    def run(self):
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            if self.editing:
                if self.edit_type == "options":
                    opts = SETTING_LABELS.get(self.keys[self.selected], ("", []))[1]
                    if self.edit_idx > 0:
                        self.edit_idx -= 1
                elif self.edit_type == "numeric":
                    try:
                        v = float(self.input_buffer)
                        if isinstance(self.cfg[self.keys[self.selected]], int):
                            v += 1
                        else:
                            v += 0.1
                        self.input_buffer = str(round(v, 4))
                    except ValueError:
                        pass
            else:
                if self.selected > 0:
                    self.selected -= 1

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            if self.editing:
                if self.edit_type == "options":
                    opts = SETTING_LABELS.get(self.keys[self.selected], ("", []))[1]
                    if self.edit_idx < len(opts) - 1:
                        self.edit_idx += 1
                elif self.edit_type == "numeric":
                    try:
                        v = float(self.input_buffer)
                        if isinstance(self.cfg[self.keys[self.selected]], int):
                            v -= 1
                        else:
                            v -= 0.1
                        self.input_buffer = str(round(v, 4))
                    except ValueError:
                        pass
            else:
                if self.selected < len(self.keys) - 1:
                    self.selected += 1

        @kb.add("space")
        def _edit(event):
            if not self.editing:
                self._enter_edit_mode()

        @kb.add("backspace")
        def _backspace(event):
            if self.editing and self.edit_type == "numeric":
                self.input_buffer = self.input_buffer[:-1]

        @kb.add("enter")
        def _confirm(event):
            if self.editing:
                self._exit_edit_mode(confirm=True)
            else:
                save_settings(self.cfg)
                print_formatted_text(HTML("<green>Settings saved.</green>"))

        @kb.add("escape")
        def _cancel(event):
            if self.editing:
                self._exit_edit_mode(confirm=False)

        @kb.add("c-o")
        def _save(event):
            if not self.editing:
                save_settings(self.cfg)
                print_formatted_text(HTML("<green>Settings saved.</green>"))

        @kb.add("0")
        @kb.add("1")
        @kb.add("2")
        @kb.add("3")
        @kb.add("4")
        @kb.add("5")
        @kb.add("6")
        @kb.add("7")
        @kb.add("8")
        @kb.add("9")
        @kb.add(".")
        def _digit(event):
            if self.editing and self.edit_type == "numeric":
                self.input_buffer += event.data

        @kb.add("c-x")
        def _exit(event):
            # Auto save on exit if not in editing mode, otherwise just exit without saving
            if not self.editing:
                save_settings(self.cfg)
                print_formatted_text(HTML("<green>Settings saved.</green>"))
            event.app.exit(result="exit")

        set_title("AndroidToolkit Settings")
        clear()

        app = Application(
            layout=Layout(self._render(), focused_element=None),
            key_bindings=kb,
            full_screen=True,
            style=style,
            mouse_support=True,
        )

        app.run()
        clear()


if __name__ == "__main__":
    SettingsUI().run()
