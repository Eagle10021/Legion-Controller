"""Legion Control main window."""
import json
import logging
import os
import queue
import re
import secrets
import socket
import threading
import tkinter.font as tkfont
from tkinter import filedialog

import customtkinter as ctk
import pystray

from . import battery as batt
from . import effects as fx
from . import settings as cfg
from . import sysinfo
from . import themes as T
from .ha_link import HALink
from .hardware import LedController, PowerController, read_platform_profile, set_platform_profile
from .widgets import (ColorPicker, KeyboardPreview, Segmented, ToolTip, battery_icon_name, hex_to_rgb, icon,
                      icon_image, rgb_to_hex)

log = logging.getLogger(__name__)

INSTANCE_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "legion-control.sock")
CHARGE_MODES = [("Normal Charging", "Normal", "power-plug"), ("Conservation Mode", "Conservation", "leaf"),
                ("Rapid Charge", "Rapid", "flash")]
PROFILE_NAMES = {"low-power": "Quiet", "balanced": "Balanced", "performance": "Performance", "custom": "Custom"}
# Words Home Assistant (or a voice assistant) may send for charging modes and power profiles
CHARGE_MODE_WORDS = {"normal": "Normal Charging", "conservation": "Conservation Mode", "rapid": "Rapid Charge"}
PROFILE_WORDS = {"quiet": "low-power", "low-power": "low-power", "low power": "low-power", "balanced": "balanced",
                 "performance": "performance", "custom": "custom"}
NEUTRAL_BORDER = ["#979DA2", "#565B5E"]  # CustomTkinter's default entry border


def pick_font(*candidates):
    families = set(tkfont.families())
    return next((c for c in candidates if c in families), "TkDefaultFont")


