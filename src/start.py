# -*- coding: utf-8 -*-

"""AndroidToolkit startup script and interactive menu entrypoint."""

# Hidden import to ensure CFFI modules are properly included in Nuitka builds
import _cffi_backend # noqa: F401
import logging
import os
import sys
import platform
import time
import datetime
from typing import Optional, Tuple, List, Dict
from prompt_toolkit import (
    print_formatted_text,
    ANSI,
    HTML,
    prompt
)
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.shortcuts import clear, set_title
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType
from functools import wraps
from flash_ak3 import AnyKernel3
from utils.menu import choose, Option
from utils.lang import t, set_lang
import colorama
import subprocess
import socket
import traceback
import threading
# TODO: Plugin system
import pluginutils, pluginutils.load, pluginutils.manage # noqa: F401
import argparse
try:
    import msvcrt
except ImportError:
    import termios
    import tty
    import select


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

_labels_cache = {}
INFO = ""
ERROR = ""
WARN = ""

def _init_labels():
    global INFO, ERROR, WARN
    _labels_cache.clear()
    INFO = f"<info>{t('[信息]', '[INFO]')}</info>"
    ERROR = f"<error>{t('[错误]', '[ERROR]')}</error>"
    WARN = f"<orange>{t('[警告]', '[WARN]')}</orange>"

flag = False
key = False
started = False

LINE = "-" * 68


class MultilineFormatter(logging.Formatter):
    def format(self, record):
        original = super().format(record)
        lines = original.splitlines()
        if len(lines) <= 1:
            return original
        prefix = lines[0][:len(lines[0]) - len(record.getMessage())]
        return '\n'.join([lines[0]] + [prefix + line for line in lines[1:]])


""" UTILITY FUNCTIONS """

