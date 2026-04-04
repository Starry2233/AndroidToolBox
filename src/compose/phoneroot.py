import subprocess
import os
import sys
import shutil
import time
import tempfile
from typing import Optional
import adbutils
from adbutils import adb
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.styles import Style
from utils.lang import t


STYLE = Style.from_dict({
    "yellow": "fg:#f1c40f",
    "red": "fg:#ff7b7b",
    "orange": "fg:#f4a261",
    "info": "fg:#3B78FF",
    "cyan": "fg:#67e0c2",
    "green": "fg:#7ad1a8",
    "blue": "fg:#8ab4f8",
    "magenta": "fg:#c7a0ff",
    "white": "fg:#e6edf3",
})

INFO = t("[信息]", "[Info]")
ERROR = t("[错误]", "[Error]")
WARN = t("[警告]", "[Warn]")


def _info(msg: str):
    print_formatted_text(HTML(f"<info>{INFO}</info> {msg}"), style=STYLE)


def _error(msg: str):
    print_formatted_text(HTML(f"<red>{ERROR}</red> {msg}"), style=STYLE)


def _warn(msg: str):
    print_formatted_text(HTML(f"<orange>{WARN}</orange> {msg}"), style=STYLE)


def _ok(msg: str):
    print_formatted_text(HTML(f"<green>{msg}</green>"), style=STYLE)


def _heading(msg: str):
    print_formatted_text(HTML(f"<yellow>{msg}</yellow>"), style=STYLE)


def _sub(msg: str):
    print_formatted_text(HTML(f"<cyan>{msg}</cyan>"), style=STYLE)


class PhoneRootError(Exception):
    pass


