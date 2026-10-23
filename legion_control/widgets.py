"""Reusable widgets: tooltip, icons, segmented buttons, the resizable keyboard preview and the colour picker."""
import colorsys
import os
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

from . import themes as T
from .assets.mdi_codepoints import CODEPOINTS


def hex_to_rgb(hex_val):
    hex_val = hex_val.lstrip("#")
    return tuple(int(hex_val[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in rgb))


class ToolTip:
    """Small label shown above a widget while hovering."""

    def __init__(self, widget, text, font):
        self.widget, self.text, self.font, self.win = widget, text, font, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.win or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() - 30
        self.win = tk.Toplevel(self.widget)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry(f"+{x}+{y}")
        tk.Label(self.win, text=self.text, bg="#1a1a1a", fg=T.TEXT, font=self.font, padx=8, pady=3).pack()

    def hide(self, _event=None):
        if self.win:
            self.win.destroy()
            self.win = None


_icon_cache = {}
_ICON_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "mdi-subset.ttf")


def icon(name, color, size=24):
    """
    A Material Design Icon (see assets/mdi_codepoints.py for the available names) as a CTkImage.
    Rendered at 2x from the bundled icon font so it stays sharp. Cached per name/colour/size.
    """
    key = (name, color, size)
    if key not in _icon_cache:
        font = ImageFont.truetype(_ICON_FONT, size * 2)
        img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((size, size), chr(CODEPOINTS[name]), font=font, fill=color, anchor="mm")
        _icon_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _icon_cache[key]


def icon_image(name, color, size):
    """Same glyph as a plain PIL image (for the tray icon)."""
    font = ImageFont.truetype(_ICON_FONT, size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size / 2, size / 2), chr(CODEPOINTS[name]), font=font, fill=color, anchor="mm")
    return img


def battery_icon_name(capacity, charging):
    """mdi battery glyph for a level, e.g. battery-70 or battery-charging-80."""
    if charging:
        return "battery-charging-" + str(min((20, 50, 80, 100), key=lambda v: abs(v - capacity)))
    if capacity >= 95:
        return "battery"
    if capacity < 5:
        return "battery-outline"
    return f"battery-{max(10, min(90, round(capacity / 10) * 10))}"


class Segmented(ctk.CTkFrame):
    """A row of buttons where one is active, coloured with the theme accent."""

    def __init__(self, master, values, command, font, width=48, expand=False):
        super().__init__(master, fg_color="#222", corner_radius=6)
        self.buttons = {}
        for v in values:
            b = ctk.CTkButton(self, text=v, width=width, height=28, corner_radius=4, border_width=0, font=font,
                              fg_color="transparent", text_color="#aaa", hover_color="#333",
                              command=lambda v=v: command(v))
            b.pack(side="left", padx=1, pady=1, fill="x" if expand else None, expand=expand)
            self.buttons[v] = b

    def set_active(self, value, accent, on_accent):
        for v, b in self.buttons.items():
            if v == value:
                b.configure(fg_color=accent, text_color=on_accent, hover_color=accent)
            else:
                b.configure(fg_color="transparent", text_color="#aaa", hover_color="#333")


def _legion5_gen6_keys():
    """
    Key rectangles (x1, y1, x2, y2) of the Legion 5 Gen 6 (15ACH6H) keyboard, measured from a photo of the part,
    in a 1400 x 535 layout space. Returns (keys, body_outline_polygon).
    """
    keys = []

    def run(x, y1, y2, n, pitch=79.5, w=72):
        for i in range(n):
            keys.append((x + i * pitch, y1, x + i * pitch + w, y2))

    def numpad(y1, y2, n=3):
        for i in range(n):
            keys.append((1145 + i * 65, y1, 1200 + i * 65, y2))

    fw = (1380 - 19 * 8) / 20  # function row: 20 equal keys, Esc to PgDn
    for i in range(20):
        keys.append((10 + i * (fw + 8), 22, 10 + i * (fw + 8) + fw, 62))
    keys.append((10, 85, 65, 145))                      # `
    run(72, 85, 145, 12)                                # 1 ... =
    keys.append((1025, 85, 1135, 145))                  # Backspace
    numpad(85, 145, 4)                                  # NumLock / * -
    keys.append((10, 155, 105, 215))                    # Tab
    run(112, 155, 215, 13)                              # Q ... backslash
    numpad(155, 215)                                    # 7 8 9
    keys.append((1340, 155, 1390, 290))                 # numpad + (two rows tall)
    keys.append((10, 230, 130, 295))                    # CapsLk
    run(137, 230, 295, 11)                              # A ... '
    keys.append((1010, 230, 1135, 295))                 # Enter
    numpad(230, 295)                                    # 4 5 6
    keys.append((10, 305, 175, 370))                    # Shift
    run(182, 305, 370, 10)                              # Z ... /
    keys.append((976, 305, 1135, 370))                  # Shift
    numpad(305, 370)                                    # 1 2 3
    keys.append((1340, 305, 1390, 440))                 # numpad Enter (two rows tall)
    for x1, x2 in ((10, 95), (102, 172), (180, 258), (265, 337), (345, 725), (733, 800), (808, 880)):
        keys.append((x1, 390, x2, 455))                 # Ctrl Fn Win Alt Space Alt Ctrl
    keys.append((976, 380, 1046, 440))                  # Up
    keys.append((1145, 380, 1265, 440))                 # numpad 0 (double wide)
    keys.append((1275, 380, 1330, 440))                 # numpad .
    for x1, x2 in ((890, 965), (976, 1046), (1056, 1135)):
        keys.append((x1, 448, x2, 515))                 # Left Down Right (below the bottom row)
    body = [(0, 10), (1400, 10), (1400, 462), (1142, 462), (1142, 525), (882, 525), (882, 462), (0, 462)]
    return keys, body


