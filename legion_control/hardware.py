"""Hardware access: the 4-zone keyboard (ITE 8295 over USB) and the ideapad_acpi charging controls."""
import logging
import os
import re
import subprocess

import usb.core

log = logging.getLogger(__name__)


class LedController:
    """
    Talks to the Lenovo Legion lighting chip (ITE 8295) with raw USB control transfers.
    Needs write access to the USB device (udev rule: idVendor 048d, idProduct c965, MODE 0666).
    """
    VENDOR = 0x048D
    PRODUCT = 0xC965
    EFFECT = {"static": 1, "breath": 3, "wave": 4, "hue": 6, "off": 1}

    def __init__(self):
        self.device = usb.core.find(idVendor=self.VENDOR, idProduct=self.PRODUCT)
        if self.device is None:
            log.warning("Keyboard lighting controller %04x:%04x not found", self.VENDOR, self.PRODUCT)

    @property
    def available(self):
        return self.device is not None

    def build_control_string(self, effect, colors=None, speed=1, brightness=1, wave_direction=None):
        """
        Build the 32-byte payload.

        effect: 'static', 'breath', 'wave', 'hue' or 'off'
        colors: 4 hex strings 'RRGGBB' (or 'r,g,b'), one per zone
        speed: 1-4, brightness: 1 (low) or 2 (high), wave_direction: 'LTR' / 'RTL'
        """
        data = [204, 22]
        if effect == "off":
            data.append(self.EFFECT["off"])
            data += [0] * 30
            return data
        data.append(self.EFFECT[effect])
        data.append(speed)
        data.append(brightness)
        if effect not in ["static", "breath"]:
            data += [0] * 12
        else:
            chunk = [0, 0, 0]
            for section in range(4):
                if colors and section < len(colors) and colors[section].strip():
                    color = colors[section].lower()
                    if re.match(r"^[0-9a-f]{6}$", color):
                        chunk = [int(color[i:i + 2], 16) for i in range(0, 6, 2)]
                    elif "," in color:
                        components = color.split(",")
                        if all(c.strip().isdigit() for c in components):
                            chunk = [max(0, min(255, int(c))) for c in components[:3]]
                        else:
                            raise ValueError(f"Invalid RGB format: {color}")
                    else:
                        raise ValueError(f"Invalid color model: {color}")
                data += chunk
        data += [0]
        if wave_direction is not None:
            wd = wave_direction.upper()
            data += [1, 0] if wd == "RTL" else [0, 1] if wd == "LTR" else [0, 0]
        else:
            data += [0, 0]
        data += [0] * 13
        return data

    def send_control_string(self, data):
        """Send a payload. Returns True on success; errors are logged, not raised."""
        if not self.device:
            return False
        try:
            if self.device.is_kernel_driver_active(0):
                try:
                    self.device.detach_kernel_driver(0)
                except usb.core.USBError:
                    pass
            self.device.ctrl_transfer(bmRequestType=0x21, bRequest=0x9, wValue=0x03CC, wIndex=0x00,
                                      data_or_wLength=data)
            return True
        except usb.core.USBError as e:
            log.error("USB write to the keyboard failed: %s", e)
            return False


class PowerController:
    """
    Conservation mode and Rapid Charge through ideapad_acpi sysfs, with an acpi_call fallback for Rapid Charge.
    The sysfs files are root-only, so writes go through a single pkexec call per change.
    """
    RAPID_ACPI = "\\_SB.PCI0.LPC0.EC0.VPC0.SBMC "

    def __init__(self):
        self.conservation_path = self._find("conservation_mode")
        self.rapid_path = self._find("rapid_charge")
        self.has_acpi_call = os.path.exists("/proc/acpi/call")
        self.has_conservation = self.conservation_path is not None
        self.has_rapid = self.rapid_path is not None or self.has_acpi_call

    @staticmethod
    def _find(name):
        drivers_dir = "/sys/bus/platform/drivers/ideapad_acpi"
        if os.path.isdir(drivers_dir):
            for entry in os.listdir(drivers_dir):
                path = os.path.join(drivers_dir, entry, name)
                if entry.startswith("VPC") and os.path.exists(path):
                    return path
        for root, _dirs, files in os.walk("/sys/devices/platform"):
            if name in files:
                return os.path.join(root, name)
        return None

    @staticmethod
    def _read_flag(path):
        try:
            with open(path) as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    def get_conservation(self):
        return self.has_conservation and self._read_flag(self.conservation_path)

    def get_rapid(self):
        return self.rapid_path is not None and self._read_flag(self.rapid_path)

    def current_mode(self):
        if self.get_conservation():
            return "Conservation Mode"
        if self.get_rapid():
            return "Rapid Charge"
        return "Normal Charging"

    def set_mode(self, mode):
        """
        Switch to 'Normal Charging', 'Conservation Mode' or 'Rapid Charge'.
        Tries a direct write first (works if a udev rule grants access), otherwise one pkexec prompt.
        Returns True if the mode now reads back as requested.
        """
        conservation = mode == "Conservation Mode"
        rapid = mode == "Rapid Charge"
        writes = []  # (path, value)
        if self.has_conservation:
            writes.append((self.conservation_path, "1" if conservation else "0"))
        if self.rapid_path:
            writes.append((self.rapid_path, "1" if rapid else "0"))
        elif self.has_acpi_call:
            writes.append(("/proc/acpi/call", self.RAPID_ACPI + ("0x07" if rapid else "0x08")))
        # Turn the other mode off before turning the requested one on (the firmware refuses both at once)
        writes.sort(key=lambda w: w[1] not in ("0", self.RAPID_ACPI + "0x08"))

        try:
            for path, value in writes:
                with open(path, "w") as f:
                    f.write(value)
        except PermissionError:
            script = "; ".join(f"echo {_shq(v)} > {_shq(p)}" for p, v in writes)
            result = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)
            if result.returncode != 0:
                log.warning("Changing charge mode was cancelled or failed: %s", result.stderr.strip())
        except OSError as e:
            log.error("Changing charge mode failed: %s", e)
        return self.current_mode() == mode or (rapid and not self.rapid_path)


def _shq(s):
    """Single-quote a string for sh."""
    return "'" + s.replace("'", "'\\''") + "'"


PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"


def read_platform_profile():
    """Current platform_profile (low-power / balanced / performance / custom)."""
    try:
        with open(PLATFORM_PROFILE) as f:
            return f.read().strip()
    except OSError:
        return None


def platform_profile_choices():
    try:
        with open(PLATFORM_PROFILE + "_choices") as f:
            return f.read().split()
    except OSError:
        return []


def set_platform_profile(profile):
    """
    Switch the power profile (same as Fn+Q). Writes directly if allowed (extras/99-legion-control-power.rules),
    otherwise asks for the password once through pkexec. Returns True if the profile now reads back as requested.
    """
    if profile not in platform_profile_choices():
        log.warning("Unknown power profile %r (choices: %s)", profile, platform_profile_choices())
        return False
    try:
        with open(PLATFORM_PROFILE, "w") as f:
            f.write(profile)
    except PermissionError:
        result = subprocess.run(["pkexec", "sh", "-c", f"echo {_shq(profile)} > {PLATFORM_PROFILE}"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            log.warning("Changing the power profile was cancelled or failed: %s", result.stderr.strip())
    except OSError as e:
        log.error("Changing the power profile failed: %s", e)
    return read_platform_profile() == profile
