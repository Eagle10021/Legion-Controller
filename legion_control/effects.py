"""Software lighting effects: computed frame by frame and sent to the keyboard in hardware 'static' mode."""
import math
import random

HARDWARE_EFFECTS = ["static", "breath", "wave", "hue", "off"]
SOFTWARE_EFFECTS = ["Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]
ALL_EFFECTS = HARDWARE_EFFECTS + SOFTWARE_EFFECTS

# Display names for the effect menu (stored values stay the same for profile compatibility)
EFFECT_LABELS = {
    "static": "Static", "breath": "Breath", "wave": "Wave (hardware)", "hue": "Hue cycle", "off": "Off",
    "Police": "Police", "Scanner": "Scanner", "Heartbeat": "Heartbeat", "Fire": "Fire",
    "Battery": "Battery gauge", "Soft Wave": "Soft wave",
}

# Icons for the effect buttons (names from assets/mdi_codepoints.py)
EFFECT_ICONS = {
    "static": "palette", "breath": "weather-night", "wave": "waves", "hue": "palette-swatch-variant",
    "off": "lightbulb-off-outline", "Police": "police-badge", "Scanner": "radar", "Heartbeat": "heart-pulse",
    "Fire": "fire", "Battery": "battery-heart-variant", "Soft Wave": "gradient-horizontal",
}
SHORT_LABELS = {"wave": "Wave", "hue": "Hue", "Battery": "Battery"}


def is_software(effect):
    return effect in SOFTWARE_EFFECTS


def frame_delay(effect, speed, step):
    """Milliseconds until the next frame."""
    if effect == "Fire":
        return {1: 250, 2: 150, 3: 80, 4: 40}.get(speed, 100)
    if effect == "Scanner":
        return {1: 400, 2: 250, 3: 120, 4: 60}.get(speed, 150)
    if effect == "Police":
        return {1: 600, 2: 350, 3: 180, 4: 90}.get(speed, 350)
    if effect == "Heartbeat":
        return {0: 120, 1: 180, 2: 120}.get(step % 4, 1200)  # two quick beats, then a pause
    return {1: 800, 2: 400, 3: 200, 4: 100}.get(speed, 400)


def frame(effect, step, colors, direction="LTR", battery=None, thresholds=(15, 75, 95)):
    """
    Colours for the 4 zones at this step.
    colors: the 4 assigned zone colours ('rrggbb'); battery: dict from battery.read_battery
    thresholds: (low alert %, green from %, full bar from %)
    """
    off = ["000000"] * 4
    if effect == "Police":
        return ["ff0000"] * 2 + ["0000ff"] * 2 if step % 2 == 0 else ["0000ff"] * 2 + ["ff0000"] * 2
    if effect == "Scanner":
        res = list(off)
        res[[0, 1, 2, 3, 2, 1][step % 6]] = colors[0]
        return res
    if effect == "Heartbeat":
        return list(colors) if step % 4 in (0, 2) else off
    if effect == "Fire":
        return [f"{random.randint(180, 255):02x}{random.randint(0, 80):02x}00" for _ in range(4)]
    if effect == "Battery":
        return _battery_gauge(step, battery or {}, thresholds)
    if effect == "Soft Wave":
        if direction == "RTL":
            return [colors[(step + i) % 4] for i in range(4)]
        return [colors[(step - i) % 4] for i in range(4)]
    return off


def _battery_gauge(step, battery, thresholds):
    low, green, full = thresholds
    p = float(battery.get("capacity", 0))
    charging = battery.get("status") == "Charging"
    if p <= low:
        if charging:
            return ["ff0000", "000000", "000000", "000000"]  # plugged in: calm acknowledgement
        return ["ff0000" if step % 2 == 0 else "000000"] * 4  # discharging: alarm
    count = 4 if p >= full else 3 if p >= 50 else 2 if p >= 25 else 1
    base = (0, 255, 0) if p >= green else (200, 200, 0) if p >= 45 else (255, 120, 0) if p >= 20 else (255, 0, 0)
    pulse = 0.7 + 0.3 * abs(math.sin(step * 0.2))
    active = "{:02x}{:02x}{:02x}".format(*(int(c * pulse) for c in base))
    return [active if i < count else "000000" for i in range(4)]