_KEYS, _BODY = _legion5_gen6_keys()
_LAYOUT_W, _LAYOUT_H = 1400, 535
# Zones by key centre: the main block in thirds, then the numpad (with Home/End/PgUp/PgDn above it)
_ZONE_SPLITS = (380, 760, 1140)
_ZONE_BANDS = ((10, 380), (380, 760), (760, 1140), (1140, 1390))


def _zone_of(x):
    return next((i for i, edge in enumerate(_ZONE_SPLITS) if x < edge), 3)


_KEY_ZONES = [_zone_of((k[0] + k[2]) / 2) for k in _KEYS]


class KeyboardPreview(tk.Canvas):
    """
    Drawing of the Legion 5 Gen 6 keyboard with each key lit in its zone's colour.
    Re-renders at its real pixel size when resized. on_click(zone) gets 0-3, or -1 when clicking off the keys.
    """
    ASPECT = _LAYOUT_H / _LAYOUT_W + 0.02

    def __init__(self, master, on_click):
        super().__init__(master, height=160, bg=T.CARD, highlightthickness=0, bd=0, cursor="hand2")
        self.on_click = on_click
        self.colors = ["000000"] * 4
        self.selected = -1
        self.solo = False
        self.ring_bright = True
        self.ring_color = "#ffffff"
        self.accent = "#39c5bb"
        self._xform = None  # (offset_x, offset_y, scale) from layout space to canvas pixels
        self._photo = None
        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_click)

    def _on_resize(self, event):
        h = max(100, int(event.width * self.ASPECT))
        if int(self.cget("height")) != h:
            self.configure(height=h)
        self.redraw()

    def update_state(self, colors, selected, solo, ring_bright, ring_color, accent):
        state = (tuple(colors), selected, solo, ring_bright, ring_color, accent)
        if state == (tuple(self.colors), self.selected, self.solo, self.ring_bright, self.ring_color, self.accent):
            return
        self.colors, self.selected, self.solo = list(colors), selected, solo
        self.ring_bright, self.ring_color, self.accent = ring_bright, ring_color, accent
        self.redraw()

    def redraw(self):
        w, h = self.winfo_width(), int(self.cget("height"))
        if w < 50:
            return
        self._photo = ImageTk.PhotoImage(self.render(w, h))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)

    def render(self, w, h):
        """The drawing as a PIL image of w x h pixels (also records the transform used for clicks)."""
        ss = 2  # supersample
        W, H = w * ss, h * ss
        scale = min(W / _LAYOUT_W, H / _LAYOUT_H)
        ox, oy = (W - _LAYOUT_W * scale) / 2, (H - _LAYOUT_H * scale) / 2
        self._xform = (ox / ss, oy / ss, scale / ss)

        def pt(x, y):
            return ox + x * scale, oy + y * scale

        img = Image.new("RGBA", (W, H), hex_to_rgb(T.CARD) + (255,))
        d = ImageDraw.Draw(img)
        d.polygon([pt(x, y) for x, y in _BODY], fill=(24, 24, 27, 255), outline=(62, 62, 68, 255))
        rad = max(2, int(7 * scale))
        lit = [hex_to_rgb(c) for c in self.colors]
        ring = hex_to_rgb(self.accent if self.ring_bright else self.ring_color)
        for (x1, y1, x2, y2), zone in zip(_KEYS, _KEY_ZONES):
            a, b = pt(x1, y1), pt(x2, y2)
            rgb = lit[zone]
            on = rgb != (0, 0, 0) and not (self.solo and self.selected not in (-1, zone))
            if on:
                d.rounded_rectangle([a[0] - 3, a[1] - 3, b[0] + 3, b[1] + 3], radius=rad + 2,
                                    fill=rgb + (65,))  # backlight bleed
                fill = tuple(min(255, int(c * 0.8 + 35)) for c in rgb)
            else:
                fill = (42, 42, 47)
            d.rounded_rectangle([a, b], radius=rad, fill=fill + (255,), outline=(0, 0, 0, 110), width=2)
            if zone == self.selected:
                d.rounded_rectangle([a[0] - 2, a[1] - 2, b[0] + 2, b[1] + 2], radius=rad + 2,
                                    outline=ring + (255,), width=5 if self.ring_bright else 2)
        return img.resize((w, h), Image.LANCZOS)

    def zone_bounds(self):
        """(x_left, x_right) of each zone in canvas pixels, for lining up the zone buttons."""
        if not self._xform:
            return []
        ox, _oy, sc = self._xform
        return [(ox + a * sc, ox + b * sc) for a, b in _ZONE_BANDS]

    def _on_click(self, event):
        if self._xform:
            ox, oy, sc = self._xform
            x, y = (event.x - ox) / sc, (event.y - oy) / sc
            for (x1, y1, x2, y2), zone in zip(_KEYS, _KEY_ZONES):
                if x1 - 4 <= x <= x2 + 4 and y1 - 4 <= y <= y2 + 4:  # small margin covers the gaps
                    return self.on_click(zone)
        self.on_click(-1)