class PhoneRoot(object):
    def __init__(
        self,
        magisk_apk_path: str,
        magiskboot_path: str,
        adb_exe: str = "adb.exe",
        fastboot_exe: str = "fastboot.exe",
    ):
        self.magisk_apk_path = magisk_apk_path
        self.magiskboot_path = magiskboot_path
        self.adb_exe = adb_exe
        self.fastboot_exe = fastboot_exe
        self._tmp_dir: Optional[str] = None

    def _get_device(self, serial: Optional[str] = None) -> adbutils.AdbDevice:
        return adb.device(serial=serial) if serial else adb.device()

    def is_rooted(self, serial: Optional[str] = None) -> bool:
        try:
            device = self._get_device(serial)
            result = device.shell("su -c 'id'")
            return "uid=0(root)" in result
        except Exception as e:
            _error(f"Error checking root status: {e}")
            return False

    def is_device_connected(self) -> bool:
        return len(adb.device_list()) > 0

    def is_in_fastboot(self) -> bool:
        result = subprocess.run(
            [self.fastboot_exe, "devices"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().splitlines()
        return any(line.strip() and "fastboot" in line.lower() for line in lines[1:] if line.strip())

    def push_magisk_apk(self, serial: Optional[str] = None) -> str:
        device = self._get_device(serial)
        dest = "/data/local/tmp/magisk.apk"
        device.sync.push(self.magisk_apk_path, dest)
        return dest

    def extract_boot_image(self, partition: str = "boot", serial: Optional[str] = None) -> str:
        device = self._get_device(serial)
        self._ensure_tmp_dir()

        paths_to_try = [
            f"/dev/block/by-name/{partition}",
            f"/dev/block/bootdevice/by-name/{partition}",
        ]

        src_path = None
        for path in paths_to_try:
            result = device.shell(f"ls {path}")
            if "No such file" not in result and result.strip():
                src_path = path
                break

        if not src_path:
            raise PhoneRootError(t(f"无法找到 {partition} 分区路径", f"Cannot find {partition} partition path"))

        remote_tmp = "/data/local/tmp/boot.img"
        device.shell(f"su -c 'dd if={src_path} of={remote_tmp}'")
        local_path = os.path.join(self._tmp_dir, "boot.img")
        device.sync.pull(remote_tmp, local_path)
        device.shell(f"rm {remote_tmp}")

        if not os.path.exists(local_path):
            raise PhoneRootError(t("提取 boot.img 失败", "Failed to extract boot.img"))

        return local_path

    def reboot_to_fastboot(self, serial: Optional[str] = None):
        device = self._get_device(serial)
        device.reboot_bootloader()
        _info(t("正在重启到 Fastboot 模式...", "Rebooting to Fastboot mode..."))
        time.sleep(5)

    def flash_boot(self, boot_img_path: str, slot: Optional[str] = None):
        if not os.path.exists(boot_img_path):
            raise PhoneRootError(t(f"文件不存在: {boot_img_path}", f"File not found: {boot_img_path}"))

        cmd = [self.fastboot_exe, "flash"]
        if slot:
            cmd.append(slot)
        cmd.extend(["boot", boot_img_path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise PhoneRootError(t(f"Fastboot 刷入失败: {result.stderr}", f"Fastboot flash failed: {result.stderr}"))
        _ok(t("Boot 镜像刷入成功", "Boot image flashed successfully"))

    def reboot_device(self):
        subprocess.run([self.fastboot_exe, "reboot"], timeout=10)

    def patch_boot_image(
        self,
        boot_img_path: str,
        magisk_version: str = "25",
        output_path: Optional[str] = None,
    ) -> str:
        if not os.path.exists(self.magiskboot_path):
            raise PhoneRootError(t(f"magiskboot.exe 不存在: {self.magiskboot_path}", f"magiskboot.exe not found: {self.magiskboot_path}"))
        if not os.path.exists(boot_img_path):
            raise PhoneRootError(t(f"boot.img 不存在: {boot_img_path}", f"boot.img not found: {boot_img_path}"))

        self._ensure_tmp_dir()
        if output_path is None:
            output_path = os.path.join(self._tmp_dir, "patched_boot.img")

        work_dir = self._tmp_dir
        shutil.copy2(boot_img_path, os.path.join(work_dir, "boot.img"))
        shutil.copy2(self.magiskboot_path, os.path.join(work_dir, "magiskboot.exe"))

        magisk_dir = os.path.dirname(self.magiskboot_path)
        for fname in ["magiskinit", "magisk32.xz", "magisk64.xz"]:
            src = os.path.join(magisk_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(work_dir, fname))

        old_cwd = os.getcwd()
        try:
            os.chdir(work_dir)
            self._run_magiskboot_patch(magisk_version, output_path)
        finally:
            os.chdir(old_cwd)

        if not os.path.exists(output_path):
            raise PhoneRootError(t("修补 boot.img 失败", "Failed to patch boot.img"))

        _ok(t(f"修补成功: {output_path}", f"Patched: {output_path}"))
        return output_path

    def _run_magiskboot_patch(self, version: str, output_path: str):
        boot_path = os.path.join(self._tmp_dir, "boot.img")

        subprocess.run(
            ["magiskboot.exe", "unpack", "-h", boot_path],
            capture_output=True, timeout=30, check=True
        )

        ramdisk_path = os.path.join(self._tmp_dir, "ramdisk.cpio")
        if not os.path.exists(ramdisk_path):
            raise PhoneRootError(t("未检测到 ramdisk，可能不是有效的 boot.img", "No ramdisk found, may not be a valid boot image"))

        shutil.copy2(ramdisk_path, os.path.join(self._tmp_dir, "ramdisk.cpio.orig"))

        config_path = os.path.join(self._tmp_dir, "config")
        with open(config_path, "w") as f:
            f.write("KEEPVERITY=true\nKEEPFORCEENCRYPT=true\nPATCHVBMETAFLAG=false\nRECOVERYMODE=false\nLEGACYSAR=true\n")

        cpio_cmds = [
            "add 0750 init magiskinit",
            "mkdir 0750 overlay.d",
            "mkdir 0750 overlay.d/sbin",
        ]
        if os.path.exists(os.path.join(self._tmp_dir, "magisk32.xz")):
            cpio_cmds.append("add 0644 overlay.d/sbin/magisk32.xz magisk32.xz")
        if os.path.exists(os.path.join(self._tmp_dir, "magisk64.xz")):
            cpio_cmds.append("add 0644 overlay.d/sbin/magisk64.xz magisk64.xz")
        cpio_cmds.extend([
            "patch", "backup ramdisk.cpio.orig",
            "mkdir 000 .backup", "add 000 .backup/.magisk config",
        ])

        subprocess.run(
            ["magiskboot.exe", "cpio", "ramdisk.cpio"] + cpio_cmds,
            capture_output=True, timeout=30, check=True
        )

        subprocess.run(
            ["magiskboot.exe", "hexpatch", "kernel",
             "49010054011440B93FA00F71E9000054010840B93FA00F7189000054001840B91FA00F7188010054",
             "A1020054011440B93FA00F7140020054010840B93FA00F71E0010054001840B91FA00F7181010054"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["magiskboot.exe", "hexpatch", "kernel", "821B8012", "E2FF8F12"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["magiskboot.exe", "hexpatch", "kernel",
             "77616E745F696E697472616D667300", "736B69705F696E697472616D667300"],
            capture_output=True, timeout=10
        )

        new_boot = os.path.join(self._tmp_dir, "boot_new.img")
        subprocess.run(
            ["magiskboot.exe", "repack", boot_path, new_boot],
            capture_output=True, timeout=30, check=True
        )

        shutil.move(new_boot, output_path)

    def full_root_flow(
        self,
        serial: Optional[str] = None,
        magisk_version: str = "25",
        slot: Optional[str] = None,
        auto_reboot: bool = True,
    ):
        _heading(t("=== Android 一键 Root ===", "=== Android One-Click Root ==="))

        if not self.is_device_connected():
            raise PhoneRootError(t("未检测到 ADB 设备，请确保 USB 调试已开启并连接设备", "No ADB device detected. Ensure USB debugging is enabled."))

        device = self._get_device(serial)
        _info(t(f"已连接设备: {device.serial}", f"Connected: {device.serial}"))

        _info(t("[1/4] 正在提取 boot.img...", "[1/4] Extracting boot.img..."))
        boot_path = self.extract_boot_image(serial=serial)
        _sub(f"  -> {boot_path}")

        _info(t(f"[2/4] 正在修补 boot.img (Magisk v{magisk_version})...", f"[2/4] Patching boot.img (Magisk v{magisk_version})..."))
        patched_path = self.patch_boot_image(boot_path, magisk_version)
        _sub(f"  -> {patched_path}")

        _info(t("[3/4] 正在重启到 Fastboot 模式...", "[3/4] Rebooting to Fastboot..."))
        self.reboot_to_fastboot(serial=serial)

        _info(t("等待设备进入 Fastboot...", "Waiting for Fastboot..."))
        for _ in range(20):
            if self.is_in_fastboot():
                break
            time.sleep(1)
        else:
            raise PhoneRootError(t("设备未在 20 秒内进入 Fastboot 模式", "Device did not enter Fastboot mode within 20s"))

        _info(t("[4/4] 正在刷入修补后的 boot.img...", "[4/4] Flashing patched boot.img..."))
        self.flash_boot(patched_path, slot=slot)

        if auto_reboot:
            _info(t("正在重启设备...", "Rebooting device..."))
            self.reboot_device()
            _info(t("等待设备启动完成 (约 30-60 秒)...", "Waiting for boot (~30-60s)..."))
            time.sleep(30)

            adb.wait_for_device(timeout=120)
            if self.is_rooted(serial=serial):
                print()
                _ok(t("恭喜！设备已成功获取 Root 权限", "Root obtained successfully!"))
            else:
                print()
                _warn(t("设备已重启，请手动检查 Root 状态", "Device rebooted. Please check root status manually."))
                _info(t("可安装 Magisk APK 进行完整性设置", "Install Magisk APK for complete setup if needed."))

        print()
        _heading(t("=== 流程完成 ===", "=== Done ==="))
        return patched_path

    def _ensure_tmp_dir(self):
        if self._tmp_dir is None or not os.path.exists(self._tmp_dir):
            self._tmp_dir = tempfile.mkdtemp(prefix="phoneroot_")
        os.makedirs(self._tmp_dir, exist_ok=True)

    def cleanup(self):
        if self._tmp_dir and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

    def __del__(self):
        self.cleanup()
