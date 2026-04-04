import adbutils
import subprocess
import serial.tools.list_ports

def _check_adb_devices() -> bool:
    try:
        devices = adbutils.adb.device_list()
        return len(devices) > 0
    except Exception as e:
        print(f"Error checking ADB devices: {e}")
        return False
    

def _check_edl_devices() -> bool:
    try:
        ports = serial.tools.list_ports.comports()
        edl_devices = [port for port in ports if "Qualcomm HS-USB QDLoader 9008" in port.description]
        return len(edl_devices) > 0
    except Exception as e:
        print(f"Error checking EDL devices: {e}")
        return False
    

def _check_fastboot_devices() -> int:
    # return 1 if in bootloader, 2 if in fastbootd, 0 if not
    try:
        if subprocess.run(["fastboot", "devices"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout.strip() == "":
            return 0
        result = subprocess.run(["fastboot", "getvar", "is-userspace"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output = result.stdout.strip()
        if "is-userspace: yes" in output:
            return 2
        else:
            return 1 # normally this means it's in bootloader, but some devices don't support getvar is-userspace, so we just assume it's in bootloader if getvar fails
    except Exception:
        return 0


def check_device(type: str) -> bool:
    match type:
        case "adb":
            return _check_adb_devices()
        case "edl":
            return _check_edl_devices()
        case "fastboot":
            return _check_fastboot_devices() > 0
        case "fastbootd":
            return _check_fastboot_devices() == 2
        case "bootloader":
            return _check_fastboot_devices() == 1
        case _:
            return False
        

def wait_for_device(types: list) -> str:
    while True:
        for t in types:
            if check_device(t):
                return t
            