class ColorPicker(ctk.CTkFrame):
    """
    Saturation/value square plus a hue bar. on_change(hex) is called while dragging.
    The square is rebuilt with PIL gradient compositing (fast) and cached per hue.
    """

    def __init__(self, master, on_change, height=170):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.hue, self.sat, self.val = 180.0, 1.0, 1.0
        self.h = height
        self.sv = tk.Canvas(self, height=height, bg="#000", highlightthickness=0, bd=0, cursor="crosshair")
        self.hue_bar = tk.Canvas(self, width=26, height=height, bg="#000", highlightthickness=0, bd=0,
                                 cursor="sb_v_double_arrow")
        self.sv.pack(side="left", fill="x", expand=True)
        self.hue_bar.pack(side="left", padx=(10, 0))
        self._sv_base = None  # (hue, size, image)
        self._photos = {}
        self.sv.bind("<Configure>", lambda e: self.redraw())
        for ev in ("<Button-1>", "<B1-Motion>"):
            self.sv.bind(ev, self._drag_sv)
            self.hue_bar.bind(ev, self._drag_hue)

    def set_hex(self, hex_val):
        r, g, b = (c / 255 for c in hex_to_rgb(hex_val))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s > 0 and v > 0:  # keep the hue when picking greys/black
            self.hue = h * 360
        self.sat, self.val = s, v
        self.redraw()

    def hex(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue / 360, self.sat, self.val)
        return rgb_to_hex((r * 255, g * 255, b * 255))

    def _drag_sv(self, e):
        w = max(1, self.sv.winfo_width() - 1)
        self.sat = min(1, max(0, e.x / w))
        self.val = 1 - min(1, max(0, e.y / (self.h - 1)))
        self.redraw()
        self.on_change(self.hex())

    def _drag_hue(self, e):
        self.hue = (1 - min(1, max(0, e.y / (self.h - 1)))) * 360
        self.redraw()
        self.on_change(self.hex())

    def redraw(self):
        w, h = self.sv.winfo_width(), self.h
        if w < 10:
            return
        if not self._sv_base or self._sv_base[:2] != (round(self.hue, 1), (w, h)):
            grad = Image.linear_gradient("L")  # value = row
            x_mask = grad.transpose(Image.Transpose.TRANSPOSE).resize((w, h))  # value = column
            y_mask = ImageOps.invert(grad).resize((w, h))
            hr, hg, hb = colorsys.hsv_to_rgb(self.hue / 360, 1, 1)
            saturated = Image.composite(Image.new("RGB", (w, h), (int(hr * 255), int(hg * 255), int(hb * 255))),
                                        Image.new("RGB", (w, h), "white"), x_mask)
            self._sv_base = (round(self.hue, 1), (w, h), Image.composite(saturated, Image.new("RGB", (w, h)), y_mask))
        img = self._sv_base[2].copy()
        d = ImageDraw.Draw(img)
        cx, cy = self.sat * (w - 1), (1 - self.val) * (h - 1)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline="#000", width=3)
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline="#fff", width=2)
        self._photos["sv"] = ImageTk.PhotoImage(img)
        self.sv.delete("all")
        self.sv.create_image(0, 0, anchor="nw", image=self._photos["sv"])

        if "hue_base" not in self._photos or self._photos["hue_base"][0] != h:
            col = Image.new("RGB", (1, h))
            col.putdata([tuple(int(c * 255) for c in colorsys.hsv_to_rgb(1 - y / h, 1, 1)) for y in range(h)])
            self._photos["hue_base"] = (h, col.resize((26, h)))
        bar = self._photos["hue_base"][1].copy()
        hy = (1 - self.hue / 360) * (h - 1)
        ImageDraw.Draw(bar).rectangle([0, hy - 2, 25, hy + 2], outline="#fff", width=2)
        self._photos["hue"] = ImageTk.PhotoImage(bar)
        self.hue_bar.delete("all")
        self.hue_bar.create_image(0, 0, anchor="nw", image=self._photos["hue"])