def onerror(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {fn.__name__}: {e}")
            logger.exception("msg")
            print_formatted_text(HTML(ERROR + "抱歉，脚本遇到了未经捕获的异常，即将退出..."), style=style)
            print_formatted_text(HTML(INFO + "错误详情已记录到安装目录下 logs 文件夹中，您可以将该文件发送给技术支持以获取帮助。"), style=style)
            time.sleep(3)
            cleanup(-1)
    return wrapper


def auto_clear(fn=None, *, logo=False, end=False):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            clear()
            if logo:
                # TODO: 恢复外部批处理调用: run("call .\\logo.bat")
                pass
            result = func(*args, **kwargs)
            if end: clear()
            return result
        return wrapper

    return decorator(fn) if fn is not None else decorator


def run(
    cmd: str,
    *,
    extra_env: Optional[Dict[str, str]] = None,
    check: bool = False,
):
    subprocess.run(cmd, shell=True, env={**os.environ, **(extra_env or {})}, check=check, text=True, errors="replace")


def checkwin() -> Tuple[str, str, str, Tuple[str, str]]:
    return (
        platform.system(),
        platform.release(),
        platform.version(),
        platform.architecture()
    )


def pause(message: str = "Click or press any key to continue", style_override: Optional[Style] = None, timeout: Optional[float] = None) -> None:
    def _console_pause(msg: str, to: Optional[float]):
        sys.stdout.write(msg)
        sys.stdout.flush()
        if to is not None and to <= 0:
            print()
            return
        # Windows
        try:
            start = time.time()
            if to is None:
                msvcrt.getwch()
            else:
                while True:
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                        break
                    if time.time() - start >= to:
                        break
                    time.sleep(0.05)
            print()
            return
        except NameError:
            pass

        # POSIX
        try:
            fd = sys.stdin.fileno()
            old_attrs = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                if to is None:
                    os.read(fd, 1)
                else:
                    rlist, _, _ = select.select([fd], [], [], to)
                    if rlist:
                        os.read(fd, 1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
            print()
            return
        except NameError:
            pass

        # Fallback to input()
        try:
            input()
        except Exception:
            time.sleep(to or 2)

    # If not a tty, do a simple console pause
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        _console_pause(message, timeout)
        return

    # Otherwise try interactive prompt_toolkit pause; if that fails, fallback to console
    try:
        chosen_style = style_override or style
        if chosen_style is None:
            fallback_style = Style.from_dict({"pause": "fg:#cbd6e2"})
            chosen_style = fallback_style

        pause_style = Style.from_dict({"pause": "fg:#9dcffb bold"})
        app_style = merge_styles([chosen_style, pause_style]) if chosen_style else pause_style

        kb = KeyBindings()

        @kb.add("enter", eager=True)
        @kb.add(" ", eager=True)
        def _enter(event):
            event.app.exit()

        @kb.add("<any>")
        def _any(event):
            event.app.exit()

        def _mouse_handler(mouse_event):
            if mouse_event.event_type == MouseEventType.MOUSE_UP:
                try:
                    get_app().exit()
                except Exception:
                    pass
            return None

        class PauseControl(FormattedTextControl):
            def __init__(self, render_fn, handler):
                super().__init__(render_fn, focusable=True, show_cursor=False)
                self._handler = handler

            def mouse_handler(self, mouse_event):
                return self._handler(mouse_event)

        control = PauseControl(lambda: [("class:pause", message)], _mouse_handler)
        window = Window(content=control, always_hide_cursor=True, dont_extend_width=False, dont_extend_height=False)

        app = Application(
            layout=Layout(window, focused_element=control),
            key_bindings=kb,
            mouse_support=True,
            full_screen=False,
            style=app_style,
        )

        if timeout is not None and timeout > 0:
            def _timer():
                time.sleep(timeout)
                try:
                    app.exit()
                except Exception:
                    pass

            t = threading.Thread(target=_timer, daemon=True)
            t.start()

        app.run()
    except Exception:
        _console_pause(message, timeout)


def check_adb_server() -> Tuple[bool, Optional[Exception]]:
    adb_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # ADB Server request timeout: fast 0.2, usually 0.25, default 0.3, slowly 0.6
    adb_server.settimeout(0.3)
    try:
        adb_server.connect(("127.0.0.1", 5037))
    except socket.timeout:
        return False, None
    except Exception as e:
        return False, e
    adb_server.close()
    return True, None


""" UI/MENU FUNCTIONS """


@onerror
def menu() -> str:
    if os.path.exists("mod") and os.path.isdir("mod"):
        print_formatted_text(HTML(t("已加载扩展列表：", "Loaded Mods:")), style=style) if len(os.listdir("mod")) != 0 else print_formatted_text(HTML(t("已加载扩展列表：未加载任何扩展", "Loaded Mods: No mods loaded")), style=style)
        if len(os.listdir("mod")) != 0:
            i: int = 1
            for item in os.listdir("mod"):
                print_formatted_text(f"{i}. {item}", style=style)
                i += 1
    else:
        os.remove("mod") if os.path.isfile("mod") else ...
        os.makedirs("mod", exist_ok=True)

    print_formatted_text(ANSI(t("鼠标双击或按回车键确定，方向键，数字键，鼠标单击来选择功能", "Double-click/Enter to confirm, arrows/numbers/click to select")))

    header = t("AndroidToolkit 控制台&主菜单", "AndroidToolkit Console & Main Menu")

    options = [
        Option("onekeyroot", t("一键Root", "One-Click Root")),
        Option("gbl", t("粗粮高通机型临时Root&强解bl", "Temporary Root & BL Unlock (Qualcomm)")),
        Option("openshell", t("在此处打开cmd[含adb环境]", "Open CMD here (with ADB)")),
        Option("about", t("关于脚本", "About")),
        Option("mods", t("扩展管理", "Extensions")),
        Option("commonly", t("常用合集[子菜单]", "Common Tools [Submenu]")),

        Option("man-apps", t("应用管理[子菜单]", "App Manager [Submenu]")),
        Option("magisk-mod", t("Magisk模块管理[子菜单]", "Magisk Modules [Submenu]")),
    ]
    options.append(Option("user-debug", t("高级菜单[子菜单]", "Advanced [Submenu]")))
    options.append(Option("exit", t("退出工具", "Exit")))

    kb = KeyBindings()
    result = choose(
        message="",
        options=options,
        default="onekeyroot",
        extra_bindings=kb,
        header_text=header,
        header_click_callback=None,
    )

    clear()
    return result


""" SPECIAL FUNCTIONS """

@onerror
def sel():
    clear()
    run("call sel file s .")
    pause(t("已选择文件，按任意键继续...", "File selected, press any key to continue..."))
    run("call sel file m .")
    pause(t("已选择文件，按任意键继续...", "File selected, press any key to continue..."))


@onerror
def color():
    clear()
    print_formatted_text(HTML(INFO + "<black>BLACK</black>"), style=style)
    print_formatted_text(HTML(INFO + "<red>RED</red>"), style=style)
    print_formatted_text(HTML(INFO + "<green>GREEN</green>"), style=style)
    print_formatted_text(HTML(INFO + "<orange>ORANGE</orange>"), style=style)
    print_formatted_text(HTML(INFO + "<blue>BLUE</blue>"), style=style)
    print_formatted_text(HTML(INFO + "<magenta>MAGENTA</magenta>"), style=style)
    print_formatted_text(HTML(INFO + "<cyan>CYAN</cyan>"), style=style)
    print_formatted_text(HTML(INFO + "<white>WHITE</white>"), style=style)
    run("pause")


""" FLASHING FUNCTIONS """

@onerror
def flash_anykernel3(ak3_path, boot_path):
    global logger
    try:
        ak3 = AnyKernel3(ak3_path)
        ak3.extract_zip()
        ak3.unpack_bootimg(boot_path, "./tmp/boot_unpacked")
        ak3.rename_mainfile()
        ak3.patch_bootimg()
        ak3.repack_bootimg(repack_to="./tmp/boot_patched.img")
        ak3.clean_up()
        os.remove("./tmp/kernel")
    except Exception as e:
        logger.error(traceback.format_exc())
        return 1


def flash_partation(imgpath: str, part: Optional[str] = "boot"):
    run("device_check.exe fastboot")
    print("\n")
    run(f"fastboot.exe flash {part} {imgpath}")


def _extract_boot_to_tmp(paths: List[str], partition_name: str) -> bool:
    run("adb start-server 1>nul")
    run("device_check.exe adb")
    print_formatted_text("\n", style=style)
    for prefix in paths:
        process = subprocess.run(["adb.exe", "shell", f"su -c \"dd if={prefix}{partition_name} of=/sdcard/boot.img bs=2048\""])
        if process.returncode == 0:
            break
    process = subprocess.run(["adb.exe", "pull", "/sdcard/boot.img", "./tmp/boot.img"])
    return process.returncode == 0


@auto_clear
@onerror
def anykernel3():
    paths = ["/dev/block/by-name/", "/dev/block/bootdevice/by-name"]
    mapping = {
        "1": ("boot", "boot"),
        "2": ("boot_a", "boot_a"),
        "3": ("boot_b", "boot_b"),
    }

    while True:
        print_formatted_text(HTML(WARN + t("目前仅支持boot.img修补，并可能存在未知问题！", "Only boot.img patching is supported, may have unknown issues!")), style=style)
        result = choose(message="", options=[
            Option("A", t("返回上级菜单", "Back")),
            Option("1", t("A-only槽位", "A-only Slot")),
            Option("2", t("AB分区-A槽位", "AB Partition - Slot A")),
            Option("3", t("AB分区-B槽位", "AB Partition - Slot B"))
        ], default="A")
        if result == "A":
            clear()
            return
        if result not in mapping:
            print_formatted_text(HTML(ERROR + t("输入错误，请重新输入", "Invalid input, please try again")), style=style)
            continue

        src_partition, dst_partition = mapping[result]
        if not _extract_boot_to_tmp(paths, src_partition):
            print_formatted_text(HTML(ERROR + t("提取Boot失败", "Failed to extract boot")), style=style)
            continue
        print_formatted_text(HTML(INFO + t("请加载AnyKernel3 Zip", "Please load AnyKernel3 Zip")), style=style)
        run("call sel file s .")
        with open("./tmp/output.txt", "r", encoding="utf-8") as f:
            filepath = f.read().rstrip("\r\n").rstrip("\n")
        flash_anykernel3(filepath, "./tmp/boot.img")
        flash_partation("./tmp/boot_patched.img", dst_partition)
        print_formatted_text(HTML(INFO + t("刷入成功", "Flash successful")), style=style)


""" FEATURE MENU HANDLERS """

@onerror
@auto_clear(logo=True, end=True)
def root():
    while True:
        result = choose(
            message=t("一键Root菜单", "One-Click Root Menu"),
            options=[
                Option("A", t("返回上级菜单", "Back")),
                Option("1", t("手机通用Root", "Android Phone Generic Root")),
            ],
            default="A"
        )
        match result:
            case "A":
                return
            case "1":
                # TODO: 恢复外部批处理调用: run("call otherroot")
                ...


@onerror
@auto_clear(logo=True, end=True)
def qcom_gbl():
    run("call qcom_gbl_selinux.bat"); clear()


@onerror
@auto_clear(logo=True, end=True)
def appset():
    while True:
        result = choose(
            message=t("应用管理菜单", "App Manager Menu"),
            options=[
                Option("A", t("返回上级菜单", "Back")),
                Option("1", t("安装应用", "Install App")),
                Option("2", t("卸载应用", "Uninstall App"))
            ],
            default="A"
        )
        match result:
            case "A":
                return
            case "1":
                # TODO: run("call userinstapp")
                clear()
            case "2":
                # TODO:  run("call unapp")
                clear()


@onerror
@auto_clear(logo=True, end=True)
def userdebug():
    while True:
        result = choose(
            message="Advanced Options",
            options=[
                Option("A", t("返回上级菜单", "Back")),
                Option("1", t("设备信息", "Device Info")),
                Option("2", t("导入本地root文件", "Import Local Root Files")),
                Option("3", t("恢复出厂设置", "Factory Reset"))
                ],
                default="A"
        )
        match result:
            case "A":
                return
            case "1":
                # TODO device info implementation
                clear()
            case "2":
                # TODO import root files implementation
                clear()
            case "3":
                # TODO factory reset implementation
                clear()

@onerror
@auto_clear(logo=True, end=True)
def commonly():
    while True:
        commonly_list: List[Option] = [
            Option("A", t("返回上级菜单", "Back")),
            Option("1", t("刷入第三方Recovery", "Flash Custom Recovery")),
            Option("2", t("备份与恢复", "Backup & Restore")),
            Option("3", t("scrcpy投屏", "scrcpy Screen Mirroring")),
            Option("4", t("高级重启", "Advanced Reboot")),
            Option("5", t("刷入AnyKernel3[实验性]", "Flash AnyKernel3 [Experimental]")),
            Option("6", t("开启无线调试", "Enable Wireless Debugging"))
        ]
        result = choose(
            message=t("常用合集", "Common Tools"),
            options=commonly_list,
            default="A"
        )
        match result:
            case "A":
                return
            case "2":
                # TODO ota
                clear()
            case "3":
                # TODO twrp flash
                clear()
            case "5":
                # TODO backup & restore
                clear()
            case "8":
                subprocess.Popen("scrcpy.exe", text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                clear()
            case "9":
                # TODO advanced reboot
                clear()
            case "10":
                clear()
                anykernel3()
            case "11":
                # TODO wifiadb
                clear()


@onerror
@auto_clear(logo=True, end=True)
def magisk():
    while True:
        result = choose(
            message=t("magisk模块管理", "Magisk Module Manager"),
            options=[
                Option("A", t("返回上级菜单", "Back")),
                Option("1", t("刷入Magisk模块", "Flash Magisk Module")),
                Option("2", t("刷入Xposed框架", "Flash Xposed Framework")),
            ],
            default="A"
        )
        if result == "A":
            return
        if result == "1":
            # TODO Module Manager
            clear()
        if result == "2":
            # TODO Xposed Installer
            clear()


""" MOD MANAGEMENT FUNCTIONS """

def load_mod_menu():
    mod_dir = ".\\mod"
    if not os.path.isdir(mod_dir):
        print_formatted_text(HTML(ERROR + t("未找到 mod 目录", "mod directory not found")), style=style)
        return None

    dirs = [d for d in os.listdir(mod_dir)
            if os.path.isdir(os.path.join(mod_dir, d))]

    if not dirs:
        print_formatted_text(HTML(WARN + t("未发现任何扩展", "No mods found")), style=style)
        time.sleep(2)
        return None

    base = 10
    mapping = {}
    options = [("A", t("返回上级菜单", "Back"))]

    for i, name in enumerate(dirs, start=base + 1):
        key = str(i)
        mapping[key] = name
        options.append((key, name))

    result = choose(
        message=t("已加载扩展", "Loaded Mod(s)"),
        options=[Option(value, label) for value, label in options],
        default="A"
    )

    if result == "A":
        return None

    return mapping.get(result)


@onerror
def run_mod_main(modname):
    # TODO load mod
    ...


@onerror
@auto_clear(logo=True, end=True)
def mod():
    while True:
        result = choose(
            message=t("扩展管理", "Extensions Manager"),
            options=[
                Option("A", t("返回上级菜单", "Back")),
                Option("1", t("运行已安装扩展", "Run Installed Extension")),
                Option("2", t("安装扩展", "Install Extension")),
                Option("3", t("卸载扩展", "Uninstall Extension")),
            ],
            default="A"
        )
        match result:
            case "A":
                return
            case "1":
                modname = load_mod_menu()
                if modname:
                    run_mod_main(modname)
            case "2":
                run("call mod")
            case "3":
                run("call unmod")


""" MAIN FLOW FUNCTIONS """

@onerror
@auto_clear(end=True)
def about():
    print_formatted_text(
        HTML(
            "<cyan>AndroidToolkit</cyan> is a community-driven and open-source TUI tool"
        )
    )

    kb = KeyBindings()

    prompt(
        HTML(INFO + t("单击此字符或按任意键继续返回上级菜单", "Click or press any key to go back")),
        key_bindings=kb,
        style=style
    )


@onerror
def pre_main(lang: str) -> bool:
    global flag
    global logger
    colorama.init(autoreset=True, convert=True)
    if not lang == "default":
        set_lang(lang)
    _init_labels()

    env_path_lower = (os.environ.get("PATH") or "").lower()
    keywords = ["windows", "system32", "powershell"]
    if not all(k in env_path_lower for k in keywords):
        print_formatted_text(HTML(ERROR + t("你的系统环境变量异常，这可能导致异常问题，输入no跳过", "Abnormal system environment variables, input 'no' to skip")), style=style)
        answer = input().strip().lower()
        if answer != "no":
            return False
    title = "AndroidToolkit"
    set_title(title)
    os.makedirs("mod", exist_ok=True)
    for item in os.listdir("mod"):
        item_path = os.path.join("mod", item)
        if os.path.isdir(item_path):
            if os.path.exists(os.path.join(item_path, "start.bat")):
                run(f'cd /d mod\\{item} && call start.bat')

    try:
        this_path = os.path.dirname(os.path.abspath(__file__))
        candidate_bin = os.path.normpath(os.path.join(this_path, "..", "bin"))
        if os.path.isdir(candidate_bin):
            os.chdir(candidate_bin)
            logger.debug("Changed working directory to %s", candidate_bin)
        else:
            logger.debug("Bin directory not found: %s; continuing in current working directory", candidate_bin)
    except Exception:
        logger.exception("Failed to change working directory to bin; continuing")


    if os.getenv("ATB_SKIP_PLATFORM_CHECK", "0") != "1":
        print_formatted_text(HTML(INFO + t("正在检查Windows属性...", "Checking Windows properties...")), style=style)
        os_name, os_release, os_version, arch = checkwin()
        match arch[0]:
            case "64bit":
                arch = "x64"
            case "32bit":
                arch = "x86"
            case _:
                arch = "arm64-v8a"
        print_formatted_text(HTML(INFO + f"{t('当前运行环境', 'Current environment')}:{os_name}{os_release}_{arch}_{os_version}"), style=style)
        os_vercode = 0
        try:
            os_vercode = float(os_release)
        except ValueError:
            pass
        if os_vercode <= 7:
            print_formatted_text(HTML(ERROR + t("此脚本需要 Windows 8 或更高版本", "This script requires Windows 8 or higher")), style=style)
            pause(t("按任意键退出", "Press any key to exit"))
            return False
        print_formatted_text(HTML(INFO + f"{t('当前系统', 'Current system')}: {os_name} {os_release}"), style=style)
        if subprocess.run(["where", "adb.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True).returncode != 0:
            print_formatted_text(HTML(ERROR + t("未找到 ADB 可执行文件", "ADB executable not found")), style=style)
            pause(t("按任意键退出", "Press any key to exit"))
            return False
        adb_process = subprocess.Popen(["adb.exe", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=True)
        adb_process.wait()
        if adb_process.returncode != 0:
            print_formatted_text(HTML(ERROR + f"ADB{t('检查失败，返回值', 'check failed, return code')}：{adb_process.returncode}"), style=style)
            return False
        print_formatted_text(HTML(INFO + t("检查ADB命令成功", "ADB check successful")), style=style)

    pause(t("单击此字符或按任意键继续", "Click or press any key to continue"))
    flag = True
    clear()
    return True


@onerror
def cleanup(code: int = 0):
    print_formatted_text(HTML(INFO + t("正在结束ADB服务...", "Stopping ADB service...")), style=style)
    if check_adb_server()[0]:
        subprocess.Popen(["adb.exe", "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
    sys.exit(code)


class AndroidToolkit(object):
    """High-level controller for preflight, menu loop, and action dispatch."""

    def __init__(self, lang: str) -> None:
        self.lang = lang

    def _run_pre_main(self) -> bool:
        return pre_main(self.lang) if not flag else True

    def _handle_action(self, action: str) -> Optional[int]:
        match action:
            case "onekeyroot":
                root()
            case "gbl":
                qcom_gbl()
            case "openshell":
                clear()
                subprocess.run(["cmd.exe", "/k"], shell=True)
                clear()
            case "about":
                about()
            case "mods":
                mod()
            case "commonly":
                commonly()
            case "user-debug":
                userdebug()
            case "man-apps":
                appset()
            case "magisk-mod":
                magisk()
            case "exit":
                return 0
        return None

    def run(self) -> int:
        try:
            pre_ok = self._run_pre_main()
            if not pre_ok:
                return 1
            while True:
                clear()
                run("call logo")
                selection = menu()
                maybe_code = self._handle_action(selection)
                if maybe_code is not None:
                    return maybe_code
        except KeyboardInterrupt:
            print_formatted_text(HTML("\n" + WARN + t("检测到用户中断，正在退出...", "User interruption detected, exiting...")), style=style)
            return 0


@onerror
def main(lang: str) -> int:
    return AndroidToolkit(lang).run()


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    os.makedirs("logs", exist_ok=True)
    filename = f"logs/atb_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = MultilineFormatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    parser = argparse.ArgumentParser(description="AndroidToolkit - A community-driven TUI tool for Android management")
    parser.add_argument("--lang", choices=["en", "zh", "default"], help="Set the language for the interface (en or zh)", default=None)
    args = parser.parse_args()
    lang = args.lang if args.lang else os.environ.get("ATB_LANG", "default")

    exit_code = main(lang)
    logger.debug("ATBExitEvent, main returned: %s", exit_code)
    cleanup(exit_code)
