"""System information for the info dialog (cached; RAM speed needs root via pkexec, asked once)."""
import os
import platform
import re
import subprocess

STANDARD_RAM_GB = [4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 1024, 2048]


def _dmi(name):
    try:
        with open(f"/sys/devices/virtual/dmi/id/{name}") as f:
            return f.read().strip()
    except OSError:
        return ""


def device_name():
    p_name, p_version, p_family = _dmi("product_name"), _dmi("product_version"), _dmi("product_family")
    if "Legion" in p_version:
        return p_version
    if "Legion" in p_family:
        return p_family if p_name in p_family else f"{p_family} {p_name}"
    return p_name or "Unknown model"


def basic_info():
    info = {"User": os.environ.get("USER", ""), "Hostname": platform.node(), "OS": "Linux",
            "Kernel": platform.release(), "Device": device_name(), "BIOS": _dmi("bios_version") or "Unknown"}
    model = _dmi("product_name")
    if model and model != info["Device"]:
        info["Model ID"] = model
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    info["OS"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    try:
        with open("/proc/meminfo") as f:
            kb = int(next(l for l in f if l.startswith("MemTotal")).split()[1])
        gb = kb / 1024 / 1024  # MemTotal is a little under the installed size; round up to a standard size
        info["Memory"] = f"{next((s for s in STANDARD_RAM_GB if s >= gb), round(gb))} GB"
    except (OSError, StopIteration, ValueError):
        pass
    try:
        with open("/proc/cpuinfo") as f:
            info["CPU"] = next(l for l in f if l.startswith("model name")).split(":", 1)[1].strip()
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq") as f:
            info["CPU Speed"] = f"{int(f.read()) / 1e6:.2f} GHz"
    except (OSError, StopIteration, ValueError):
        pass
    try:
        out = subprocess.run(["lspci", "-mm"], capture_output=True, text=True, timeout=5).stdout
        gpus = []
        for line in out.splitlines():
            parts = re.findall(r'"([^"]*)"', line)
            if len(parts) >= 3 and ("VGA" in parts[0] or "3D" in parts[0]):
                vendor, dev = parts[1], parts[2]
                m = re.match(r"^(.*?) \[(.*?)\]", dev)
                if m:
                    dev = f"{m.group(2)} [{m.group(1)}]"
                vendor = ("NVIDIA" if "NVIDIA" in vendor.upper() else "AMD" if "Advanced Micro" in vendor
                          else "Intel" if "Intel" in vendor else vendor)
                gpus.append(f"{vendor} {dev}")
        for i, g in enumerate(gpus):
            info["GPU" if len(gpus) == 1 else f"GPU {i + 1}"] = g
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def ram_speed():
    """RAM speed from dmidecode (asks for the password once). Returns '' if cancelled."""
    try:
        out = subprocess.run(["pkexec", "dmidecode", "-t", "17"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    speeds = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(("Configured Memory Speed:", "Speed:")):
            val = line.split(":", 1)[1].strip()
            if val and "Unknown" not in val and "None" not in val:
                speeds.add(val)
    return ", ".join(sorted(speeds))


def display_rows(info):
    """Ordered (label, value) rows for the dialog."""
    shown = dict(info)
    if shown.get("CPU Speed"):
        shown["CPU"] = f"{shown.get('CPU', '')} @ {shown['CPU Speed']}"
    if shown.get("RAM Speed"):
        shown["Memory"] = f"{shown.get('Memory', '')} @ {shown['RAM Speed']}"
    rows = [(k, shown[k]) for k in ["User", "Hostname", "OS", "Kernel", "Device", "Model ID", "BIOS", "CPU", "Memory"]
            if shown.get(k)]
    rows += [(k, v) for k, v in shown.items() if k.startswith("GPU")]
    return rows