class LegionApp(ctk.CTk):
    def __init__(self, app_dir):
        super().__init__(className="legioncontrol")
        self.app_dir = app_dir
        self.title("Legion Control")
        ctk.set_appearance_mode("Dark")
        self.minsize(960, 660)
        self.geometry("1140x820")
        self.configure(fg_color="#000000")

        self.F = pick_font("Noto Sans", "Inter", "Cantarell", "DejaVu Sans")
        self.FM = pick_font("Noto Sans Mono", "JetBrains Mono", "DejaVu Sans Mono")

        # Hardware
        try:
            self.led = LedController()
        except Exception as e:  # pyusb backend missing etc.
            log.error("USB init failed: %s", e)
            self.led = None
        self.power = PowerController()
        self.battery_path = batt.find_battery()

        # Settings and state
        self.conf = cfg.load(app_dir)
        self.profiles = self.conf["profiles"]
        self.theme_var = ctk.StringVar(value=self.conf["theme"] if self.conf["theme"] in T.THEMES else T.DEFAULT_THEME)
        self.live_preview = ctk.BooleanVar(value=self.conf["live_preview"])
        self.profile_var = ctk.StringVar(value=self.conf["current_profile"])
        self.effect = "static"
        self.brightness = "Low"
        self.speed = 2
        self.direction = "LTR"
        self.colors = ["39c5bb"] * 4
        self.last_on = ["39c5bb"] * 4
        self.selected = -1
        self.history = list(self.conf["color_history"])
        self.pref_blink_opposite = ctk.BooleanVar(value=self.conf["pref_blink_opposite"])
        self.pref_solo = ctk.BooleanVar(value=self.conf["pref_solo_mode"])
        self.thresholds = [self.conf["pref_batt_low"], self.conf["pref_batt_green"], self.conf["pref_batt_full"]]
        self.charge_mode = self.power.current_mode()
        self.blink_on = True
        self.sw_step = 0
        self.sw_colors = ["000000"] * 4
        self.battery = batt.read_battery(self.battery_path, self.power.get_conservation())
        self.sysinfo = cfg.load_json(cfg.SYSINFO_CACHE)
        self._save_job = None
        self._loading = True
        self._ui_calls = queue.Queue()  # work from background threads, run on the UI thread by command_loop

        self.ha = HALink(self.conf["home_assistant"])

        self.build_ui()
        self.load_profile(self.profile_var.get(), apply=False)
        self.apply_theme()
        self.apply_settings()
        self._loading = False

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.setup_tray()
        self.start_instance_listener()
        self.after(200, self.battery_loop)
        self.after(600, self.blink_loop)
        self.after(100, self.sw_loop)
        self.after(250, self.command_loop)
        self.after(1000, self.ha_heartbeat)

    # ------------------------------------------------------------------ helpers
    def font(self, size, weight="normal"):
        return (self.F, size, weight)

    @property
    def accent(self):
        return T.theme(self.theme_var.get())["accent"]

    @property
    def on_accent(self):
        return T.theme(self.theme_var.get())["on_accent"]

    def label(self, parent, text="", size=12, weight="normal", color=T.TEXT_SEC, **kw):
        return ctk.CTkLabel(parent, text=text, font=self.font(size, weight), text_color=color, **kw)

    def card(self, parent, title, icon_name):
        """A section card: accent line, icon + title, and a body frame that is returned."""
        card = ctk.CTkFrame(parent, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.CARD_BORDER)
        line = ctk.CTkFrame(card, height=3, fg_color=self.accent, corner_radius=2)
        line.pack(fill="x", padx=14, pady=(0, 0))
        self.accent_lines.append(line)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(10, 4))
        icon_lbl = ctk.CTkLabel(head, text="", image=icon(icon_name, self.accent, 18))
        icon_lbl.pack(side="left", padx=(0, 8))
        self.accent_icons.append((icon_lbl, icon_name, 18))
        self.label(head, title, 12, "bold", T.TEXT_SEC).pack(side="left")
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        return card, body

    def icon_button(self, parent, name, tip, command, size=18):
        b = ctk.CTkButton(parent, text="", image=icon(name, "#d6d6d6", size), width=36, height=34,
                          fg_color=T.FIELD, hover_color=T.FIELD_HOVER, corner_radius=8, command=command)
        ToolTip(b, tip, self.font(10))
        return b

    def option_menu(self, parent, **kw):
        return ctk.CTkOptionMenu(parent, font=self.font(12), dropdown_font=self.font(12), fg_color=T.FIELD,
                                 button_color=T.FIELD, button_hover_color=T.FIELD_HOVER, corner_radius=8, **kw)

    # ------------------------------------------------------------------ layout
    def build_ui(self):
        self.accent_lines, self.accent_icons = [], []
        root = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=14, border_width=1, border_color="#222")
        root.pack(fill="both", expand=True, padx=8, pady=8)
        root.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")

        # Header
        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(18, 10))
        self.logo = ctk.CTkLabel(header, text="", image=icon("lightning-bolt", self.accent, 34))
        self.logo.pack(side="left", padx=(0, 10))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left")
        self.label(titles, "LEGION CONTROL", 22, "bold", T.TEXT).pack(anchor="w")
        self.label(titles, self.sysinfo.get("Device") or sysinfo.device_name(), 11, color=T.TEXT_DIM).pack(anchor="w")
        self.icon_button(header, "cog", "Settings", self.show_settings).pack(side="right", padx=(6, 0))
        self.icon_button(header, "information-outline", "System information",
                         self.show_system_info).pack(side="right", padx=(6, 0))
        self.theme_menu = self.option_menu(header, variable=self.theme_var, values=list(T.THEMES), width=150,
                                           height=34, command=lambda _v: self.apply_theme())
        self.theme_menu.pack(side="right", padx=(6, 0))
        self.label(header, "Theme", 11, color=T.TEXT_DIM).pack(side="right", padx=(0, 4))

        # Footer
        footer = ctk.CTkFrame(root, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=26, pady=(6, 18))
        self.live_switch = ctk.CTkSwitch(footer, text="Live preview", variable=self.live_preview, font=self.font(13),
                                         text_color=T.TEXT_SEC, command=self.on_live_toggle)
        self.live_switch.pack(side="left")
        ToolTip(self.live_switch, "Send every change to the keyboard straight away", self.font(10))
        self.status = self.label(footer, "", 12, color=T.TEXT_DIM)
        self.status.pack(side="left", padx=18)
        self.apply_btn = ctk.CTkButton(footer, text="APPLY", image=icon("check", "#000000", 18), compound="left",
                                       height=42, width=170, font=self.font(14, "bold"), corner_radius=10,
                                       command=lambda: self.apply_settings(manual=True))
        self.apply_btn.pack(side="right")
        self.ha_pill = ctk.CTkButton(footer, text="", image=icon("home-assistant", T.TEXT_DIM, 16), compound="left",
                                     height=28, fg_color=T.FIELD, hover_color=T.FIELD_HOVER, corner_radius=14,
                                     font=self.font(11), text_color=T.TEXT_SEC, command=self.show_settings)
        self.ha_pill.pack(side="right", padx=12)
        ToolTip(self.ha_pill, "Home Assistant link (click for settings)", self.font(10))

        # Body: two columns sharing the width 2:3, scrolling when the window is short
        body = ctk.CTkScrollableFrame(root, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=14)
        body.grid_columnconfigure(0, weight=2, uniform="cols", minsize=330)
        body.grid_columnconfigure(1, weight=3, uniform="cols", minsize=480)
        body.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        self.build_battery(left)
        self.build_profiles(left)
        self.build_lighting(right)
        self.build_color(right)

    def build_battery(self, parent):
        card, body = self.card(parent, "BATTERY & POWER", "battery-heart-variant")
        card.pack(fill="x", pady=(0, 12))
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", pady=(4, 0))
        self.batt_icon = ctk.CTkLabel(top, text="")
        self.batt_icon.pack(side="left", padx=(0, 8))
        self.batt_pct = self.label(top, "--%", 34, "bold", T.TEXT)
        self.batt_pct.pack(side="left")
        self.batt_watts = self.label(top, "", 13, "bold")
        self.batt_watts.pack(side="right")
        self.batt_bar = ctk.CTkProgressBar(body, height=8, fg_color="#2c2c2c", corner_radius=4)
        self.batt_bar.pack(fill="x", pady=(8, 8))
        self.batt_status = self.label(body, "", 12, anchor="w")
        self.batt_status.pack(fill="x")

        rows = ctk.CTkFrame(body, fg_color="transparent")
        rows.pack(fill="x", pady=(10, 0))
        rows.grid_columnconfigure(2, weight=1)
        self.batt_rows = {}
        for r, (key, ic) in enumerate([("Charge", "battery-50"), ("Condition", "battery-heart-variant"),
                                       ("Power profile", "speedometer"), ("Estimate", "timer-outline")]):
            ctk.CTkLabel(rows, text="", image=icon(ic, T.TEXT_DIM, 16)).grid(row=r, column=0, padx=(0, 8), pady=3)
            self.label(rows, key, 12, anchor="w").grid(row=r, column=1, sticky="w")
            val = self.label(rows, "--", 12, "bold", T.TEXT, anchor="e")
            val.grid(row=r, column=2, sticky="e")
            self.batt_rows[key] = val

        ctk.CTkFrame(body, height=1, fg_color="#2a2a2a").pack(fill="x", pady=14)
        self.label(body, "Charging mode", 12, "bold").pack(anchor="w", pady=(0, 6))
        available = [m for m in CHARGE_MODES if m[0] == "Normal Charging"
                     or (m[0] == "Conservation Mode" and self.power.has_conservation)
                     or (m[0] == "Rapid Charge" and self.power.has_rapid)]
        modes = ctk.CTkFrame(body, fg_color="#222", corner_radius=8)
        modes.pack(fill="x")
        self.mode_btns = {}
        for i, (mode, text, ic) in enumerate(available):
            modes.grid_columnconfigure(i, weight=1, uniform="modes")
            b = ctk.CTkButton(modes, text=text, image=icon(ic, "#aaaaaa", 16), compound="left", height=34,
                              font=self.font(11, "bold"), fg_color="transparent", hover_color="#333",
                              text_color="#aaaaaa", corner_radius=6, command=lambda m=mode: self.set_charge_mode(m))
            b.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self.mode_btns[mode] = (b, ic)
        self.label(body, "Conservation keeps the battery around 60-80 % for a longer life; Rapid charges faster. "
                         "Changing it asks for your password.", 11, color=T.TEXT_DIM, wraplength=340,
                   justify="left").pack(anchor="w", pady=(8, 0))

    def build_profiles(self, parent):
        card, body = self.card(parent, "PROFILES", "content-save")
        card.pack(fill="x", pady=(0, 12))
        self.profile_menu = self.option_menu(body, variable=self.profile_var, values=list(self.profiles), height=32,
                                             command=lambda name: self.load_profile(name))
        self.profile_menu.pack(fill="x", pady=(4, 8))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        for i, (name, tip, cmd) in enumerate([("plus", "New profile from current settings", self.add_profile),
                                              ("content-save", "Save changes to this profile", self.save_profile),
                                              ("import", "Import profile", self.import_profile),
                                              ("export", "Export profile", self.export_profile),
                                              ("delete-outline", "Delete profile", self.delete_profile)]):
            row.grid_columnconfigure(i, weight=1, uniform="pbtn")
            self.icon_button(row, name, tip, cmd).grid(row=0, column=i, sticky="ew", padx=2)

    def build_lighting(self, parent):
        card, body = self.card(parent, "LIGHTING", "keyboard-variant")
        card.pack(fill="x", pady=(0, 12))
        card.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")

        self.effect_btns = {}
        for group, effects in (("Hardware", fx.HARDWARE_EFFECTS), ("Software", fx.SOFTWARE_EFFECTS)):
            self.label(body, group, 11, "bold", T.TEXT_DIM).pack(anchor="w", pady=(4, 3))
            grid = ctk.CTkFrame(body, fg_color="transparent")
            grid.pack(fill="x")
            for i, e in enumerate(effects):
                grid.grid_columnconfigure(i, weight=1, uniform=group)
                b = ctk.CTkButton(grid, text=fx.SHORT_LABELS.get(e, fx.EFFECT_LABELS[e]),
                                  image=icon(fx.EFFECT_ICONS[e], "#bbbbbb", 16), compound="left", height=34,
                                  font=self.font(11, "bold"), fg_color=T.FIELD, hover_color=T.FIELD_HOVER,
                                  text_color="#bbbbbb", corner_radius=8, command=lambda e=e: self.on_effect_picked(e))
                b.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
                ToolTip(b, fx.EFFECT_LABELS[e], self.font(10))
                self.effect_btns[e] = b

        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x", pady=(12, 0))
        self.controls_bar = bar
        b = ctk.CTkFrame(bar, fg_color="transparent")
        b.pack(side="left")
        self.label(b, "Brightness", 11, "bold", T.TEXT_DIM).pack(anchor="w")
        self.bright_seg = Segmented(b, ["OFF", "LOW", "HIGH"], self.on_brightness, self.font(10, "bold"), 56)
        self.bright_seg.pack(anchor="w", pady=(2, 0))
        s = ctk.CTkFrame(bar, fg_color="transparent")
        s.pack(side="right")
        self.label(s, "Animation speed", 11, "bold", T.TEXT_DIM).pack(anchor="e")
        self.speed_seg = Segmented(s, ["1", "2", "3", "4"], self.on_speed, self.font(10, "bold"), 42)
        self.speed_seg.pack(anchor="e", pady=(2, 0))

        self.wave_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.label(self.wave_frame, "Wave direction", 11, "bold", T.TEXT_DIM).pack(anchor="w", pady=(12, 2))
        self.wave_seg = Segmented(self.wave_frame, ["LTR", "RTL"], self.on_direction, self.font(10, "bold"),
                                  expand=True)
        self.wave_seg.pack(fill="x")

        self.preview = KeyboardPreview(body, self.select_zone)
        self.preview.pack(fill="x", pady=(16, 2))
        self.preview.bind("<Configure>", lambda e: self.after(10, self.place_zone_buttons), add="+")
        self.zone_row = ctk.CTkFrame(body, fg_color="transparent", height=40)
        self.zone_row.pack(fill="x")
        self.zone_btns = []
        for i in range(4):
            btn = ctk.CTkButton(self.zone_row, text=f"Zone {i + 1}", image=icon("power", "#ffffff", 14),
                                compound="left", width=88, height=30, corner_radius=15, font=self.font(10, "bold"),
                                fg_color="#222", hover_color="#333", command=lambda i=i: self.toggle_zone(i))
            ToolTip(btn, f"Turn zone {i + 1} on or off", self.font(10))
            self.zone_btns.append(btn)
        self.zone_hint = self.label(body, "", 11, color=T.TEXT_DIM)
        self.zone_hint.pack(pady=(6, 0))

    def place_zone_buttons(self):
        """Centre each zone button under its zone in the keyboard drawing."""
        bounds = self.preview.zone_bounds()
        scale = ctk.ScalingTracker.get_widget_scaling(self)  # place() scales x; the canvas works in real pixels
        for btn, (x1, x2) in zip(self.zone_btns, bounds):
            btn.place(x=(x1 + x2) / 2 / scale, rely=0.5, anchor="center")

    def build_color(self, parent):
        card, body = self.card(parent, "COLOUR", "palette")
        card.pack(fill="x", pady=(0, 12))
        self.picker = ColorPicker(body, self.on_picker_change)
        self.picker.pack(fill="x", pady=(4, 10))

        entries = ctk.CTkFrame(body, fg_color="transparent")
        entries.pack()
        f = ctk.CTkFrame(entries, fg_color="transparent")
        f.pack(side="left", padx=(0, 14))
        self.label(f, "HEX", 10, "bold", T.TEXT_DIM).pack()
        self.hex_entry = ctk.CTkEntry(f, width=96, height=30, font=(self.FM, 12), justify="center", border_width=1)
        self.hex_entry.pack()
        self.hex_entry.bind("<Return>", self.on_hex_entered)
        self.rgb_entries = []
        for name, col in [("R", "#ff6b6b"), ("G", "#5ee07a"), ("B", "#6b9bff")]:
            f = ctk.CTkFrame(entries, fg_color="transparent")
            f.pack(side="left", padx=4)
            self.label(f, name, 10, "bold", col).pack()
            e = ctk.CTkEntry(f, width=52, height=30, font=(self.FM, 12), justify="center", border_width=1)
            e.pack()
            e.bind("<Return>", self.on_rgb_entered)
            self.rgb_entries.append(e)

        lower = ctk.CTkFrame(body, fg_color="transparent")
        lower.pack(fill="x", pady=(14, 0))
        lower.grid_columnconfigure(1, weight=1)
        pre = ctk.CTkFrame(lower, fg_color="transparent")
        pre.grid(row=0, column=0, sticky="nw")
        self.label(pre, "PRESETS", 10, "bold", T.TEXT_DIM).pack(anchor="w")
        grid = ctk.CTkFrame(pre, fg_color="transparent")
        grid.pack(anchor="w", pady=(2, 0))
        for i, (name, col) in enumerate(T.PRESETS):
            b = ctk.CTkButton(grid, text="", width=24, height=24, corner_radius=12, fg_color="#" + col,
                              hover_color="#" + col, command=lambda c=col: self.set_color(c, remember=True))
            b.grid(row=i // 4, column=i % 4, padx=2, pady=2)
            ToolTip(b, name, self.font(10))

        mid = ctk.CTkFrame(lower, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="n", pady=(14, 0))
        for text, ic, cmd in [("Gradient Z1 → Z4", "gradient-horizontal", self.gradient),
                              ("Save to recent", "history", self.remember_current)]:
            ctk.CTkButton(mid, text=text, image=icon(ic, "#cccccc", 15), compound="left", height=30, width=150,
                          font=self.font(11), fg_color=T.FIELD, hover_color=T.FIELD_HOVER, corner_radius=8,
                          command=cmd).pack(pady=2)

        hist = ctk.CTkFrame(lower, fg_color="transparent")
        hist.grid(row=0, column=2, sticky="ne")
        self.label(hist, "RECENT", 10, "bold", T.TEXT_DIM).pack(anchor="w")
        hgrid = ctk.CTkFrame(hist, fg_color="transparent")
        hgrid.pack(anchor="w", pady=(2, 0))
        self.history_btns = []
        for i in range(12):
            b = ctk.CTkButton(hgrid, text="", width=24, height=24, corner_radius=6, fg_color="#2a2a2a",
                              hover_color="#333", border_width=1, border_color="#222")
            b.grid(row=i // 4, column=i % 4, padx=2, pady=2)
            self.history_btns.append(b)
        self.refresh_history()

    # ------------------------------------------------------------------ theme / control state
    def apply_theme(self):
        a, on = self.accent, self.on_accent
        self.apply_btn.configure(fg_color=a, hover_color=a, text_color=on, image=icon("check", on, 18))
        for line in self.accent_lines:
            line.configure(fg_color=a)
        for lbl, name, size in self.accent_icons:
            lbl.configure(image=icon(name, a, size))
        self.logo.configure(image=icon("lightning-bolt", a, 34))
        self.batt_bar.configure(progress_color=a)
        self.batt_watts.configure(text_color=a)
        self.live_switch.configure(progress_color=a)
        self.refresh_controls()
        self.refresh_charge_modes()
        self.refresh_battery_icon()
        self.schedule_save()

    def refresh_controls(self):
        a, on = self.accent, self.on_accent
        for e, b in self.effect_btns.items():
            active = e == self.effect
            b.configure(fg_color=a if active else T.FIELD, hover_color=a if active else T.FIELD_HOVER,
                        text_color=on if active else "#bbbbbb",
                        image=icon(fx.EFFECT_ICONS[e], on if active else "#bbbbbb", 16))
        self.bright_seg.set_active("OFF" if self.effect == "off" else self.brightness.upper(), a, on)
        self.speed_seg.set_active(str(self.speed), a, on)
        self.wave_seg.set_active(self.direction, a, on)
        if self.effect in ("wave", "Soft Wave"):
            self.wave_frame.pack(fill="x", after=self.controls_bar)
        else:
            self.wave_frame.pack_forget()
        for i, btn in enumerate(self.zone_btns):
            lit = self.colors[i] != "000000"
            sel = i == self.selected
            btn.configure(fg_color=a if sel else "#222", hover_color=a if sel else "#333",
                          text_color=on if sel else ("#dddddd" if lit else "#666666"),
                          image=icon("power" if lit else "power-off", on if sel else ("#ffffff" if lit else "#666666"),
                                     14))
        self.zone_hint.configure(text="Editing all zones. Click a zone on the keyboard to edit it alone."
                                 if self.selected == -1 else
                                 f"Editing zone {self.selected + 1}. Click outside the keys to edit all zones.")
        self.redraw_preview()

    def refresh_charge_modes(self):
        a, on = self.accent, self.on_accent
        for mode, (b, ic) in self.mode_btns.items():
            active = mode == self.charge_mode
            b.configure(fg_color=a if active else "transparent", hover_color=a if active else "#333",
                        text_color=on if active else "#aaaaaa", image=icon(ic, on if active else "#aaaaaa", 16))

    def refresh_battery_icon(self):
        b = self.battery
        self.batt_icon.configure(image=icon(battery_icon_name(b["capacity"], b["status"] == "Charging"),
                                            self.accent, 38))

    def redraw_preview(self):
        if fx.is_software(self.effect):
            shown = self.sw_colors
        elif self.effect == "off":
            shown = ["000000"] * 4
        else:
            shown = self.colors
        ring = "#ffffff" if self.pref_blink_opposite.get() else self.accent
        self.preview.update_state(shown, self.selected, self.pref_solo.get(), self.blink_on, ring, self.accent)

    # ------------------------------------------------------------------ zone / colour editing
    def select_zone(self, index):
        self.selected = index
        self.blink_on = True
        self.sync_color_fields(self.colors[index] if index != -1 else self.colors[0])
        self.refresh_controls()
        if self.live_preview.get():
            self.apply_settings()

    def targets(self):
        """Zones that colour edits apply to: the selected one, or all four when none is selected."""
        return [self.selected] if self.selected != -1 else [0, 1, 2, 3]

    def set_color(self, hex_val, remember=False, from_picker=False):
        hex_val = hex_val.lstrip("#").lower()
        for i in self.targets():
            self.colors[i] = hex_val
            if hex_val != "000000":
                self.last_on[i] = hex_val
        if self.effect == "off" and hex_val != "000000":
            self.effect = "static"  # picking a colour while the lights are off turns them on
        if not from_picker:
            self.picker.set_hex(hex_val)
        self.update_entries(hex_val)
        if remember:
            self.add_history(hex_val)
        self.changed()

    def sync_color_fields(self, hex_val):
        self.picker.set_hex(hex_val)
        self.update_entries(hex_val)

    def update_entries(self, hex_val):
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, "#" + hex_val.upper())
        for e, v in zip(self.rgb_entries, hex_to_rgb(hex_val)):
            e.delete(0, "end")
            e.insert(0, str(v))

    def on_picker_change(self, hex_val):
        self.set_color(hex_val, from_picker=True)

    def on_hex_entered(self, _e=None):
        val = self.hex_entry.get().strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", val):
            self.hex_entry.configure(border_color=NEUTRAL_BORDER)
            self.set_color(val, remember=True)
        else:
            self.hex_entry.configure(border_color=T.BAD)

    def on_rgb_entered(self, _e=None):
        try:
            rgb = [int(e.get()) for e in self.rgb_entries]
            if not all(0 <= c <= 255 for c in rgb):
                raise ValueError
        except ValueError:
            for e in self.rgb_entries:
                e.configure(border_color=T.BAD)
            return
        for e in self.rgb_entries:
            e.configure(border_color=NEUTRAL_BORDER)
        self.set_color(rgb_to_hex(rgb), remember=True)

    def toggle_zone(self, i):
        if self.colors[i] != "000000":
            self.last_on[i] = self.colors[i]
            self.colors[i] = "000000"
        else:
            self.colors[i] = self.last_on[i] if self.last_on[i] != "000000" else "39c5bb"
            if self.effect == "off":
                self.effect = "static"
        if self.selected == i:
            self.sync_color_fields(self.colors[i])
        self.changed()

    def gradient(self):
        c1, c4 = hex_to_rgb(self.colors[0]), hex_to_rgb(self.colors[3])
        for i, t in ((1, 1 / 3), (2, 2 / 3)):
            self.colors[i] = rgb_to_hex(a + (b - a) * t for a, b in zip(c1, c4))
            self.last_on[i] = self.colors[i]
        if self.selected in (1, 2):
            self.sync_color_fields(self.colors[self.selected])
        self.changed()

    def remember_current(self):
        self.add_history(self.colors[self.selected if self.selected != -1 else 0])

    def add_history(self, hex_val):
        hex_val = "#" + hex_val.lstrip("#").lower()
        if hex_val == "#000000":
            return
        if hex_val in self.history:
            self.history.remove(hex_val)
        self.history = [hex_val] + self.history[:11]
        self.refresh_history()
        self.schedule_save()

    def refresh_history(self):
        for i, b in enumerate(self.history_btns):
            if i < len(self.history):
                c = self.history[i]
                b.configure(fg_color=c, hover_color=c, state="normal", command=lambda c=c: self.set_color(c))
            else:
                b.configure(fg_color="#2a2a2a", hover_color="#2a2a2a", state="disabled")

    # ------------------------------------------------------------------ effect controls
    def on_effect_picked(self, effect):
        self.effect = effect
        self.sw_step = 0
        self.changed()

    def on_brightness(self, val):
        if val == "OFF":
            self.effect = "off"
        else:
            self.brightness = "Low" if val == "LOW" else "High"
            if self.effect == "off":
                self.effect = "static"
        self.changed()

    def on_speed(self, val):
        self.speed = int(val)
        self.changed()

    def on_direction(self, val):
        self.direction = val
        self.changed()

    def on_live_toggle(self):
        self.schedule_save()
        if self.live_preview.get():
            self.apply_settings()

    def changed(self):
        """Something about the lighting changed: refresh the UI, push to the keyboard if live, save soon."""
        self.refresh_controls()
        if self.live_preview.get():
            self.apply_settings()
        self.schedule_save()
        self.publish_ha()

    # ------------------------------------------------------------------ talking to the keyboard
    def apply_settings(self, manual=False, blink=False):
        """Send the current lighting to the keyboard. Blink frames dim/invert the selected zone."""
        if not self.led or not self.led.available:
            self.set_status("Keyboard lighting controller not found")
            return
        effect = self.effect
        software = fx.is_software(effect)
        hw_effect = "static" if software else effect
        source = self.sw_colors if software else self.colors
        colors = []
        for i, c in enumerate(source):
            if blink and not self.blink_on and i == self.selected:
                colors.append(rgb_to_hex(255 - v for v in hex_to_rgb(c)) if self.pref_blink_opposite.get()
                              else rgb_to_hex(v * 0.3 for v in hex_to_rgb(c)))
            elif self.pref_solo.get() and self.selected != -1 and i != self.selected and not software:
                colors.append("000000")
            else:
                colors.append(c)
        # All-black static is sent as the firmware's real "off" (brightness 0), not black at low brightness
        if hw_effect == "static" and all(c == "000000" for c in colors) and not software:
            hw_effect = "off"
        data = self.led.build_control_string(hw_effect, colors, self.speed, 2 if self.brightness == "High" else 1,
                                             self.direction if hw_effect == "wave" else None)
        ok = self.led.send_control_string(data)
        if not ok:
            self.set_status("Couldn't write to the keyboard (see terminal)")
        elif manual:
            self.set_status("Applied")
            self.schedule_save()
            self.publish_ha()

    def set_status(self, text):
        self.status.configure(text=text)
        if text == "Applied":
            self.after(2000, lambda: self.status.cget("text") == "Applied" and self.status.configure(text=""))

    # ------------------------------------------------------------------ loops
    def blink_loop(self):
        """Pulse the selected zone (preview always; keyboard too when live preview is on)."""
        if self.selected != -1:
            self.blink_on = not self.blink_on
            self.redraw_preview()
            if self.live_preview.get() and self.effect in ("static", "breath"):
                self.apply_settings(blink=True)
        self.after(600, self.blink_loop)

    def sw_loop(self):
        if fx.is_software(self.effect):
            battery = self.battery if self.effect == "Battery" else None
            self.sw_colors = fx.frame(self.effect, self.sw_step, self.colors, self.direction, battery,
                                      tuple(self.thresholds))
            self.apply_settings()
            self.redraw_preview()
            self.sw_step += 1
        self.after(fx.frame_delay(self.effect, self.speed, self.sw_step), self.sw_loop)

    def battery_loop(self):
        self.battery = b = batt.read_battery(self.battery_path, self.power.get_conservation())
        low = b["status"] == "Discharging" and b["capacity"] <= self.thresholds[0]
        self.batt_pct.configure(text=f"{b['capacity']}%", text_color=T.BAD if low else T.TEXT)
        self.batt_bar.set(b["capacity"] / 100)
        self.refresh_battery_icon()
        sign = "+" if b["status"] == "Charging" else "−" if b["status"] == "Discharging" else ""
        self.batt_watts.configure(text=f"{sign}{b['wattage']:.1f} W" if b["wattage"] else "")
        self.batt_status.configure(text=b["status_text"])
        self.batt_rows["Charge"].configure(text=f"{b['energy_now']:.1f} / {b['energy_full']:.1f} Wh")
        if b["health"] is not None:
            colour = T.TEXT if b["health"] > 80 else T.WARN if b["health"] > 60 else T.BAD
            self.batt_rows["Condition"].configure(text=f"{b['health']:.1f} %  ({b['energy_full']:.1f} of "
                                                       f"{b['energy_design']:.1f} Wh)", text_color=colour)
        profile = read_platform_profile()
        self.batt_rows["Power profile"].configure(text=PROFILE_NAMES.get(profile, profile or "n/a"))
        self.batt_rows["Estimate"].configure(text=b["time_str"].replace("About ", "") or "—")
        mode = self.power.current_mode()
        if mode != self.charge_mode:  # changed elsewhere (Fn keys, another tool)
            self.charge_mode = mode
            self.refresh_charge_modes()
        self.refresh_ha_pill()
        self.after(2000, self.battery_loop)

    def refresh_ha_pill(self):
        status = self.ha.status
        if status == "Off":
            self.ha_pill.configure(text="HA off", image=icon("home-assistant", T.TEXT_DIM, 16))
        elif status == "Connected":
            self.ha_pill.configure(text="HA connected", image=icon("home-assistant", "#41bdf5", 16))
        else:
            self.ha_pill.configure(text="HA " + ("connecting" if status == "Connecting" else "error"),
                                   image=icon("home-assistant", T.WARN, 16))

    def call_soon(self, fn):
        """Run fn on the UI thread (safe to call from any thread)."""
        self._ui_calls.put(fn)

    def command_loop(self):
        """Run work queued by background threads and commands from the Home Assistant link (on the UI thread)."""
        while True:
            try:
                self._ui_calls.get_nowait()()
            except queue.Empty:
                break
            except Exception:
                log.exception("Background task callback failed")
        while True:
            try:
                cmd = self.ha.commands.get_nowait()
            except queue.Empty:
                break
            try:
                self.handle_command(cmd)
            except Exception:
                log.exception("Home Assistant command failed: %s", cmd)
        self.after(250, self.command_loop)

    def ha_heartbeat(self):
        self.publish_ha(force=True)
        self.after(30000, self.ha_heartbeat)

    # ------------------------------------------------------------------ Home Assistant
    def snapshot(self):
        b = self.battery
        return {
            "battery": {"capacity": b["capacity"], "status_text": b["status_text"], "wattage": round(b["wattage"]),
                        "health": round(b["health"], 1) if b["health"] is not None else None,
                        "time_str": b["time_str"]},
            "charge_mode": self.charge_mode,
            "power_profile": read_platform_profile(),
            "theme": self.theme_var.get(),
            "keyboard": {"effect": self.effect, "effect_label": fx.EFFECT_LABELS.get(self.effect, self.effect),
                         "colors": list(self.colors), "brightness": "Off" if self.effect == "off" else self.brightness,
                         "speed": self.speed, "profile": self.profile_var.get(), "profiles": list(self.profiles),
                         "effects": fx.ALL_EFFECTS},
        }

    def publish_ha(self, force=False):
        if self.ha.enabled:
            self.ha.publish(self.snapshot(), force=force)

    def handle_command(self, cmd):
        """
        Apply a command from Home Assistant. Keyboard: effect, color, colors, brightness, speed, profile.
        Power: charge_mode (normal / conservation / rapid) and power_profile (quiet / balanced / performance).
        """
        log.info("HA command: %s", cmd)
        word = str(cmd.get("charge_mode", "")).strip().lower()
        mode = next((m for k, m in CHARGE_MODE_WORDS.items() if word.startswith(k) or word == m.lower()), None)
        if mode:
            self.set_charge_mode(mode)
        profile = PROFILE_WORDS.get(str(cmd.get("power_profile", "")).strip().lower())
        if profile:
            self.set_power_profile(profile)
        if not any(k in cmd for k in ("effect", "color", "colors", "brightness", "speed", "profile")):
            return  # power-only command: leave the keyboard alone
        if cmd.get("profile") in self.profiles:
            self.load_profile(cmd["profile"], apply=False)
        eff = str(cmd.get("effect", "")).strip()
        if eff:
            match = next((k for k, v in fx.EFFECT_LABELS.items() if eff.lower() in (k.lower(), v.lower())), None)
            if match:
                self.effect, self.sw_step = match, 0
        hex_re = r"#?[0-9a-fA-F]{6}"
        if isinstance(cmd.get("color"), str) and re.fullmatch(hex_re, cmd["color"]):
            self.colors = [cmd["color"].lstrip("#").lower()] * 4
            if self.effect == "off":
                self.effect = "static"
        if isinstance(cmd.get("colors"), list) and len(cmd["colors"]) == 4 and all(
                isinstance(c, str) and re.fullmatch(hex_re, c) for c in cmd["colors"]):
            self.colors = [c.lstrip("#").lower() for c in cmd["colors"]]
        bright = str(cmd.get("brightness", "")).lower()
        if bright == "off":
            self.effect = "off"
        elif bright in ("low", "high"):
            self.brightness = bright.capitalize()
            if self.effect == "off":
                self.effect = "static"
        if str(cmd.get("speed", "")) in ("1", "2", "3", "4"):
            self.speed = int(cmd["speed"])
        self.last_on = [c if c != "000000" else lo for c, lo in zip(self.colors, self.last_on)]
        self.sync_color_fields(self.colors[self.selected if self.selected != -1 else 0])
        self.refresh_controls()
        self.apply_settings()  # always apply: HA expects the keyboard to change
        self.schedule_save()
        self.publish_ha(force=True)

    # ------------------------------------------------------------------ power
    def set_charge_mode(self, mode):
        if mode == self.charge_mode:
            return
        self.set_status("Waiting for permission...")

        def work():
            ok = self.power.set_mode(mode)
            self.call_soon(lambda: self._charge_mode_done(ok, mode))

        threading.Thread(target=work, daemon=True).start()

    def set_power_profile(self, profile):
        """Fn+Q power profile; runs off the UI thread in case it needs a password prompt."""
        def work():
            ok = set_platform_profile(profile)
            self.call_soon(lambda: (self.set_status(f"Power profile: {PROFILE_NAMES.get(profile, profile)}"
                                                    if ok else "Power profile not changed"),
                                    self.publish_ha(force=True)))

        threading.Thread(target=work, daemon=True).start()

    def _charge_mode_done(self, ok, mode):
        self.charge_mode = self.power.current_mode()
        self.refresh_charge_modes()
        self.set_status(f"{mode} on" if ok else "Charging mode not changed")
        self.publish_ha(force=True)

    # ------------------------------------------------------------------ profiles & settings
    def current_profile_dict(self):
        return {"effect": self.effect, "brightness": self.brightness, "speed": self.speed,
                "wave_direction": self.direction, "colors": list(self.colors)}

    def load_profile(self, name, apply=True):
        if name not in self.profiles:
            name = "Default" if "Default" in self.profiles else next(iter(self.profiles))
        p = {**cfg.DEFAULT_PROFILE, **self.profiles[name]}
        self.effect, self.brightness = p["effect"], p["brightness"]
        self.speed, self.direction = int(p["speed"]), p["wave_direction"]
        self.colors = [c.lstrip("#").lower() for c in (list(p["colors"]) + ["39c5bb"] * 4)[:4]]
        self.last_on = [c if c != "000000" else "39c5bb" for c in self.colors]
        self.profile_var.set(name)
        self.sw_step = 0
        self.sync_color_fields(self.colors[self.selected if self.selected != -1 else 0])
        self.refresh_controls()
        if apply:
            self.apply_settings()
            self.schedule_save()
            self.publish_ha()

    def save_profile(self):
        self.profiles[self.profile_var.get()] = self.current_profile_dict()
        self.save_now()
        self.set_status(f"Saved profile \"{self.profile_var.get()}\"")

    def add_profile(self):
        name = (ctk.CTkInputDialog(text="Profile name:", title="New profile").get_input() or "").strip()
        if name:
            self.profiles[name] = self.current_profile_dict()
            self.profile_var.set(name)
            self.profile_menu.configure(values=list(self.profiles))
            self.save_now()

    def delete_profile(self):
        name = self.profile_var.get()
        if name == "Default" or name not in self.profiles:
            self.set_status("The Default profile can't be deleted")
            return
        del self.profiles[name]
        self.profile_menu.configure(values=list(self.profiles))
        self.load_profile("Default")
        self.save_now()

    def export_profile(self):
        name = self.profile_var.get()
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{name}.json",
                                            filetypes=[("JSON files", "*.json")])
        if path:
            with open(path, "w") as f:
                json.dump({name: self.current_profile_dict()}, f, indent=2)
            self.set_status(f"Exported \"{name}\"")

    def import_profile(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            added = [n for n, p in data.items() if isinstance(p, dict) and "colors" in p]
            for n in added:
                self.profiles[n] = data[n]
        except (OSError, ValueError, AttributeError) as e:
            self.set_status(f"Import failed: {e}")
            return
        self.profile_menu.configure(values=list(self.profiles))
        self.save_now()
        self.set_status(f"Imported {len(added)} profile(s)")

    def schedule_save(self):
        if self._loading:
            return
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(1000, self.save_now)

    def save_now(self):
        self._save_job = None
        self.profiles[self.profile_var.get()] = self.current_profile_dict()
        self.conf.update({
            "theme": self.theme_var.get(), "live_preview": self.live_preview.get(),
            "current_profile": self.profile_var.get(), "color_history": self.history,
            "pref_blink_opposite": self.pref_blink_opposite.get(), "pref_solo_mode": self.pref_solo.get(),
            "pref_batt_low": self.thresholds[0], "pref_batt_green": self.thresholds[1],
            "pref_batt_full": self.thresholds[2], "profiles": self.profiles})
        try:
            cfg.save(self.conf)
        except OSError as e:
            self.set_status(f"Couldn't save settings: {e}")

    # ------------------------------------------------------------------ dialogs
    def dialog(self, title, size):
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry(size)
        top.configure(fg_color=T.BG)
        top.transient(self)
        top.after(100, top.lift)
        return top

    def show_settings(self):
        top = self.dialog("Settings", "540x680")
        box = ctk.CTkScrollableFrame(top, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        def section(text, ic):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=(16, 6))
            ctk.CTkLabel(row, text="", image=icon(ic, self.accent, 18)).pack(side="left", padx=(0, 8))
            self.label(row, text, 12, "bold", self.accent).pack(side="left")

        def switch(text, var, hint):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=(4, 0))
            self.label(row, text, 13, color=T.TEXT).pack(side="left")
            ctk.CTkSwitch(row, text="", variable=var, width=44, progress_color=self.accent,
                          command=lambda: (self.refresh_controls(), self.schedule_save())).pack(side="right")
            self.label(box, hint, 11, color=T.TEXT_DIM).pack(anchor="w")

        section("ZONE EDITING", "keyboard-variant")
        switch("Opposite colour pulse", self.pref_blink_opposite, "The selected zone flashes its inverted colour.")
        switch("Solo focus", self.pref_solo, "Other zones go dark while you edit one.")

        section("BATTERY GAUGE EFFECT", "battery-heart-variant")
        for idx, text in enumerate(["Low alert (blink) at or below", "Green from", "Full bar from"]):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=3)
            self.label(row, text, 12).pack(side="left")
            self.label(row, "%", 12, "bold", T.TEXT_DIM).pack(side="right", padx=(4, 0))
            e = ctk.CTkEntry(row, width=56, height=28, justify="center", font=self.font(12, "bold"))
            e.insert(0, str(self.thresholds[idx]))
            e.pack(side="right")

            def commit(_e=None, e=e, idx=idx):
                try:
                    v = int(e.get())
                    if not 0 <= v <= 100:
                        raise ValueError
                    self.thresholds[idx] = v
                    e.configure(border_color=NEUTRAL_BORDER)
                    self.schedule_save()
                except ValueError:
                    e.configure(border_color=T.BAD)
                    e.delete(0, "end")
                    e.insert(0, str(self.thresholds[idx]))

            e.bind("<Return>", commit)
            e.bind("<FocusOut>", commit)

        section("HOME ASSISTANT", "home-assistant")
        self.label(box, "Sends battery, charging mode, power profile and keyboard state to Home Assistant, and "
                        "lets it change the keyboard. See examples/home-assistant in the repo for the HA side.",
                   11, color=T.TEXT_DIM, wraplength=470, justify="left").pack(anchor="w")
        ha = self.conf["home_assistant"]
        enabled = ctk.BooleanVar(value=ha["enabled"])
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        self.label(row, "Connect to Home Assistant", 13, color=T.TEXT).pack(side="left")
        ctk.CTkSwitch(row, text="", variable=enabled, width=44, progress_color=self.accent).pack(side="right")
        fields = {}
        for key, text, secret in [("url", "Home Assistant URL (e.g. http://homeassistant.local:8123)", False),
                                  ("token", "Long-lived access token (HA profile → Security)", True),
                                  ("listen", "Listen for commands on (this laptop's IP, e.g. Tailscale; "
                                             "empty = no commands)", False),
                                  ("port", "Command port", False),
                                  ("command_token", "Command token (HA sends it as a Bearer token)", True)]:
            self.label(box, text, 11, color=T.TEXT_DIM).pack(anchor="w", pady=(8, 0))
            e = ctk.CTkEntry(box, height=30, font=(self.FM, 11), show="•" if secret else "")
            e.insert(0, str(ha.get(key, "")))
            e.pack(fill="x")
            fields[key] = e

        def new_token():
            fields["command_token"].delete(0, "end")
            fields["command_token"].insert(0, secrets.token_urlsafe(24))

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btns, text="Generate command token", height=30, fg_color=T.FIELD, hover_color=T.FIELD_HOVER,
                      font=self.font(11), command=new_token).pack(side="left")
        ha_status = self.label(box, f"Status: {self.ha.status}", 11, color=T.TEXT_DIM)

        def save_ha():
            new = dict(ha, enabled=enabled.get(), **{k: e.get().strip() for k, e in fields.items()})
            try:
                new["port"] = int(new["port"] or 47125)
            except ValueError:
                fields["port"].configure(border_color=T.BAD)
                return
            self.conf["home_assistant"] = new
            self.save_now()
            self.ha.close()
            self.ha = HALink(new)  # reconnect right away with the new settings
            self.publish_ha(force=True)
            ha_status.configure(text=f"Saved. Status: {self.ha.status}")
            top.after(3000, lambda: top.winfo_exists() and ha_status.configure(text=f"Status: {self.ha.status}"))

        ctk.CTkButton(btns, text="Save & connect", height=30, fg_color=self.accent, hover_color=self.accent,
                      text_color=self.on_accent, font=self.font(12, "bold"), command=save_ha).pack(side="right")
        ha_status.pack(anchor="w", pady=(8, 4))

        ctk.CTkButton(top, text="Close", width=120, height=32, fg_color=T.FIELD, hover_color=T.FIELD_HOVER,
                      command=top.destroy).pack(pady=14)

    def show_system_info(self):
        top = self.dialog("System information", "680x560")
        self.label(top, "SYSTEM INFORMATION", 16, "bold", T.TEXT).pack(pady=(20, 4))
        status = self.label(top, "Loading hardware details...", 11, color=self.accent)
        status.pack()
        grid = ctk.CTkFrame(top, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=36, pady=12)
        grid.grid_columnconfigure(1, weight=1)

        def render():
            if not top.winfo_exists():
                return
            for w in grid.winfo_children():
                w.destroy()
            for r, (k, v) in enumerate(sysinfo.display_rows(self.sysinfo)):
                self.label(grid, k, 12, "bold", self.accent, anchor="e").grid(row=r, column=0, sticky="ne",
                                                                             padx=(0, 14), pady=4)
                self.label(grid, v, 12, color="#cccccc", anchor="w", justify="left", wraplength=420).grid(
                    row=r, column=1, sticky="w", pady=4)

        def work():
            if "CPU" not in self.sysinfo:
                self.sysinfo.update(sysinfo.basic_info())
                cfg.save_json(cfg.SYSINFO_CACHE, self.sysinfo)
                self.after(0, render)
            if "RAM Speed" not in self.sysinfo and not self.sysinfo.get("_ram_asked"):
                speed = sysinfo.ram_speed()
                self.sysinfo["_ram_asked"] = True
                if speed:
                    self.sysinfo["RAM Speed"] = speed
                cfg.save_json(cfg.SYSINFO_CACHE, self.sysinfo)
            self.after(0, lambda: (render(), top.winfo_exists() and status.configure(text="")))

        render()
        threading.Thread(target=work, daemon=True).start()
        ctk.CTkButton(top, text="Close", width=120, height=32, fg_color=T.FIELD, hover_color=T.FIELD_HOVER,
                      command=top.destroy).pack(pady=16)

    # ------------------------------------------------------------------ tray & single instance
    def hide_to_tray(self):
        self.save_now()
        self.withdraw()

    def show_window(self, *_args):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def quit_app(self, *_args):
        self.after(0, self._quit)  # the tray menu runs on its own thread

    def _quit(self):
        self.save_now()
        self.ha.close()
        if getattr(self, "tray", None):
            self.tray.stop()
        try:
            os.unlink(INSTANCE_SOCKET)
        except OSError:
            pass
        self.destroy()

    def setup_tray(self):
        menu = (pystray.MenuItem("Show Legion Control", self.show_window, default=True),
                pystray.MenuItem("Exit", self.quit_app))
        self.tray = pystray.Icon("legioncontrol", icon_image("lightning-bolt", "#FFD700", 64), "Legion Control", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def start_instance_listener(self):
        """A second launch connects to this socket and asks us to show the window."""
        try:
            os.unlink(INSTANCE_SOCKET)
        except OSError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(INSTANCE_SOCKET)
        server.listen(1)

        def serve():
            while True:
                conn, _ = server.accept()
                with conn:
                    if conn.recv(16) == b"show":
                        self.show_window()

        threading.Thread(target=serve, daemon=True).start()


def notify_running_instance():
    """True if another instance was found (and told to show itself)."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(INSTANCE_SOCKET)
            s.sendall(b"show")
        return True
    except OSError:
        return False
