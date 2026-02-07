# pluginutils/swt.py

from typing import Any, Callable, List, Optional, Tuple

_ENTRIES: List[Callable] = []


def entry(func: Callable) -> Callable:
    _ENTRIES.append(func)
    return func


def get_entries() -> List[Callable]:
    return list(_ENTRIES)


def clear_entries():
    _ENTRIES.clear()


_LOADS: List[Callable] = []


def preload(func: Callable) -> Callable:
    _LOADS.append(func)
    return func


def get_loads() -> List[Callable]:
    return list(_LOADS)


def clear_loads():
    _LOADS.clear()


_UNLOADS = []


def unload(func):
    _UNLOADS.append(func)
    return func


def get_unloads():
    return list(_UNLOADS)


def clear_unloads():
    _UNLOADS.clear()


HookRecord = Tuple[Callable, Optional[Any]]
_HOOKS: dict[str, List[HookRecord]] = {}


def hook(name: str, data: Optional[Any] = None):
    """
    注册钩子。``name`` 决定触发时机，``data`` 可附带额外上下文（如主菜单项元组）。
    - load: ATB 启动时执行
    - entry: 手动运行插件时执行
    - register-mainmenu: 注册主菜单项目，``data`` 约定为 (label, callback)
    """
    def decorator(func: Callable) -> Callable:
        _HOOKS.setdefault(name, []).append((func, data))
        return func

    return decorator


def get_hooks(name: str) -> List[Callable]:
    return [fn for fn, _ in _HOOKS.get(name, [])]


def get_hook_data(name: str) -> List[HookRecord]:
    return list(_HOOKS.get(name, []))


def clear_hooks():
    _HOOKS.clear()
