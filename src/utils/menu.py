import time
from typing import Iterable, Optional, Tuple, Any, List
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.application import Application
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.mouse_events import MouseEventType, MouseButton
from prompt_toolkit.application import get_app


style = Style.from_dict({
    "yellow": "fg:#f1c40f",
    "red": "fg:#ff7b7b",
    "orange": "fg:#f4a261",
    "info": "fg:#3B78FF",
    "black": "fg:#0c1118",
    "cyan": "fg:#67e0c2",
    "green": "fg:#7ad1a8",
    "blue": "fg:#8ab4f8",
    "magenta": "fg:#c7a0ff",
    "white": "fg:#e6edf3",
    "reset": "",
    "number": "bold",
    "selected-option": "fg:#e6edf3 bold underline",
})


class Option:
    def __init__(self, value, label):
        self.value = value
        self.label = label


def menu_choice(
    message: str,
    options: Iterable[Tuple[Any, str]],
    default: Optional[str] = None,
    style_override: Optional[Style] = None,
    extra_bindings: Optional[KeyBindings] = None,
    header_text: Optional[str] = None,
    header_click_callback=None,
):
    option_list: List[Tuple[Any, str]] = list(options)
    if not option_list:
        raise ValueError("menu_choice requires at least one option")

    selected_index = 0
    header_rows = 1 if header_text else 0

    if default is not None:
        for idx, (value, _label) in enumerate(option_list):
            if value == default:
                selected_index = idx
                break

    kb = KeyBindings()

    @kb.add("enter", eager=True)
    @kb.add(" ", eager=True)
    def _(event):
        idx = selected_index or 0
        event.app.exit(result=option_list[idx][0])

    digit_buf = {"text": "", "t": 0.0}

    def _select_by_number(event, digit: str) -> None:
        now = time.monotonic()
        if now - digit_buf["t"] > 0.2:
            digit_buf["text"] = ""
        digit_buf["text"] += digit
        digit_buf["t"] = now
        try:
            idx = int(digit_buf["text"]) - 1
        except ValueError:
            return
        if 0 <= idx < len(option_list):
            _set_selection(idx, event.app)

    for d in "0123456789":
        @kb.add(d, eager=True)
        def _(event, _d=d):
            _select_by_number(event, _d)

    def _clamp(idx: int) -> int:
        count = len(option_list)
        return max(0, min(count - 1, idx))

    def _set_selection(idx: int, app):
        nonlocal selected_index
        selected_index = _clamp(idx)
        app.invalidate()

    @kb.add("up")
    @kb.add("k")
    def _(event):
        _set_selection(selected_index - 1, event.app)

    @kb.add("down")
    @kb.add("j")
    def _(event):
        _set_selection(selected_index + 1, event.app)

    last_click = {"idx": None, "t": 0.0}

    def mouse_handler(mouse_event):
        nonlocal selected_index
        if mouse_event.event_type != MouseEventType.MOUSE_UP:
            return NotImplemented

        y = mouse_event.position.y
        if header_rows and y == 0:
            if header_click_callback:
                header_click_callback()
            return None

        if header_rows:
            y -= header_rows
        if 0 <= y < len(option_list):
            _set_selection(y, get_app())

        if mouse_event.event_type == MouseEventType.MOUSE_UP and mouse_event.button == MouseButton.LEFT:
            now = time.monotonic()
            idx = selected_index
            if idx == last_click["idx"] and (now - last_click["t"]) <= 0.5:
                value = option_list[idx][0]
                get_app().exit(result=value)
            last_click["idx"] = idx
            last_click["t"] = now
        return None

    def render_lines():
        fragments = []
        if header_text:
            fragments.append(("class:menu-header", header_text))
            fragments.append(("", "\n"))

        sel = selected_index

        for idx, (_, label) in enumerate(option_list):
            pointer = ">" if idx == sel else " "
            prefix = f" {pointer} " if idx == sel else "   "
            text = f"{prefix}{idx + 1}. {label}"
            style_class = "class:radio-selected" if idx == sel else "class:radio"
            fragments.append((style_class, text))
            if idx != len(option_list) - 1:
                fragments.append(("", "\n"))
        return fragments

    class MenuControl(FormattedTextControl):
        def __init__(self, render_fn, handler):
            super().__init__(render_fn, focusable=True, show_cursor=False)
            self._handler = handler

        def mouse_handler(self, mouse_event):
            return self._handler(mouse_event)

    control = MenuControl(render_lines, mouse_handler)
    window = Window(content=control, always_hide_cursor=True, dont_extend_width=True, dont_extend_height=True)

    radio_style = Style.from_dict(
        {
            "radio-list": "",
            "radio": "fg:#cbd6e2",
            "radio-selected": "fg:#e6edf3 bold underline",
            "radio-checked": "fg:#7ad1a8",
            "radio-number": "fg:#9dcffb bold",
        }
    )

    app_style = merge_styles([style_override, radio_style]) if style_override else radio_style

    kb_final = merge_key_bindings([kb, extra_bindings]) if extra_bindings else kb

    app = Application(
        layout=Layout(window, focused_element=control),
        key_bindings=kb_final,
        mouse_support=True,
        full_screen=False,
        style=app_style,
    )

    result = app.run()
    if result is None:
        sel = selected_index or 0
        result = option_list[sel][0]
    return result


def choose(message: str, options: Iterable[Option], default: Optional[str] = None,
           extra_bindings: Optional[KeyBindings] = None, header_text: Optional[str] = None,
           header_click_callback=None):
    return menu_choice(
        message=message,
        options=[(opt.value, opt.label) for opt in options],
        default=default,
        style_override=style,
        extra_bindings=extra_bindings,
        header_text=header_text,
        header_click_callback=header_click_callback,
    )