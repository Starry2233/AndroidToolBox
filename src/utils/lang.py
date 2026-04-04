import locale

_LANG = None

def _detect():
    global _LANG
    if _LANG is not None:
        return _LANG
    try:
        lang, _ = locale.getdefaultlocale()
    except Exception:
        lang = None
    _LANG = "zh" if lang and lang.startswith("zh") else "en"
    return _LANG

def set_lang(code: str):
    """Set language: 'zh' or 'en'"""
    global _LANG
    _LANG = code

def t(zh: str, en: str) -> str:
    """Return translated string based on detected locale."""
    return zh if _detect() == "zh" else en
