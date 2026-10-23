"""Battery readings from /sys/class/power_supply."""
import glob
import os


def find_battery():
    """First battery under /sys/class/power_supply (BAT0 on Legions), or None."""
    for path in sorted(glob.glob("/sys/class/power_supply/*")):
        try:
            with open(os.path.join(path, "type")) as f:
                if f.read().strip() == "Battery":
                    return path
        except OSError:
            continue
    return None


def _read(path, name, cast=str):
    try:
        with open(os.path.join(path, name)) as f:
            return cast(f.read().strip())
    except (OSError, ValueError):
        return None


def read_battery(path, conservation=False):
    """
    Snapshot of the battery as a dict:
    capacity (%), status, status_text, wattage (W), energy_now/full/design (Wh), health (%), time_str.
    Laptops report energy (µWh) or charge (µAh); charge is converted with the voltage.
    """
    data = {"capacity": 0, "status": "Unknown", "status_text": "Unknown", "wattage": 0.0,
            "energy_now": 0.0, "energy_full": 0.0, "energy_design": 0.0, "health": None, "time_str": ""}
    if not path:
        return data

    data["capacity"] = _read(path, "capacity", int) or 0
    data["status"] = _read(path, "status") or "Unknown"

    e_now, e_full, e_design = (_read(path, n, int) for n in ("energy_now", "energy_full", "energy_full_design"))
    power = _read(path, "power_now", int)
    if e_now is None:  # charge-based batteries
        volts = (_read(path, "voltage_now", int) or 0) / 1e6
        c_now, c_full, c_design = (_read(path, n, int) for n in ("charge_now", "charge_full", "charge_full_design"))
        e_now, e_full, e_design = (int(c * volts) if c is not None else None for c in (c_now, c_full, c_design))
        current = _read(path, "current_now", int)
        if power is None and current is not None:
            power = int(current * volts)

    data["energy_now"] = (e_now or 0) / 1e6
    data["energy_full"] = (e_full or 0) / 1e6
    data["energy_design"] = (e_design or 0) / 1e6
    data["wattage"] = (power or 0) / 1e6
    if e_design:
        data["health"] = 100.0 * (e_full or 0) / e_design

    status = data["status"]
    if status == "Not charging" and conservation:
        data["status_text"] = "Held by Conservation Mode"
    elif status == "Not charging":
        data["status_text"] = "Plugged in, not charging"
    else:
        data["status_text"] = status

    if data["wattage"] > 0.1:
        if status == "Discharging":
            data["time_str"] = _fmt_hours(data["energy_now"] / data["wattage"], "remaining")
        elif status == "Charging" and data["energy_full"] > data["energy_now"]:
            data["time_str"] = _fmt_hours((data["energy_full"] - data["energy_now"]) / data["wattage"], "until full")
    return data


def _fmt_hours(hours, suffix):
    h = int(hours)
    m = int((hours - h) * 60)
    return f"About {h} h {m:02d} min {suffix}"
