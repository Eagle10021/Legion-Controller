#!/usr/bin/env python3

import os
import sys
import json
import re
import platform
import subprocess
import math
import random
import colorsys
import usb.core
import socket
import threading
import pystray
from pystray import MenuItem as item
import customtkinter as ctk
from PIL import Image, ImageOps, ImageDraw



# Point sys.path to the folder where ctk_color_picker.py is located
current_dir = os.path.dirname(os.path.abspath(__file__))
ctk_cp_path = os.path.join(current_dir, "CTkColorPicker", "CTkColorPicker")
sys.path.insert(0, ctk_cp_path)
from ctk_color_picker import AskColor
from customtkinter import CTkInputDialog

# --- Tooltip Helper Class ---
class ToolTip:
    """Custom tooltip that appears above widgets on hover"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() - 30
        
        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = ctk.CTkLabel(tw, text=self.text, fg_color="#1a1a1a", 
                            text_color="#e0e0e0", corner_radius=6,
                            font=("Segoe UI", 10))
        label.pack(padx=8, pady=4)
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# --- Backend Classes ---
class LedController:
    VENDOR = 0x048D # Replace with your Vendor ID (from lsusb)
    PRODUCT = 0xC965 # Replace with your Product ID (from lsusb)
    EFFECT = {"static": 1, "breath": 3, "wave": 4, "hue": 6, "off": 1}
    def __init__(self):
        device = usb.core.find(idVendor=self.VENDOR, idProduct=self.PRODUCT)
        if device is None: pass
        self.device = device

    def build_control_string(self, effect, colors=None, speed=1, brightness=1, wave_direction=None):
        data = [204, 22]
        if effect == "off":
            data.append(self.EFFECT["off"])
            data += [0]*30
            return data
        data.append(self.EFFECT[effect])
        data.append(speed)
        data.append(brightness)
        if effect not in ["static", "breath"]:
            data += [0]*12
        else:
            chunk = [0, 0, 0]
            for section in range(4):
                if colors and section < len(colors) and colors[section].strip():
                    color = colors[section].lower()
                    if re.match(r"^[0-9a-f]{6}$", color):
                        chunk = [int(color[i:i+2],16) for i in range(0,6,2)]
                    elif "," in color:
                        components = color.split(",")
                        if all(c.strip().isdigit() for c in components):
                            chunk = [max(0,min(255,int(c))) for c in components[:3]]
                        else:
                            raise ValueError(f"Invalid RGB format: {color}")
                    else:
                        raise ValueError(f"Invalid color model: {color}")
                data += chunk
        data += [0]
        if wave_direction is not None:
            wd = wave_direction.upper()
            if wd == "RTL":
                data += [1,0]
            elif wd == "LTR":
                data += [0,1]
            else:
                data += [0,0]
        else:
            data += [0,0]
        data += [0]*13
        return data

    def send_control_string(self, data):
        if self.device:
            if self.device.is_kernel_driver_active(0):
                 try: self.device.detach_kernel_driver(0)
                 except: pass
            self.device.ctrl_transfer(bmRequestType=0x21, bRequest=0x9, wValue=0x03CC, wIndex=0x00, data_or_wLength=data)

class PowerController:
    def __init__(self):
        base_path = "/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00"
        self.CONSERVATION_PATH = None
        self.RAPID_CHARGE_PATH = None
        drivers_dir = "/sys/bus/platform/drivers/ideapad_acpi"
        if os.path.exists(drivers_dir):
            for item in os.listdir(drivers_dir):
                if item.startswith("VPC"):
                    p = os.path.join(drivers_dir, item)
                    self.CONSERVATION_PATH = os.path.join(p, "conservation_mode")
                    self.RAPID_CHARGE_PATH = os.path.join(p, "rapid_charge")
                    break
        def find_file(start_dir, name):
            if not os.path.exists(start_dir): return None
            for root, dirs, files in os.walk(start_dir):
                if name in files: return os.path.join(root, name)
            return None
        if not self.RAPID_CHARGE_PATH or not os.path.exists(self.RAPID_CHARGE_PATH):
             found = find_file("/sys/devices/platform", "rapid_charge")
             if found: self.RAPID_CHARGE_PATH = found
        if not self.CONSERVATION_PATH or not os.path.exists(self.CONSERVATION_PATH):
             found = find_file("/sys/devices/platform", "conservation_mode")
             if found: self.CONSERVATION_PATH = found
        if not self.CONSERVATION_PATH: self.CONSERVATION_PATH = os.path.join(base_path, "conservation_mode")
        if not self.RAPID_CHARGE_PATH: self.RAPID_CHARGE_PATH = os.path.join(base_path, "rapid_charge")
        self.has_conservation = os.path.exists(self.CONSERVATION_PATH)
        self.has_rapid = os.path.exists(self.RAPID_CHARGE_PATH)

    def get_conservation(self):
        if not self.has_conservation: return False
        try:
            with open(self.CONSERVATION_PATH, 'r') as f: return f.read().strip() == '1'
        except: return False
    def set_conservation(self, enable):
        if not self.has_conservation: return
        val = '1' if enable else '0'
        try:
            with open(self.CONSERVATION_PATH, 'w') as f: f.write(val)
        except PermissionError:
            os.system(f"pkexec sh -c 'echo {val} > \"{self.CONSERVATION_PATH}\"'")

    def get_rapid(self):
        if not self.has_rapid: return False
        try:
             with open(self.RAPID_CHARGE_PATH, 'r') as f: return f.read().strip() == '1'
        except: return False

    def set_rapid(self, enable):
        if not self.has_rapid: return
        val = '1' if enable else '0'
        try:
            with open(self.RAPID_CHARGE_PATH, 'w') as f: f.write(val)
        except PermissionError:
            os.system(f"pkexec sh -c 'echo {val} > \"{self.RAPID_CHARGE_PATH}\"'")

# --- Main Application ---
class LegionLightApp(ctk.CTk):
    def __init__(self):
        super().__init__(className="legioncontrol")
        self.title("Legion Control")
        self.geometry("800x600")
        self.resizable(True, True)
        ctk.set_appearance_mode("Dark")
        
        # Keys
        self.c_bg = "#121212"
        self.c_card = "#1e1e1e"
        self.c_text = "#e0e0e0"
        self.c_text_sec = "#a0a0a0"
        self.c_accent = "#39c5bb"
        self.corner_rad = 6

        try: self.controller = LedController()
        except: self.controller = None

        # Variables
        self.theme_var_str = ctk.StringVar(value="")
        self.live_preview_var = ctk.BooleanVar(value=False)
        self.current_profile_var = ctk.StringVar(value="Default")
        self.profiles = {}
        
        self.power_controller = PowerController()
        initial_mode = "Normal Charging"
        if self.power_controller.get_conservation(): initial_mode = "Conservation Mode"
        elif self.power_controller.get_rapid(): initial_mode = "Rapid Charge"
        self.power_mode_var = ctk.StringVar(value=initial_mode)

        self.effect_var = ctk.StringVar(value="static")
        self.brightness_var = ctk.StringVar(value="Low")
        self.speed_var = ctk.IntVar(value=2)
        self.color_vars = [ctk.StringVar(value="39c5bb") for _ in range(4)]
        self.last_on_colors = ["39c5bb" for _ in range(4)] # Store colors for turning back on
        self.selected_zone = 0 # Track which zone is being edited
        self.color_history = ["#333333"] * 12 # History of 12 user colors
        self.wave_direction_var = ctk.StringVar(value="LTR")
        
        # Software Animation State
        self.sw_animation_step = 0
        self.sw_active_colors = ["000000"] * 4
        
        # User Preferences (Advanced Selection)
        self.pref_blink_opposite = ctk.BooleanVar(value=False)
        self.pref_solo_mode = ctk.BooleanVar(value=False)
        
        # Battery Indicator Preferences
        self.pref_batt_low = ctk.IntVar(value=15)
        self.pref_batt_green = ctk.IntVar(value=75)
        self.pref_batt_full = ctk.IntVar(value=95)
        
        # UI Feedback states
        self.blink_active = True
        self.blink_loop()
        self.sw_animation_loop()
        
        # Resize tracking to prevent infinite loops
        self.last_kb_size = (0, 0)
        self.last_sv_size = (0, 0)
        
        self.cache_file = os.path.join(current_dir, "sys_info_cache.json")
        self.sys_info_cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f: self.sys_info_cache = json.load(f)
            except: pass

        self.setup_tray()
        self.start_instance_listener()
        self.root_info_attempted = "RAM Speed" in self.sys_info_cache
        self.sys_scan_done = "CPU Speed" in self.sys_info_cache
        
        # Flag to prevent saving during startup
        self._is_loading = True
        
        self.load_settings()
        
        # Determine initial accent color from loaded variable
        initial_theme = self.theme_var_str.get()
        if initial_theme == "Teto":
            self.c_accent = "#d03a58"
        elif initial_theme == "Neru":
            self.c_accent = "#e4d935"
        else:
            self.c_accent = "#39c5bb"
            self.theme_var_str.set("Miku") # Ensure valid value
            
        self.build_ui()
        
        
        # --- Post-Build Setup Sequence ---
        # 1. Update general UI state
        self.after(20, self.update_control_ui)
        
        # 2. Sync is now handled by update_control_ui
        
        # 3. Reload profile colors specialized for swatches
        # MUST CALL THIS AFTER UI IS BUILT
        self.after(80, lambda: self.load_profile(self.current_profile_var.get()))
        
        # 4. Apply final hardware settings
        self.after(150, self.apply_settings)
        
        # 5. Apply theme to all dynamic elements (still locked)
        self.after(200, lambda: self.toggle_theme_str(self.theme_var_str.get()))
        
        # 6. Initialize (No selection on startup)
        self.after(250, lambda: self.select_zone(-1))
        
        # 7. UNLOCK SAVING & ACTIVATE AUTO-SAVE TRACE
        def finish_setup():
            self._finish_loading()
            # Register trace AFTER initial load is fully finished
            self.theme_var_str.trace_add("write", lambda *args: self.after(0, self.toggle_theme_str))
            
        self.after(800, finish_setup)

    def build_ui(self):
        # Set minimum size
        self.minsize(1000, 700)
        
        # Configure main window background to black (border/matte)
        self.configure(fg_color="#000000")
        
        # Base Layout: Rounded Card floating in window
        # Added accent border
        self.root_frame = ctk.CTkFrame(self, fg_color=self.c_bg, corner_radius=15, border_width=2, border_color="#222")
        self.root_frame.pack(fill="both", expand=True, padx=10, pady=10)
        # Global deselect: clicking any black space in the app clears zone focus
        self.root_frame.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        # --- Header (Packed Top) ---
        header = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        header.pack(side="top", fill="x", padx=40, pady=(20, 10))
        header.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        # Logo & Title Left
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left")
        
        # Icon label (Directly placed, no frame)
        self.logo_icon = ctk.CTkLabel(title_frame, text="", image=self.get_icon("bolt", "#ffffff", 32))
        self.logo_icon.pack(side="left", padx=(0, 15))
        
        # Track for theme updating
        if not hasattr(self, "accent_frames"): self.accent_frames = []
        
        ctk.CTkLabel(title_frame, text="LEGION CONTROL", font=("Segoe UI", 28, "bold"), text_color=self.c_text).pack(side="left")
        
        # Right Side Header Controls
        theme_frame = ctk.CTkFrame(header, fg_color="transparent")
        theme_frame.pack(side="right")
        
        # System Info Button (Device Name)
        # Use cached device name if available, otherwise use placeholder
        device_name = self.sys_info_cache.get("Device", "System Info") if self.sys_info_cache else "System Info"
        
        ctk.CTkButton(theme_frame, text=device_name, width=150, height=32, fg_color="#2b2b2b", hover_color="#3a3a3a", 
                      corner_radius=8, font=("Segoe UI", 12, "bold"), command=self.show_system_info).pack(side="left", padx=(0, 25))
        
        # Custom Theme Toggle (Button Group for better contrast control)
        self.theme_btn_frame = ctk.CTkFrame(theme_frame, fg_color="#2b2b2b", corner_radius=8)
        self.theme_btn_frame.pack(side="left")
        self.theme_btns = {}
        for val in ["Miku", "Teto", "Neru"]:
            btn = ctk.CTkButton(self.theme_btn_frame, text=val, width=50, height=28, 
                                corner_radius=6, border_width=0, font=("Segoe UI", 11, "bold"),
                                fg_color="transparent", text_color="#aaa",
                                command=lambda v=val: self.theme_var_str.set(v)) # Trace handles toggle_theme_str
            btn.pack(side="left", padx=2, pady=2)
            self.theme_btns[val] = btn
        
        # Advanced Settings Button (Gear)
        ctk.CTkButton(theme_frame, text="", image=self.get_icon("settings", "#ffffff", 18), 
                      width=32, height=32, fg_color="#2b2b2b", hover_color="#3a3a3a", 
                      corner_radius=8, command=self.show_ui_settings).pack(side="left", padx=(10, 0))

        # --- Footer (Packed Bottom) ---
        # Pack footer BEFORE content to ensure it sticks to the bottom and isn't pushed off by expandable content
        footer = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=40, pady=30)
        footer.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        ctk.CTkCheckBox(footer, text="Live Preview", variable=self.live_preview_var, text_color=self.c_text_sec, font=("Segoe UI", 13), border_width=2).pack(side="left")
        
        self.apply_btn = ctk.CTkButton(footer, text="APPLY SETTINGS", height=45, width=220, 
                                       font=("Segoe UI", 15, "bold"), fg_color=self.c_accent, text_color="#000", corner_radius=8,
                                       command=self.apply_settings)
        self.apply_btn.pack(side="right")

        # --- Content Area (Scrollable, Fills Remaining Space) ---
        content = ctk.CTkScrollableFrame(self.root_frame, fg_color="transparent", corner_radius=0)
        content.pack(side="top", fill="both", expand=True, padx=20, pady=0)
        content.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        # Left Column: Profiles & Power
        left_col = ctk.CTkFrame(content, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 20))
        left_col.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        # > Profile Section
        prof_content_frame = self.create_card(left_col, "PROFILES")
        prof_row = ctk.CTkFrame(prof_content_frame, fg_color="transparent")
        prof_row.pack(fill="x", pady=5)
        
        self.profile_combo = ctk.CTkOptionMenu(prof_row, variable=self.current_profile_var, 
                                              values=list(self.profiles.keys()), command=self.load_profile,
                                              fg_color="#333", button_color="#222", width=180, corner_radius=6)
        self.profile_combo.pack(side="left", fill="x", expand=True)
        
        # Icons - import/export with tooltips
        for icon, cmd, tooltip in [
            ("➕", self.add_profile, "New Profile"),
            ("💾", self.save_settings, "Save Current Profile"),
            ("📥", self.import_profile, "Import Profile"),
            ("📤", self.export_profile, "Export Profile"),
            ("🗑️", self.delete_profile, "Delete Profile")
        ]:
             btn = ctk.CTkButton(prof_row, text=icon, width=35, fg_color="#333", hover_color="#444", 
                                command=cmd, corner_radius=6, font=("Segoe UI", 14))
             btn.pack(side="left", padx=2)
             ToolTip(btn, tooltip)

        # > Power Section
        power_content_frame = self.create_card(left_col, "BATTERY & POWER")
        
        # Battery Top Row (Percentage & Icon)
        batt_top_row = ctk.CTkFrame(power_content_frame, fg_color="transparent")
        batt_top_row.pack(fill="x", pady=(5, 5))
        
        self.batt_icon_label = ctk.CTkLabel(batt_top_row, text="", image=self.get_icon("battery", "#ffffff", 24))
        self.batt_icon_label.pack(side="left", padx=(0, 10))
        
        self.batt_perc_label = ctk.CTkLabel(batt_top_row, text="--%", font=("Segoe UI", 24, "bold"), text_color=self.c_text)
        self.batt_perc_label.pack(side="left")
        
        # Current Charge Wh (now under percentage)
        self.batt_charge_sub_label = ctk.CTkLabel(power_content_frame, text="Charge: -- / -- Wh", font=("Segoe UI", 11), text_color="#888")
        self.batt_charge_sub_label.pack(anchor="w", padx=(34, 0), pady=(0, 10))
        
        # Battery Progress Bar
        self.batt_bar = ctk.CTkProgressBar(power_content_frame, height=10, progress_color=self.c_accent, fg_color="#333")
        self.batt_bar.pack(fill="x", pady=(5, 10))
        self.batt_bar.set(0)
        
        # Battery Info Row (Status & Wattage) - Constrain width to look better on wide screens
        batt_info_outer = ctk.CTkFrame(power_content_frame, fg_color="transparent")
        batt_info_outer.pack(fill="x", pady=(5, 0))
        
        batt_info_row = ctk.CTkFrame(batt_info_outer, fg_color="transparent")
        batt_info_row.pack(anchor="center", fill="x")
        
        self.batt_status_label = ctk.CTkLabel(batt_info_row, text="Status: --", font=("Segoe UI", 12), text_color=self.c_text_sec)
        self.batt_status_label.pack(side="left")
        
        self.batt_wattage_label = ctk.CTkLabel(batt_info_row, text="0.0W", font=("Segoe UI", 13, "bold"), text_color=self.c_accent)
        self.batt_wattage_label.pack(side="right")
        
        self.batt_time_label = ctk.CTkLabel(power_content_frame, text="", font=("Segoe UI", 11), text_color="#555")
        self.batt_time_label.pack(anchor="w", pady=(2, 0))
        
        # Bottom "Health Meta" section
        health_meta_row = ctk.CTkFrame(power_content_frame, fg_color="transparent")
        health_meta_row.pack(fill="x", pady=(15, 0))
        
        self.batt_health_perc_label = ctk.CTkLabel(health_meta_row, text="Condition: --%", font=("Segoe UI", 12, "bold"))
        self.batt_health_perc_label.pack(side="left")
        
        # Full Capacity Wh (now at bottom under condition)
        self.batt_health_wh_label = ctk.CTkLabel(health_meta_row, text="-- / -- Wh", font=("Segoe UI", 11), text_color="#aaa")
        self.batt_health_wh_label.pack(side="right")
        
        # Separator
        ctk.CTkFrame(power_content_frame, height=1, fg_color="#222").pack(fill="x", pady=15)
        
        # Initial update call
        self.update_battery_status()
        
        if self.power_controller.has_conservation or self.power_controller.has_rapid:
            ctk.CTkLabel(power_content_frame, text="Charging Mode", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(10,5))
            
            modes = ["Normal Charging"]
            if self.power_controller.has_conservation: modes.append("Conservation Mode")
            if self.power_controller.has_rapid: modes.append("Rapid Charge")
            
            ctk.CTkOptionMenu(power_content_frame, variable=self.power_mode_var, values=modes, command=self.set_power_mode,
                              fg_color="#333", button_color="#222", corner_radius=6).pack(fill="x", pady=(0, 5))
            
            ctk.CTkLabel(power_content_frame, text="Conservation ~60-80% limit. Rapid = Fast Charge.", font=("Segoe UI", 11), text_color="#555").pack(anchor="w", pady=(5,0))
        else:
             ctk.CTkLabel(power_content_frame, text="Power management not available.", text_color="#555").pack()

        # Right Column: Lighting & Colors (Merged)
        right_col = ctk.CTkFrame(content, fg_color="transparent")
        right_col.pack(side="right", fill="both", expand=True)
        # Bind background of right column to deselect
        right_col.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        light_content_frame = self.create_card(right_col, "LIGHTING & COLOR")
        light_content_frame.bind("<Button-1>", lambda e: self.select_zone(-1), add="+")
        
        # -- Lighting Controls --
        # Effect Mode Dropdown (Hardware + Software effects)
        effects = ["static","breath","wave","hue","off", "Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]
        ctk.CTkOptionMenu(light_content_frame, variable=self.effect_var, values=effects, 
                          command=self.on_setting_changed, fg_color="#333", button_color="#222", corner_radius=6).pack(fill="x", pady=(0, 15))
        
        # Control Bar: Brightness & Animation Speed (Segmented style)
        self.control_bar_frame = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        self.control_bar_frame.pack(fill="x", pady=(0, 15))
        
        # Brightness Section
        b_frame = ctk.CTkFrame(self.control_bar_frame, fg_color="transparent")
        b_frame.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(b_frame, text="Brightness", text_color=self.c_text_sec, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        
        # Brightness Group
        self.bright_btn_frame = ctk.CTkFrame(b_frame, fg_color="#222", corner_radius=6)
        self.bright_btn_frame.pack(anchor="w", pady=(2, 0))
        self.bright_btns = {}
        for val in ["OFF", "LOW", "HIGH"]:
            btn = ctk.CTkButton(self.bright_btn_frame, text=val, width=55, height=28, 
                                corner_radius=4, border_width=0, font=("Segoe UI", 10, "bold"),
                                fg_color="transparent", text_color="#aaa",
                                command=lambda v=val: self._on_bright_seg_click(v))
            btn.pack(side="left", padx=1, pady=1)
            self.bright_btns[val] = btn
        
        # Speed Section
        s_frame = ctk.CTkFrame(self.control_bar_frame, fg_color="transparent")
        s_frame.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(s_frame, text="Animation Speed", text_color=self.c_text_sec, font=("Segoe UI", 12, "bold")).pack(anchor="e")
        
        self.speed_btn_frame = ctk.CTkFrame(s_frame, fg_color="#222", corner_radius=6)
        self.speed_btn_frame.pack(anchor="e", pady=(2, 0))
        self.speed_btns_list = []
        for val in ["1", "2", "3", "4"]:
            btn = ctk.CTkButton(self.speed_btn_frame, text=val, width=42, height=28, 
                                corner_radius=4, border_width=0, font=("Segoe UI", 10, "bold"),
                                fg_color="transparent", text_color="#aaa",
                                command=lambda v=val: [self.speed_var.set(int(v)), self.on_setting_changed()])
            btn.pack(side="left", padx=1, pady=1)
            self.speed_btns_list.append(btn)
        # Wave Direction
        self.wave_frame = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        ctk.CTkLabel(self.wave_frame, text="Wave Direction", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(15,5))
        # Wave Direction Group
        self.wave_btn_frame = ctk.CTkFrame(self.wave_frame, fg_color="#222", corner_radius=6)
        self.wave_btn_frame.pack(fill="x", padx=1, pady=1)
        self.wave_btns = {}
        for val in ["LTR", "RTL"]:
            btn = ctk.CTkButton(self.wave_btn_frame, text=val, height=28, 
                                corner_radius=4, border_width=0, font=("Segoe UI", 10, "bold"),
                                fg_color="transparent", text_color="#aaa",
                                command=lambda v=val: [self.wave_direction_var.set(v), self.on_setting_changed()])
            btn.pack(side="left", fill="x", expand=True, padx=1, pady=1)
            self.wave_btns[val] = btn

        # -- Keyboard Preview (Large & Clickable) --
        self.kb_preview_label = ctk.CTkLabel(light_content_frame, text="")
        self.kb_preview_label.pack(anchor="center", pady=(0, 5))
        self.kb_preview_label.bind("<Button-1>", self.on_preview_click)
        # -- Zone Power Toggles (Large & Centered) --
        power_row = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        power_row.pack(anchor="center", pady=(0, 15))
        power_row.bind("<Button-1>", lambda e: self.select_zone(-1)) # Click background to deselect

        self.zone_power_btns = []
        for i in range(4):
            btn = ctk.CTkButton(power_row, text="", image=self.get_icon("power", "#ffffff", 14),
                                 width=50, height=34, corner_radius=17, 
                                 fg_color="#222", hover_color="#333",
                                 command=lambda idx=i: self.select_zone(idx) or self.toggle_zone_power(idx))
            btn.pack(side="left", padx=38) # Restored spacing for 500px centered zones
            ToolTip(btn, f"Zone {i+1} Power")
            self.zone_power_btns.append(btn)


        # -- Integrated Color Panel --
        self.picker_frame = ctk.CTkFrame(light_content_frame, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#222")
        self.picker_frame.pack(fill="x", pady=10, padx=5)
        # Clicking inside the picker frame background should NOT deselect
        # Actually, user said "excluding the color selectors", so clicking blank space in picker might still deselect?
        # Usually it's better if the Picker acts as a safe zone.
        # But if the user wants "anywhere outside of the zones", let's make picker background neutral
        # We won't bind it for now to see if the main frame is enough.
        
        # Upper Picking Area (Fixed Size & Centered)
        picking_container = ctk.CTkFrame(self.picker_frame, fg_color="transparent", width=390, height=180)
        picking_container.pack(anchor="center", pady=(15, 5))
        picking_container.pack_propagate(False)
        
        # SV Canvas (Fixed width) - No padding labels
        self.sv_canvas = ctk.CTkLabel(picking_container, text="", width=350, height=180, fg_color="#000", corner_radius=0)
        self.sv_canvas.pack(side="left", fill="both")
        self.sv_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.sv_canvas.bind("<Button-1>", self.on_canvas_drag)
        
        # Hue Bar
        self.hue_canvas = ctk.CTkLabel(picking_container, text="", width=30, height=180, fg_color="#000", corner_radius=0)
        self.hue_canvas.pack(side="left", padx=(10, 0), fill="both")
        self.hue_canvas.bind("<B1-Motion>", self.on_hue_drag)
        self.hue_canvas.bind("<Button-1>", self.on_hue_drag)
        
        # Lower Entry Area (Numeric + Hex) - Centered
        entry_area = ctk.CTkFrame(self.picker_frame, fg_color="transparent")
        entry_area.pack(fill="x", padx=15, pady=(0, 10))
        
        # Inner centering frame
        entry_inner = ctk.CTkFrame(entry_area, fg_color="transparent")
        entry_inner.pack(anchor="center")
        
        # Hex
        hex_f = ctk.CTkFrame(entry_inner, fg_color="transparent")
        hex_f.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(hex_f, text="HEX", font=("Segoe UI", 10, "bold"), text_color="#555").pack()
        self.hex_entry = ctk.CTkEntry(hex_f, width=80, height=28, font=("Consolas", 12), justify="center", border_width=1)
        self.hex_entry.pack()
        self.hex_entry.bind("<Return>", self.on_hex_entered)
        
        # RGB Entries
        self.rgb_entries = []
        for i, (label, col) in enumerate([("R", "#ff4444"), ("G", "#44ff44"), ("B", "#4444ff")]):
             f = ctk.CTkFrame(entry_inner, fg_color="transparent")
             f.pack(side="left", padx=5)
             ctk.CTkLabel(f, text=label, font=("Segoe UI", 10, "bold"), text_color=col).pack()
             e = ctk.CTkEntry(f, width=45, height=28, font=("Consolas", 12), justify="center", border_width=1)
             e.pack()
             e.bind("<Return>", self.on_rgb_entered)
             self.rgb_entries.append(e)

        # Palette & Gradient Row
        palette_area = ctk.CTkFrame(self.picker_frame, fg_color="transparent")
        palette_area.pack(fill="x", padx=15, pady=(0, 15))
        
        # 3-Column Layout: [Presets] [Gradient] [Recents]
        palette_split = ctk.CTkFrame(palette_area, fg_color="transparent")
        palette_split.pack(fill="x")
        palette_split.grid_columnconfigure(1, weight=1) # Center the button column
        
        # Left: Presets
        prest_col = ctk.CTkFrame(palette_split, fg_color="transparent")
        prest_col.grid(row=0, column=0, sticky="nw")
        ctk.CTkLabel(prest_col, text="PRESETS", font=("Segoe UI", 10, "bold"), text_color=self.c_text_sec).pack(anchor="w")
        
        preset_grid = ctk.CTkFrame(prest_col, fg_color="transparent")
        preset_grid.pack(anchor="w")
        
        self.vocaloid_presets = ["#39c5bb", "#d03a58", "#e4d935", "#7dbf3b"]
        for i, p_col in enumerate(self.vocaloid_presets):
             btn = ctk.CTkButton(preset_grid, text="", width=22, height=22, corner_radius=11, 
                                 fg_color=p_col, hover_color=p_col,
                                 command=lambda c=p_col: self.apply_preset(c))
             btn.grid(row=i//2, column=i%2, padx=2, pady=2)

        # Center: Gradient Button
        grad_col = ctk.CTkFrame(palette_split, fg_color="transparent")
        grad_col.grid(row=0, column=1, sticky="n")
        
        self.grad_mini_btn = ctk.CTkButton(grad_col, text="GRADIENT Z1 → Z4", height=28, width=120,
                                           fg_color="#222", hover_color="#333", border_width=1, border_color="#333",
                                           font=("Segoe UI", 9, "bold"), corner_radius=6,
                                           command=self.generate_gradient)
        self.grad_mini_btn.pack(pady=(5, 2))
        
        self.save_hist_btn = ctk.CTkButton(grad_col, text="SAVE TO RECENT", height=28, width=120,
                                           fg_color="#222", hover_color="#333", border_width=1, border_color="#333",
                                           font=("Segoe UI", 9, "bold"), corner_radius=6,
                                           command=lambda: self.add_to_history(self.color_vars[self.selected_zone].get()))
        self.save_hist_btn.pack(pady=2)

        # Right: Recent Colors (4x3 Grid)
        hist_col = ctk.CTkFrame(palette_split, fg_color="transparent")
        hist_col.grid(row=0, column=2, sticky="ne")
        ctk.CTkLabel(hist_col, text="RECENT COLORS", font=("Segoe UI", 10, "bold"), text_color=self.c_text_sec).pack(anchor="w")
        
        self.history_grid = ctk.CTkFrame(hist_col, fg_color="transparent")
        self.history_grid.pack(anchor="w")
        
        self.history_swatches = []
        for i in range(12):
             btn = ctk.CTkButton(self.history_grid, text="", width=22, height=22, corner_radius=5, 
                                 fg_color="#333", hover_color="#444", border_width=1, border_color="#222")
             btn.grid(row=i//4, column=i%4, padx=2, pady=2)
             self.history_swatches.append(btn)
        self.update_history_ui()
        
        # Picker State
        self.current_hue = 180 # 0-360
        self.current_sv = (100, 100) # 0-100
        
        self.render_picker_canvases()
    
    def get_icon(self, name, color, size=24):
        """Generate a sharp PNG icon using PIL and return as CTkImage"""
        img = Image.new("RGBA", (size*2, size*2), (0,0,0,0)) # 2x for supersampling
        draw = ImageDraw.Draw(img)
        
        if name == "bolt":
            # Points for a lightning bolt
            points = [(size*1.2, size*0.2), (size*0.4, size*1.1), (size*1.0, size*1.1), 
                      (size*0.8, size*1.8), (size*1.6, size*0.9), (size*1.0, size*0.9)]
            draw.polygon(points, fill=color)
        elif name == "bolt_glow":
            points = [(size*1.2, size*0.2), (size*0.4, size*1.1), (size*1.0, size*1.1), 
                      (size*0.8, size*1.8), (size*1.6, size*0.9), (size*1.0, size*0.9)]
            # Draw a soft glow by layering slightly transparent versions
            glow_col = color + "44" if len(color)==7 else color # Basic alpha if hex
            if color == "#ffffff": glow_col = "rgba(255,255,255,80)"
            
            # Simple glow using multiple outlines
            for i in range(3, 0, -1):
                draw.polygon(points, outline=color, width=i*2)
            draw.polygon(points, fill=color)
        elif name == "battery":
            # Battery body
            draw.rounded_rectangle([size*0.4, size*0.6, size*1.6, size*1.4], radius=4, outline=color, width=4)
            # Battery tip
            draw.rectangle([size*1.6, size*0.8, size*1.75, size*1.2], fill=color)
            # Fill level (just a placeholder, real one in update_battery)
            draw.rectangle([size*0.55, size*0.75, size*1.45, size*1.25], fill=color)
        elif name == "battery_low":
            draw.rounded_rectangle([size*0.4, size*0.6, size*1.6, size*1.4], radius=4, outline="#ff4444", width=4)
            draw.rectangle([size*1.6, size*0.8, size*1.75, size*1.2], fill="#ff4444")
            draw.rectangle([size*0.55, size*0.75, size*0.8, size*1.25], fill="#ff4444")
        elif name == "settings":
            # Gear icon
            draw.ellipse([size*0.6, size*0.6, size*1.4, size*1.4], outline=color, width=4)
            import math
            for i in range(8):
                angle = i * 45
                rad = math.radians(angle)
                x1 = size + math.cos(rad) * size * 0.4
                y1 = size + math.sin(rad) * size * 0.4
                x2 = size + math.cos(rad) * size * 0.8
                y2 = size + math.sin(rad) * size * 0.8
                draw.line([x1, y1, x2, y2], fill=color, width=4)
        elif name == "deselect":
            # Simple X icon
            pad = size * 0.5
            draw.line([pad, pad, size*2-pad, size*2-pad], fill=color, width=4)
            draw.line([size*2-pad, pad, pad, size*2-pad], fill=color, width=4)
            
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def update_keyboard_preview(self):
        """Draw a visual representation of the 4-zone lighting with large fixed size"""
        if not hasattr(self, 'kb_preview_label'):
            return
            
        w, h = 500, 150
        
        # Create a higher resolution image for smoothness
        canvas_w, canvas_h = w * 2, h * 2
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Determine if lights are "off"
        is_off = self.effect_var.get() == "off"
        
        # Colors for the 4 zones
        colors = []
        effect = self.effect_var.get()
        is_sw = effect in ["Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]
        
        for i in range(4):
            if is_sw:
                hex_c = self.sw_active_colors[i]
            else:
                hex_c = self.color_vars[i].get()
                
            if is_off or hex_c == "000000":
                colors.append((25, 25, 25, 255)) # Darker if off
            else:
                rgb = self.hex_to_rgb(hex_c)
                colors.append(rgb + (255,))
        
        # Draw the keyboard body
        body_padding = 10
        draw.rounded_rectangle([body_padding, body_padding, canvas_w - body_padding, canvas_h - body_padding], 
                                radius=20, fill=(30, 30, 30, 255), outline=(60, 60, 60, 255), width=4)
        
        # Draw the 4 lighting zones
        zone_w = (canvas_w - (body_padding * 4)) // 4
        zone_h = canvas_h - (body_padding * 6)
        zone_start_y = body_padding * 3
        
        for i in range(4):
            x1 = (body_padding * 2) + (i * zone_w)
            y1 = zone_start_y
            x2 = x1 + zone_w - 5
            y2 = y1 + zone_h
            
            # Glow effect (soft rectangle)
            glow_c = colors[i][:3] + (80,) # Transparent version
            draw.rounded_rectangle([x1-2, y1-2, x2+2, y2+2], radius=10, fill=glow_c)
            
            # Main key area color
            if self.pref_solo_mode.get() and self.selected_zone != -1 and i != self.selected_zone:
                 fill_col = (20, 20, 20, 255) # Darken others in Solo mode
            else:
                 fill_col = colors[i]
            draw.rounded_rectangle([x1, y1, x2, y2], radius=8, fill=fill_col)
            
            # Add Selection Highlight (Blinking/Breathing)
            if i == self.selected_zone:
                # Determine display color for cursor
                disp_col = self.c_accent
                if self.pref_blink_opposite.get() and not self.blink_active:
                     # In inverted mode, the "off" phase highlight is white or black
                     disp_col = "#ffffff"
                
                # If blink is active, draw a thicker, brighter ring
                if self.blink_active:
                    draw.rounded_rectangle([x1-5, y1-5, x2+5, y2+5], radius=11, outline=disp_col, width=5)
                else:
                    # If blink is "off", draw a subtle, thinner ring
                    draw.rounded_rectangle([x1-3, y1-3, x2+3, y2+3], radius=9, outline=disp_col, width=2)
            
            # Add simple key highlights (to look like keys)
            key_pad = 10
            draw.line([x1 + key_pad, y1 + 30, x2 - key_pad, y1 + 30], fill=(255, 255, 255, 40), width=2)
            draw.line([x1 + key_pad, y1 + 60, x2 - key_pad, y1 + 60], fill=(255, 255, 255, 40), width=2)
            draw.line([x1 + key_pad, y1 + 90, x2 - key_pad, y1 + 90], fill=(255, 255, 255, 40), width=2)

        # Convert to CTkImage
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
        if hasattr(self, "kb_preview_label"):
            self.kb_preview_label.configure(image=ctk_img)

    def get_battery_status_data(self):
        """Get detailed battery data as a dictionary"""
        data = {
            "capacity": 0,
            "status": "Unknown",
            "wattage": 0.0,
            "time_str": "",
            "icon": "🔋"
        }
        try:
            base = "/sys/class/power_supply/BAT0/"
            
            # Capacity
            if os.path.exists(base + "capacity"):
                with open(base + "capacity", 'r') as f:
                    data["capacity"] = int(f.read().strip())
            
            # Energy Values (Wh)
            e_now = 0
            e_full = 0
            e_design = 0
            
            if os.path.exists(base + "energy_now"):
                with open(base + "energy_now", 'r') as f: e_now = int(f.read().strip())
            if os.path.exists(base + "energy_full"):
                with open(base + "energy_full", 'r') as f: e_full = int(f.read().strip())
            if os.path.exists(base + "energy_full_design"):
                with open(base + "energy_full_design", 'r') as f: e_design = int(f.read().strip())
                
            data["energy_now_wh"] = e_now / 1000000.0
            data["energy_full_wh"] = e_full / 1000000.0
            data["energy_design_wh"] = e_design / 1000000.0
            
            if e_design > 0:
                data["health"] = (e_full / e_design) * 100
            else:
                data["health"] = 0
            
            # Status
            if os.path.exists(base + "status"):
                with open(base + "status", 'r') as f:
                    data["status"] = f.read().strip()
            
            # Power / Wattage
            power_val = 0
            if os.path.exists(base + "power_now"):
                with open(base + "power_now", 'r') as f:
                    power_val = int(f.read().strip())
                    data["wattage"] = power_val / 1000000.0
            
            # Time Remaining Calculation
            if data["wattage"] > 0.1:
                energy_now = int(data["energy_now_wh"] * 1000000)
                energy_full = int(data["energy_full_wh"] * 1000000)
                power_val = int(data["wattage"] * 1000000)
                
                if data["status"] == "Discharging":
                    hours = energy_now / power_val
                    h = int(hours)
                    m = int((hours - h) * 60)
                    data["time_str"] = f"Est: {h}h {m}m remaining"
                elif data["status"] == "Charging":
                    remaining_to_charge = energy_full - energy_now
                    if remaining_to_charge > 0:
                        hours = remaining_to_charge / power_val
                        h = int(hours)
                        m = int((hours - h) * 60)
                        data["time_str"] = f"Est: {h}h {m}m until full"

            # Icon logic
            if data["status"] == "Charging": data["icon"] = "⚡"
            elif data["capacity"] < 20: data["icon"] = "🪫"
            
            return data
        except:
            return data

    def update_battery_status(self):
        """Update battery UI elements with fresh data every second"""
        data = self.get_battery_status_data()
        
        if hasattr(self, 'batt_perc_label'):
            self.batt_perc_label.configure(text=f"{data['capacity']}%")
            self.batt_bar.set(data['capacity'] / 100.0)
            self.batt_status_label.configure(text=f"Status: {data['status']}")
            self.batt_time_label.configure(text=data["time_str"])
            
            # Update Icon (Pure white, no theme sync)
            icon_name = "bolt" if data['status'] == "Charging" else "battery"
            self.batt_icon_label.configure(image=self.get_icon(icon_name, "#ffffff", 24))
            
            # Health & Capacity Labels
            if "health" in data:
                health_color = self.c_accent if data["health"] > 80 else "#ffcc00" if data["health"] > 60 else "#ff4444"
                
                # Update Charge (Current / Full Capacity) - Now at top
                self.batt_charge_sub_label.configure(text=f"Charge: {data['energy_now_wh']:.1f} / {data['energy_full_wh']:.1f} Wh")
                
                # Update Health (Full Capacity / Original Design) - Now at bottom
                self.batt_health_perc_label.configure(text=f"Battery Condition: {data['health']:.1f}%", text_color=health_color)
                self.batt_health_wh_label.configure(text=f"{data['energy_full_wh']:.1f} / {data['energy_design_wh']:.1f} Wh")
            
            # Update Keyboard Preview
            self.update_keyboard_preview()
            
            # Wattage formatting
            w = data['wattage']
            prefix = "+" if data['status'] == "Charging" else "-" if data['status'] == "Discharging" else ""
            self.batt_wattage_label.configure(text=f"{prefix}{w:.1f}W")
            
            # Visual warnings
            if data['status'] == "Discharging" and data['capacity'] <= 15:
                self.batt_perc_label.configure(text_color="#ff4444")
            else:
                self.batt_perc_label.configure(text_color=self.c_text)

        # Schedule next update in 1 second
        self.after(1000, self.update_battery_status)

    def export_profile(self):
        """Export current profile to a JSON file"""
        from tkinter import filedialog
        current = self.current_profile_var.get()
        if current not in self.profiles:
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{current}.json"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump({current: self.profiles[current]}, f, indent=2)
            except Exception as e:
                print(f"Export failed: {e}")
    
    def import_profile(self):
        """Import a profile from a JSON file"""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    imported = json.load(f)
                
                for name, settings in imported.items():
                    self.profiles[name] = settings
                
                self.profile_combo.configure(values=list(self.profiles.keys()))
                self.save_settings()
            except Exception as e:
                print(f"Import failed: {e}")
    
    def fade_in_animation(self, widget, duration=200):
        """Smooth fade-in animation for widgets"""
        # CustomTkinter doesn't support opacity animation directly
        pass
    
    def _finish_loading(self):
        """Mark that initial loading is complete, allow saves"""
        self._is_loading = False
        
    def gather_system_info(self, include_root=False):
        # If we have cached info and don't need root, return it
        if self.sys_info_cache and not include_root:
            return self.sys_info_cache

        # If cache is empty, or if we need root info, start building/updating
        info = self.sys_info_cache.copy() if self.sys_info_cache else {
            "User": os.environ.get("USER", "User"),
            "Hostname": platform.node(),
            "OS": "Linux",
            "Kernel": platform.release(),
            "Device": "Unknown Model",
            "BIOS": "Unknown",
            "CPU": "Unknown",
            "Memory": "Unknown"
        }
        
        # Only do Basic Scan if cache was empty (first run)
        if not self.sys_info_cache:
            # OS Release - Fast read
            try:
                for line in open("/etc/os-release"):
                    if line.startswith("PRETTY_NAME="):
                        info["OS"] = line.split("=")[1].strip().strip('"')
                        break
            except: pass

            # DMI Info - Fast reads from sysfs
            def get_dmi(path):
                try: 
                    with open(path, "r") as r: return r.read().strip()
                except: return ""

            p_name = get_dmi("/sys/devices/virtual/dmi/id/product_name")
            p_version = get_dmi("/sys/devices/virtual/dmi/id/product_version")
            p_family = get_dmi("/sys/devices/virtual/dmi/id/product_family")
            info["BIOS"] = get_dmi("/sys/devices/virtual/dmi/id/bios_version") or "Unknown"
            
            # Construct best device name
            if "Legion" in p_version: info["Device"] = p_version
            elif "Legion" in p_family:
                if p_name not in p_family: info["Device"] = f"{p_family} {p_name}"
                else: info["Device"] = p_family
            elif p_name: info["Device"] = p_name
                
            # Add the specific Model ID (product_name) explicitly if available
            if p_name and p_name != info.get("Device"): info["Model ID"] = p_name

            # Memory
            try:
                 with open("/proc/meminfo", "r") as f:
                     for line in f:
                         if "MemTotal" in line:
                             kb = int(line.split(":")[1].strip().split()[0])
                             gb_approx = kb / (1024*1024)
                             # Heuristic to guess physical RAM (MemTotal < Physical due to hardware reservation)
                             # Standard sizes up to 2TB
                             standard_sizes = [4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 1024, 2048]
                             installed_ram = gb_approx
                             for size in standard_sizes:
                                 if size >= gb_approx:
                                     installed_ram = size
                                     break
                             info["Memory"] = f"{installed_ram} GB"
                             break
            except: pass
            
            # CPU Model
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                             info["CPU"] = line.split(":")[1].strip()
                             break
            except: pass
            
            # CPU Speed (Sysfs/Lscpu)
            try:
                if os.path.exists("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"):
                    with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "r") as f:
                        khz = int(f.read().strip())
                        info["CPU Speed"] = f"{khz/1000000:.2f} GHz"
                else:
                    out = subprocess.check_output("lscpu", shell=True).decode("utf-8")
                    for line in out.splitlines():
                        if "CPU max MHz" in line:
                            mhz = float(line.split(":")[1].strip())
                            info["CPU Speed"] = f"{mhz/1000:.2f} GHz"
                            break
            except: pass

            # GPU(s) - Optimized subprocess call
            try:
                lspci = subprocess.check_output(["lspci", "-mm"], stderr=subprocess.DEVNULL).decode("utf-8")
                gpus = []
                for line in lspci.splitlines():
                    if "VGA" in line or "3D" in line:
                        # Format: "Slot" "Class" "Vendor" "Device" ...
                        # lspci -mm is quoted.
                        parts = [p.strip('"') for p in line.split(' "')]
                        if len(parts) >= 4:
                            # Vendor + Device is usually a good bet, specifically Device name
                            vendor = parts[2]
                            device = parts[3].replace('"', '')
                            
                            # Fix formatting: "GA106M [GeForce RTX 3060...]" -> "GeForce RTX 3060... [GA106M]"
                            marketing_match = re.search(r"^(.*?) \[(.*?)\]", device)
                            if marketing_match:
                                 chip_name = marketing_match.group(1).strip()
                                 marketing_name = marketing_match.group(2).strip()
                                 device = f"{marketing_name} [{chip_name}]"
                            
                            # Simplify vendor
                            if "NVIDIA" in vendor.upper(): vendor = "NVIDIA"
                            if "Advanced Micro Devices" in vendor: vendor = "AMD"
                            if "Intel" in vendor: vendor = "Intel"
                            
                            gpus.append(f"{vendor} {device}")
                
                for i, g in enumerate(gpus):
                    key = "GPU" if len(gpus) == 1 else f"GPU {i+1}"
                    info[key] = g
            except: pass
            
            # Update cache with basic info
            self.sys_info_cache = info
            
            # Save to disk
            try:
                with open(self.cache_file, "w") as f:
                    json.dump(self.sys_info_cache, f)
            except: pass
            
        return info

    def gather_root_info(self):
        """Fetch root-level info like RAM speed in background"""
        if self.root_info_attempted: return
        
        info = self.sys_info_cache.copy()
        try:
            # This is the slow part that needs root
            dmi = subprocess.check_output("pkexec dmidecode -t 17", shell=True).decode("utf-8")
            ram_speeds = set()
            for line in dmi.splitlines():
                line = line.strip()
                if "Configured Memory Speed:" in line or ("Speed:" in line and "Configured" not in line):
                    if ":" in line:
                        val = line.split(":")[1].strip()
                        if val and "Unknown" not in val and "None" not in val:
                            ram_speeds.add(val)
            
            if ram_speeds:
                info["RAM Speed"] = ", ".join(sorted(list(ram_speeds)))
                self.sys_info_cache = info
                # Save updated cache
                try:
                    with open(self.cache_file, "w") as f:
                        json.dump(self.sys_info_cache, f)
                except: pass
        except: pass
        
        self.root_info_attempted = True

    def get_display_info(self, info_dict):
        """Prepare raw info dictionary for display (formatting)"""
        display_info = info_dict.copy()
        
        if "CPU Speed" in display_info and display_info["CPU Speed"]:
            display_info["CPU"] = f"{display_info.get('CPU','')} @ {display_info['CPU Speed']}"
            
        if "RAM Speed" in display_info and display_info["RAM Speed"]:
             display_info["Memory"] = f"{display_info.get('Memory','')} @ {display_info['RAM Speed']}"

        # Reorder dictionary for display
        ordered_info = {}
        for k in ["User", "Hostname", "OS", "Kernel", "Device", "Model ID", "BIOS", "CPU", "Memory"]:
            if k in display_info: ordered_info[k] = display_info[k]
        
        # Add GPUs at the end
        for k in display_info:
            if k.startswith("GPU"): ordered_info[k] = display_info[k]
                
        return ordered_info

    def show_system_info(self):
        # Create Popup
        self.sys_popup = ctk.CTkToplevel(self)
        top = self.sys_popup
        top.title("System Information")
        top.geometry("700x650")
        top.configure(fg_color=self.c_card)
        top.resizable(True, True)
        
        # Center popup
        x = self.winfo_x() + (self.winfo_width() // 2) - 350
        y = self.winfo_y() + (self.winfo_height() // 2) - 325
        top.geometry(f"+{x}+{y}")
        
        top.transient(self) 
        
        def safe_grab():
            try:
                if top.winfo_exists():
                    if top.winfo_viewable():
                        top.grab_set()
                        top.focus_set()
                    else:
                        self.after(100, safe_grab)
            except:
                pass

        # Start the safe grab process
        self.after(50, safe_grab)
        
        # Header
        ctk.CTkLabel(top, text="SYSTEM INFORMATION", font=("Segoe UI", 16, "bold"), text_color=self.c_text).pack(pady=(20, 10))
        
        # Progress bar or loading text for background updates
        self.sys_status_label = ctk.CTkLabel(top, text="Loading hardware details...", font=("Segoe UI", 11), text_color=self.c_accent)
        self.sys_status_label.pack(pady=(0, 10))
        
        # Container for the info rows
        self.sys_info_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.sys_info_frame.pack(fill="both", expand=True, padx=40, pady=10)
        self.sys_info_frame.grid_columnconfigure(0, weight=0)
        self.sys_info_frame.grid_columnconfigure(1, weight=1)

        # Dictionary to store references to value labels for instant updating
        self.sys_value_labels = {}

        # Initial fast load from cache - creates the structure
        self.refresh_sys_info_ui()
        
        # Secondary async load for heavy details
        import threading
        def async_load():
            # Gather basic missing stats
            self.gather_system_info() 
            self.after(0, self.refresh_sys_info_ui)
            
            # If root info (RAM speed) isn't attempted yet, do it now
            if not self.root_info_attempted:
                self.gather_root_info()
                self.after(0, self.refresh_sys_info_ui)
            
            # Final status update
            self.after(0, lambda: self.sys_status_label.configure(text="Hardware Scan Complete", text_color="#555") if self.sys_popup.winfo_exists() else None)

        threading.Thread(target=async_load, daemon=True).start()

        # Close button
        ctk.CTkButton(top, text="CLOSE", width=120, height=32, fg_color="#333", hover_color="#444", 
                      command=top.destroy, corner_radius=6).pack(pady=20)

    def show_ui_settings(self):
        """Show advanced UI interaction settings popup"""
        top = ctk.CTkToplevel(self)
        top.title("Control Settings")
        top.geometry("450x400")
        top.attributes("-topmost", True)
        top.configure(fg_color=self.c_bg)
        
        # Center popup
        x = self.winfo_x() + (self.winfo_width() // 2) - 225
        y = self.winfo_y() + (self.winfo_height() // 2) - 200
        top.geometry(f"+{x}+{y}")
        top.transient(self)
        
        ctk.CTkLabel(top, text="ADVANCED FEEDBACK", font=("Segoe UI", 16, "bold"), text_color=self.c_text).pack(pady=(20, 20))
        
        container = ctk.CTkFrame(top, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=40)
        
        # Toggle 1: Opposite Color Blink
        f1 = ctk.CTkFrame(container, fg_color="transparent")
        f1.pack(fill="x", pady=10)
        ctk.CTkLabel(f1, text="Opposite Color Pulse", font=("Segoe UI", 13), text_color="#ccc").pack(side="left")
        ctk.CTkSwitch(f1, text="", variable=self.pref_blink_opposite, width=40,
                      command=self.save_settings).pack(side="right")
        ctk.CTkLabel(top, text="Flips the zone color during pulse (High Visibility)", font=("Segoe UI", 10), text_color="#555").pack(pady=(0, 10))

        # Toggle 2: Solo Focus Mode
        f2 = ctk.CTkFrame(container, fg_color="transparent")
        f2.pack(fill="x", pady=10)
        ctk.CTkLabel(f2, text="Solo Focus Mode", font=("Segoe UI", 13), text_color="#ccc").pack(side="left")
        ctk.CTkSwitch(f2, text="", variable=self.pref_solo_mode, width=40,
                      command=self.save_settings).pack(side="right")
        ctk.CTkLabel(top, text="Darkens other zones when picking colors", font=("Segoe UI", 10), text_color="#555").pack(pady=(0, 20))
        
        # --- Battery Thresholds ---
        ctk.CTkLabel(container, text="BATTERY THRESHOLDS", font=("Segoe UI", 12, "bold"), text_color=self.c_accent).pack(pady=(10, 5))
        
        def create_thresh_input(parent, label, var):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 11), text_color="#aaa").pack(side="left")
            
            # Label for "%"
            ctk.CTkLabel(f, text="%", font=("Segoe UI", 11, "bold"), text_color="#555").pack(side="right", padx=(2, 5))
            
            e = ctk.CTkEntry(f, width=45, height=26, font=("Segoe UI", 11, "bold"), justify="center", border_width=1)
            e.insert(0, str(var.get()))
            e.pack(side="right")
            
            def validate_and_save(event=None):
                try:
                    val = int(e.get())
                    if 0 <= val <= 100:
                        var.set(val)
                        self.save_settings()
                        e.configure(border_color="#333") # Reset to neutral
                    else:
                        e.configure(border_color="#ff4444") # Red for error
                        e.delete(0, "end")
                        e.insert(0, str(var.get())) # Revert
                except:
                    e.configure(border_color="#ff4444")
                    e.delete(0, "end")
                    e.insert(0, str(var.get())) # Revert
            
            e.bind("<FocusOut>", validate_and_save)
            e.bind("<Return>", validate_and_save)
            
        create_thresh_input(container, "Low Alert (Blink)", self.pref_batt_low)
        create_thresh_input(container, "Safe Level (Green)", self.pref_batt_green)
        create_thresh_input(container, "Full Bar Trigger", self.pref_batt_full)

        ctk.CTkButton(top, text="CLOSE", width=120, height=32, fg_color="#333", hover_color="#444", 
                      command=top.destroy, corner_radius=6).pack(pady=20)

    def refresh_sys_info_ui(self):
        """Update existing labels or create them if missing (much faster than destroying)"""
        if not hasattr(self, 'sys_popup') or not self.sys_popup.winfo_exists():
            return
            
        info = self.get_display_info(self.sys_info_cache)
        
        for i, (k, v) in enumerate(info.items()):
            # If label already exists, just update text (Instant)
            if k in self.sys_value_labels:
                lbl = self.sys_value_labels[k]
                if lbl.cget("text") != v:
                    lbl.configure(text=v)
            else:
                # Create it once
                ctk.CTkLabel(self.sys_info_frame, text=k+":", font=("Segoe UI", 12, "bold"), 
                             text_color=self.c_accent, anchor="e").grid(row=i, column=0, sticky="ne", padx=(0,15), pady=5)
                
                val_lbl = ctk.CTkLabel(self.sys_info_frame, text=v, font=("Segoe UI", 12), 
                                       text_color="#ccc", anchor="w", wraplength=380, justify="left")
                val_lbl.grid(row=i, column=1, sticky="w", pady=5)
                self.sys_value_labels[k] = val_lbl
        
    def create_card(self, parent, title):
        # Slightly darker card, lighter text
        card = ctk.CTkFrame(parent, fg_color=self.c_card, corner_radius=self.corner_rad, border_width=1, border_color="#262626")
        card.pack(fill="x", pady=(0, 15))
        
        # Colored accent line at top
        accent = ctk.CTkFrame(card, height=3, fg_color=self.c_accent, corner_radius=0)
        accent.pack(fill="x")
        
        # Track for theme updating
        if not hasattr(self, "accent_frames"): self.accent_frames = []
        # Mark as header for clarity
        accent.is_header = True 
        self.accent_frames.append(accent)
        
        # Title with padding
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 12, "bold"), text_color="#666").pack(anchor="w", padx=25, pady=(12, 5))
        
        # Content frame (returned to be used as parent for widgets)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=25, pady=(0, 15))
        
        return content

    def toggle_theme_str(self, choice=None):
        # Update colors based on selection
        val = self.theme_var_str.get()
        if val == "Teto":
            self.c_accent = "#d03a58" # Red/Pink
        elif val == "Neru":
             self.c_accent = "#c9b800" # Gold
        else: # Miku
            self.c_accent = "#39c5bb" # Teal
            
        # Determine best text color for contrast on selected light colors (Miku/Neru)
        self.sel_txt_col = "#000000" if val in ["Miku", "Neru"] else "#ffffff"
            
        # Update active UI elements if they exist
        if hasattr(self, "apply_btn"):
            self.apply_btn.configure(fg_color=self.c_accent, text_color=self.sel_txt_col)
            
        if hasattr(self, "logo_icon"):
            self.logo_icon.configure(image=self.get_icon("bolt", "#ffffff", 32))

        # Re-run control UI update to apply specific Colors to Custom Groups
        self.update_control_ui()
             
        # Update cached accent frames
        if hasattr(self, "accent_frames"):
            for frame in self.accent_frames:
                try:
                    if hasattr(frame, "is_logo"):
                         frame.configure(border_color=self.c_accent)
                    else:
                         frame.configure(fg_color=self.c_accent)
                except: pass
        
        # Update battery label color
        if hasattr(self, 'batt_bar'):
             self.batt_bar.configure(progress_color=self.c_accent)
        if hasattr(self, 'batt_wattage_label'):
             self.batt_wattage_label.configure(text_color=self.c_accent)
        
        # Update is already triggered above via self.update_control_ui()
            
        self.save_settings()

    def update_control_ui(self, *args):
        # Determine highlighting colors
        if not hasattr(self, 'sel_txt_col'):
            self.sel_txt_col = "#000000" if self.theme_var_str.get() in ["Miku", "Neru"] else "#ffffff"

        # Theme Group
        if hasattr(self, 'theme_btns'):
            current = self.theme_var_str.get()
            for val, btn in self.theme_btns.items():
                if val == current:
                    btn.configure(fg_color=self.c_accent, text_color=self.sel_txt_col, hover_color=self.c_accent)
                else:
                    btn.configure(fg_color="transparent", text_color="#aaa", hover_color="#3a3a3a")

        # Brightness Group
        if hasattr(self, 'bright_btns'):
            b_val = "LOW" if self.brightness_var.get() == "Low" else "HIGH"
            if self.effect_var.get() == "off": b_val = "OFF"
            for val, btn in self.bright_btns.items():
                if val == b_val:
                    btn.configure(fg_color=self.c_accent, text_color=self.sel_txt_col, hover_color=self.c_accent)
                else:
                    btn.configure(fg_color="transparent", text_color="#aaa", hover_color="#333")
            
        # Speed Group
        if hasattr(self, 'speed_btns_list'):
            s_val = str(self.speed_var.get())
            for btn in self.speed_btns_list:
                if btn.cget("text") == s_val:
                    btn.configure(fg_color=self.c_accent, text_color=self.sel_txt_col, hover_color=self.c_accent)
                else:
                    btn.configure(fg_color="transparent", text_color="#aaa", hover_color="#333")

        # Wave Group
        if hasattr(self, 'wave_btns'):
            w_val = self.wave_direction_var.get()
            for val, btn in self.wave_btns.items():
                if val == w_val:
                    btn.configure(fg_color=self.c_accent, text_color=self.sel_txt_col, hover_color=self.c_accent)
                else:
                    btn.configure(fg_color="transparent", text_color="#aaa", hover_color="#333")
        # Wave Visibility
        if self.effect_var.get() == "wave":
            # Pack after control_bar_frame so it's in the right spot
            self.wave_frame.pack(fill="x", pady=(0, 15), after=self.control_bar_frame)
        else:
            self.wave_frame.pack_forget()

        # Zone Power Icons
        if hasattr(self, 'zone_power_btns'):
            for i, btn in enumerate(self.zone_power_btns):
                is_on = self.color_vars[i].get() != "000000"
                if is_on:
                    btn.configure(image=self.get_icon("bolt_glow", "#ffffff", 14))
                else:
                    btn.configure(image=self.get_icon("bolt", "#555555", 14))

    def _on_bright_seg_click(self, val):
        if val == "OFF":
            self.effect_var.set("off")
        elif val == "LOW":
            self.brightness_var.set("Low")
            if self.effect_var.get() == "off": self.effect_var.set("static")
        elif val == "HIGH":
            self.brightness_var.set("High")
            if self.effect_var.get() == "off": self.effect_var.set("static")
        self.on_setting_changed()

    # --- Logic Methods (Same as before) ---
    def open_color_wheel(self, index):
        color = AskColor(initial_color="#" + self.color_vars[index].get()).get()
        if color:
            self.color_vars[index].set(color.lstrip("#"))
            self.color_swatches[index].configure(fg_color="#" + color.lstrip("#"))
            self.on_setting_changed()

    def hex_to_rgb(self, hex_val):
        hex_val = hex_val.lstrip("#")
        return tuple(int(hex_val[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(self, rgb):
        return '{:02x}{:02x}{:02x}'.format(*rgb)

    def invert_hex(self, hex_val):
        rgb = self.hex_to_rgb(hex_val)
        inv_rgb = tuple(255 - c for c in rgb)
        return self.rgb_to_hex(inv_rgb)

    def interpolate_color(self, c1, c2, t):
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    def generate_gradient(self):
        try:
            c1 = self.hex_to_rgb(self.color_vars[0].get())
            c4 = self.hex_to_rgb(self.color_vars[3].get())
            c2 = self.interpolate_color(c1, c4, 1/3)
            c3 = self.interpolate_color(c1, c4, 2/3)
            self.color_vars[1].set(self.rgb_to_hex(c2))
            self.color_vars[2].set(self.rgb_to_hex(c3))
            
            # Update swatch colors visually
            for i in range(4):
                self.color_swatches[i].configure(fg_color="#" + self.color_vars[i].get())

            if self.live_preview_var.get():
                self.apply_settings()
        except: pass

    def select_zone(self, index):
        """Focus a specific zone for editing. Pass -1 to deselect all."""
        self.selected_zone = index
        # Selection highlight is now handled in update_keyboard_preview
        
        if index == -1:
             # Just refresh UI to show all lights on
             self.update_keyboard_preview()
             if self.live_preview_var.get():
                  self.apply_settings()
             return

        # Update entries to match the color of this zone
        hex_val = self.color_vars[index].get()
        rgb = self.hex_to_rgb(hex_val)
        
        # Update picker state
        import colorsys
        h, s, v = colorsys.rgb_to_hsv(rgb[0]/255, rgb[1]/255, rgb[2]/255)
        self.current_hue = h * 360
        self.current_sv = (s * 100, v * 100)
        
        self.update_entry_fields(hex_val, rgb)
        self.render_picker_canvases()
        self.update_keyboard_preview()

    def update_entry_fields(self, hex_val, rgb):
        """Update the text entry fields sync with selection"""
        if hasattr(self, 'hex_entry'):
            self.hex_entry.delete(0, "end")
            self.hex_entry.insert(0, hex_val.upper())
            for i, val in enumerate(rgb):
                self.rgb_entries[i].delete(0, "end")
                self.rgb_entries[i].insert(0, str(val))

    def render_picker_canvases(self):
        """Generate static images for the picker UI using fixed dimensions"""
        if not hasattr(self, 'sv_canvas'):
            return
            
        w, h = 350, 180
        
        import colorsys
        
        sv_img = Image.new("RGB", (w, h))
        sv_data = []
        for y in range(h):
            v = 1.0 - (y / h)
            for x in range(w):
                s = x / w
                r, g, b = colorsys.hsv_to_rgb(self.current_hue / 360, s, v)
                sv_data.append((int(r*255), int(g*255), int(b*255)))
        sv_img.putdata(sv_data)
        
        # Add selector crosshair on canvas
        draw = ImageDraw.Draw(sv_img)
        sel_x = int((self.current_sv[0] / 100) * w)
        sel_y = int((1.0 - self.current_sv[1] / 100) * h)
        draw.ellipse([sel_x-4, sel_y-4, sel_x+4, sel_y+4], outline="#fff", width=2)
        
        # Hue Bar
        hw, hh = 30, 150
        hue_img = Image.new("RGB", (hw, hh))
        hue_data = []
        for y in range(hh):
            hue = 1.0 - (y / hh)
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            for x in range(hw):
                hue_data.append((int(r*255), int(g*255), int(b*255)))
        hue_img.putdata(hue_data)
        
        # Add selector line on hue
        draw_h = ImageDraw.Draw(hue_img)
        sel_hy = int((1.0 - self.current_hue / 360) * hh)
        draw_h.line([0, sel_hy, hw, sel_hy], fill="#fff", width=3)
        
        self.sv_canvas.configure(image=ctk.CTkImage(sv_img, sv_img, size=(w, h)))
        self.hue_canvas.configure(image=ctk.CTkImage(hue_img, hue_img, size=(hw, hh)))

    def on_canvas_drag(self, event):
        """Update color based on SV canvas interaction (Fixed size 350x180)"""
        w, h = 350, 180
        x = max(0, min(w, event.x))
        y = max(0, min(h, event.y))
        
        self.current_sv = ((x / w) * 100, (1.0 - (y / h)) * 100)
        self.sync_picker_to_actual()

    def on_hue_drag(self, event):
        """Update color based on Hue bar interaction"""
        h_h = 150
        y = max(0, min(h_h, event.y))
        self.current_hue = (1.0 - (y / h_h)) * 360
        self.sync_picker_to_actual()

    def sync_picker_to_actual(self):
        """Update everything from the HSV picker state"""
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(self.current_hue / 360, self.current_sv[0] / 100, self.current_sv[1] / 100)
        rgb = (int(r*255), int(g*255), int(b*255))
        hex_val = self.rgb_to_hex(rgb)
        
        self.color_vars[self.selected_zone].set(hex_val)
        
        self.update_entry_fields(hex_val, rgb)
        self.render_picker_canvases()
        self.update_keyboard_preview()
        if self.live_preview_var.get():
             self.apply_settings()
             
    def add_to_history(self, hex_val):
        """Add a color to history if it's new and update UI"""
        hex_val = "#" + hex_val.lstrip("#")
        if hex_val == "#333333" or hex_val == "#000000": return # Ignore default/black
        
        if hex_val in self.color_history:
            self.color_history.remove(hex_val)
        self.color_history.insert(0, hex_val)
        self.color_history = self.color_history[:12]
        self.update_history_ui()
        self.save_settings() # Persist history changes

    def update_history_ui(self):
        """Refresh history swatches"""
        if not hasattr(self, 'history_swatches'): return
        for i, hex_c in enumerate(self.color_history):
            self.history_swatches[i].configure(fg_color=hex_c, hover_color=hex_c, 
                                              command=lambda c=hex_c: self.apply_preset(c))

    def on_hex_entered(self, event):
        hex_val = self.hex_entry.get().lstrip("#")
        if re.match(r"^[0-9a-fA-F]{6}$", hex_val):
            self.apply_preset(hex_val)
            self.add_to_history(hex_val)
        
    def on_rgb_entered(self, event):
        try:
             rgb = tuple(int(e.get()) for e in self.rgb_entries)
             hex_val = self.rgb_to_hex(rgb)
             self.apply_preset(hex_val)
             self.add_to_history(hex_val)
        except: pass

    def apply_preset(self, color_hex):
        """Apply a preset color to the selected zone"""
        hex_val = color_hex.lstrip("#")
        self.color_vars[self.selected_zone].set(hex_val)
        
        # Update picker state
        rgb = self.hex_to_rgb(hex_val)
        import colorsys
        h, s, v = colorsys.rgb_to_hsv(rgb[0]/255, rgb[1]/255, rgb[2]/255)
        self.current_hue = h * 360
        self.current_sv = (s * 100, v * 100)
        
        self.update_entry_fields(hex_val, rgb)
        self.render_picker_canvases()
        self.update_keyboard_preview()
        if self.live_preview_var.get():
             self.apply_settings()

    def toggle_zone_power(self, index):
        """Toggle a specific zone between its last color and black (off)"""
        current_hex = self.color_vars[index].get()
        
        if current_hex != "000000":
            # Turn OFF: save current and set to black
            self.last_on_colors[index] = current_hex
            self.apply_preset("000000") if self.selected_zone == index else self.set_zone_silent(index, "000000")
        else:
            # Turn ON: restore last color
            restore_hex = self.last_on_colors[index]
            if restore_hex == "000000": restore_hex = "39c5bb" # Fallback
            self.apply_preset(restore_hex) if self.selected_zone == index else self.set_zone_silent(index, restore_hex)
        
        self.update_control_ui()

    def set_zone_silent(self, index, hex_val):
        """Update a zone color without forcing selection change"""
        hex_val = hex_val.lstrip("#")
        self.color_vars[index].set(hex_val)
        self.update_keyboard_preview()
        if self.live_preview_var.get():
             self.apply_settings()

    def on_preview_click(self, event):
        """Handle clicks on large keyboard preview. Selective focus."""
        # Scale to our 1000x300 internal drawing space
        cx, cy = event.x * 2, event.y * 2
        
        body_padding = 10
        # Matches logic in update_keyboard_preview
        zone_w = (1000 - (body_padding * 4)) // 4
        zone_h = 300 - (body_padding * 6)
        zone_y1 = body_padding * 3
        zone_y2 = zone_y1 + zone_h
        
        found_zone = -1
        # If click is inside the vertical boundary of the zones
        if zone_y1 <= cy <= zone_y2:
            for i in range(4):
                z_x1 = (body_padding * 2) + (i * zone_w)
                z_x2 = z_x1 + zone_w - 5
                if z_x1 <= cx <= z_x2:
                    found_zone = i
                    break
        
        # If found_zone is -1, it means we clicked the keyboard frame/padding
        self.select_zone(found_zone)

    def blink_loop(self):
        """Toggle blink state and redraw keyboard preview for selection feedback"""
        self.blink_active = not self.blink_active
        self.update_keyboard_preview()
        
        # Also pulse physical keyboard if live preview is on
        if self.live_preview_var.get():
            self.apply_settings(is_blink=True)
            
        self.after(600, self.blink_loop)

    def sw_animation_loop(self):
        """Ticker for software-driven lighting effects"""
        effect = self.effect_var.get()
        is_sw = effect in ["Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]
        
        if is_sw:
            self.sw_active_colors = self.calculate_sw_effect(effect)
            self.apply_settings(is_sw_anim=True)
            self.update_keyboard_preview()
            self.sw_animation_step += 1
            
        # Determine timing based on effect and speed
        speed = self.speed_var.get()
        if effect == "Fire":
            delay = {1: 250, 2: 150, 3: 80, 4: 40}.get(speed, 100)
        elif effect == "Scanner":
            delay = {1: 400, 2: 250, 3: 120, 4: 60}.get(speed, 150)
        elif effect == "Police":
            delay = {1: 600, 2: 350, 3: 180, 4: 90}.get(speed, 350)
        elif effect == "Heartbeat":
            sub = self.sw_animation_step % 4
            if sub == 0 or sub == 2: delay = 120
            elif sub == 1: delay = 180
            else: delay = 1200 # Pause between beats
        else:
            delay = {1: 800, 2: 400, 3: 200, 4: 100}.get(speed, 400)
            
        self.after(delay, self.sw_animation_loop)

    def calculate_sw_effect(self, effect):
        """Logic for software lighting animations"""
        step = self.sw_animation_step
        
        if effect == "Police":
             # Alternate flashing Red and Blue
             if step % 2 == 0:
                 return ["ff0000", "ff0000", "0000ff", "0000ff"]
             else:
                 return ["0000ff", "0000ff", "ff0000", "ff0000"]
                 
        elif effect == "Scanner":
             # Red scanner bounce
             idx_map = [0, 1, 2, 3, 2, 1]
             active = idx_map[step % 6]
             res = ["000000"] * 4
             res[active] = self.color_vars[0].get() # Use color from Z1 as theme
             return res
             
        elif effect == "Heartbeat":
             # Double-thump pulse
             sub = step % 4
             if sub == 0 or sub == 2:
                  return [v.get() for v in self.color_vars]
             return ["000000"] * 4
             
        elif effect == "Fire":
             # Rapid randomized intensities of orange/red
             cols = []
             for _ in range(4):
                 r = random.randint(180, 255)
                 g = random.randint(0, 80)
                 cols.append(f"{r:02x}{g:02x}00")
             return cols
             
        elif effect == "Battery":
             # Zone representation of battery percentage
             try:
                data = self.get_battery_status_data()
                p = float(data.get('capacity', 0))
                status = data.get('status', 'Unknown')
             except: p = 0; status = 'Unknown'
             
             # CRITICAL WARNING: 
             low_thresh = self.pref_batt_low.get()
             if p <= low_thresh:
                 if status != "Charging":
                     # Discharging: Blink ALL Red
                     return ["ff0000" if step % 2 == 0 else "000000"] * 4
                 else:
                     # Charging: Solid Zone 1 Red (acknowledgement)
                     return ["ff0000", "000000", "000000", "000000"]
             
             # Calculate how many zones to light up (Progress Bar)
             full_thresh = self.pref_batt_full.get()
             count = 1
             if p >= full_thresh: count = 4
             elif p >= 50: count = 3
             elif p >= 25: count = 2
             
             # Color scaling: Green (Full) -> Yellow (Half) -> Red (Low)
             green_thresh = self.pref_batt_green.get()
             if p >= green_thresh: base_col = (0, 255, 0)      # Green
             elif p >= 45: base_col = (200, 200, 0) # Yellow-Gold
             elif p >= 20: base_col = (255, 120, 0) # Orange
             else: base_col = (255, 0, 0)         # Red
             
             # Suble pulse effect using sw_animation_step
             pulse = 0.7 + (0.3 * abs(math.sin(step * 0.2)))
             active_rgb = tuple(int(c * pulse) for c in base_col)
             active_hex = self.rgb_to_hex(active_rgb)
             
             res = ["000000"] * 4
             for i in range(count):
                 res[i] = active_hex
             return res
             
        elif effect == "Soft Wave":
             # Software rotation of 4 colors
             return [self.color_vars[(step + i) % 4].get() for i in range(4)]
             
        return ["000000"] * 4

    def on_setting_changed(self, *args):
        self.update_control_ui()
        self.update_keyboard_preview()
        if self.live_preview_var.get():
            self.apply_settings()

    # Settings & Profile methods (Copied from previous, simplified)
    def load_profile(self, profile_name):
        if profile_name not in self.profiles and "Default" in self.profiles: profile_name = "Default"
        if profile_name not in self.profiles: return
        p = self.profiles[profile_name]
        self.effect_var.set(p.get("effect", "static"))
        self.brightness_var.set(p.get("brightness", "Low"))
        self.speed_var.set(p.get("speed", 2))
        self.wave_direction_var.set(p.get("wave_direction", "LTR"))
        colors = p.get("colors", [])
        for i, c in enumerate(colors):
            if i < 4: 
                self.color_vars[i].set(c)
                # Update swatches if they exist
                if hasattr(self, 'color_swatches') and i < len(self.color_swatches):
                    self.color_swatches[i].configure(fg_color="#"+c)

        self.current_profile_var.set(profile_name)
        self.update_control_ui()
        if self.live_preview_var.get(): self.apply_settings()

    def add_profile(self):
        dialog = CTkInputDialog(text="Profile Name:", title="New Profile")
        name = dialog.get_input()
        if name and name.strip():
            self.profiles[name.strip()] = self._get_current_settings_dict()
            self.current_profile_var.set(name.strip())
            self.profile_combo.configure(values=list(self.profiles.keys()))
            self.save_settings()

    def delete_profile(self):
        cur = self.current_profile_var.get()
        if cur != "Default" and cur in self.profiles:
            del self.profiles[cur]
            self.load_profile("Default")
            self.profile_combo.configure(values=list(self.profiles.keys()))
            self.save_settings()

    def save_settings(self):
        # Don't save during initial loading to prevent overwriting loaded config
        if hasattr(self, '_is_loading') and self._is_loading:
            return
            
        self.profiles[self.current_profile_var.get()] = self._get_current_settings_dict()
        data = {
            "theme": self.theme_var_str.get(),
            "live_preview": self.live_preview_var.get(),
            "current_profile": self.current_profile_var.get(),
            "color_history": self.color_history,
            "pref_blink_opposite": self.pref_blink_opposite.get(),
            "pref_solo_mode": self.pref_solo_mode.get(),
            "pref_batt_low": self.pref_batt_low.get(),
            "pref_batt_green": self.pref_batt_green.get(),
            "pref_batt_full": self.pref_batt_full.get(),
            "profiles": self.profiles
        }
        try:
            config_path = os.path.join(current_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(data, f)
        except:
            pass

    def load_settings(self):
        config_path = os.path.join(current_dir, "config.json")
        try:
             if os.path.exists(config_path):
                 with open(config_path, "r") as f:
                    data = json.load(f)
                    theme = data.get("theme", "Miku")
                    self.theme_var_str.set(theme)
                    self.live_preview_var.set(data.get("live_preview", False))
                    self.color_history = data.get("color_history", ["#333333"] * 12)
                    self.pref_blink_opposite.set(data.get("pref_blink_opposite", False))
                    self.pref_solo_mode.set(data.get("pref_solo_mode", False))
                    
                    self.pref_batt_low.set(data.get("pref_batt_low", 15))
                    self.pref_batt_green.set(data.get("pref_batt_green", 75))
                    self.pref_batt_full.set(data.get("pref_batt_full", 95))
                    
                    self.profiles = data.get("profiles", {"Default": self._get_current_settings_dict()})
                    self.current_profile_var.set(data.get("current_profile", "Default"))
                    # REMOVED load_profile call here as it triggers UI updates too early
             else:
                 self.profiles = {"Default": self._get_current_settings_dict()}
                 self.theme_var_str.set("Miku")
        except:
             if not hasattr(self, 'profiles') or not self.profiles:
                 self.profiles = {"Default": self._get_current_settings_dict()}
             self.theme_var_str.set("Miku")

    def _get_current_settings_dict(self):
        return {
            "effect": self.effect_var.get(),
            "brightness": self.brightness_var.get(),
            "speed": self.speed_var.get(),
            "wave_direction": self.wave_direction_var.get(),
            "colors": [v.get() for v in self.color_vars]
        }

    def apply_settings(self, is_blink=False, is_sw_anim=False):
        if not self.controller: return
        
        # Don't pulse if effect is not static/breath or if brightness is off
        effect = self.effect_var.get()
        if is_blink and effect not in ["static", "breath"]: return
        if self.brightness_var.get() == "OFF": return

        # Software Animations map to hardware 'static' mode
        hw_effect = effect
        if is_sw_anim or effect in ["Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]:
            hw_effect = "static"

        colors = []
        for i, v in enumerate(self.color_vars):
            # Base color source: software active colors or static vars
            if is_sw_anim or effect in ["Police", "Scanner", "Heartbeat", "Fire", "Battery", "Soft Wave"]:
                hex_val = self.sw_active_colors[i]
            else:
                hex_val = v.get().lstrip("#")
            
            # If this is the "off" phase of the blink and this is the selected zone, handle feedback
            if is_blink and not self.blink_active and i == self.selected_zone and i != -1:
                if self.pref_blink_opposite.get():
                    # Pulse with Inverted Color (Exclusive Pro Feature)
                    colors.append(self.invert_hex(hex_val))
                else:
                    rgb = self.hex_to_rgb(hex_val)
                    # Standard Dim to 30% brightness
                    dim_rgb = tuple(int(c * 0.3) for c in rgb)
                    colors.append(self.rgb_to_hex(dim_rgb))
            elif self.pref_solo_mode.get() and self.selected_zone != -1 and i != self.selected_zone and not is_sw_anim:
                # Solo Mode: Turn off other zones to focus on selected area
                colors.append("000000")
            else:
                colors.append(hex_val)

        try:
            data = self.controller.build_control_string(
                hw_effect, colors, self.speed_var.get(), 
                2 if self.brightness_var.get() == "High" else 1,
                self.wave_direction_var.get() if hw_effect == "wave" else None
            )
            self.controller.send_control_string(data)
            
            # Only save settings for manual changes, not hardware blinks or sw animations
            if not is_blink and not is_sw_anim:
                self.save_settings()
        except: pass

    def set_power_mode(self, choice):
        if choice == "Normal Charging":
            self.power_controller.set_conservation(False)
            self.power_controller.set_rapid(False)
        elif choice == "Conservation Mode":
            self.power_controller.set_conservation(True)
            self.power_controller.set_rapid(False)
        elif choice == "Rapid Charge":
            self.power_controller.set_conservation(False)
            self.power_controller.set_rapid(True)

    def on_closing(self):
        # Instead of quitting, hide to tray
        self.withdraw()
        self.save_settings()

    def quit_app(self, icon=None, item=None):
        """Actually close the application"""
        self.save_settings()
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.stop()
        self.quit()
        self.destroy()
        os._exit(0)

    def show_window(self, icon=None, item=None):
        """Bring the window back from the tray"""
        self.deiconify()
        self.lift()
        self.focus_force()

    def setup_tray(self):
        """Initialize the system tray icon"""
        # Create a simple icon using our existing get_icon method
        # We need a PIL image for pystray
        img = self.get_icon("bolt", self.c_accent, 64) 
        # get_icon returns a CTkImage, we need the raw PIL image if possible or recreate it
        
        # Helper to get raw PIL image for tray
        side = 64
        tray_img = Image.new("RGBA", (side, side), (0,0,0,0))
        draw = ImageDraw.Draw(tray_img)
        points = [(side*0.6, side*0.1), (side*0.2, side*0.55), (side*0.5, side*0.55), 
                  (side*0.4, side*0.9), (side*0.8, side*0.45), (side*0.5, side*0.45)]
        draw.polygon(points, fill=self.c_accent)

        menu = (
            item('Show Legion Control', self.show_window, default=True),
            item('Exit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("legioncontrol", tray_img, "Legion Control", menu)
        
        # Start tray in a background thread so it doesn't block mainloop
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def start_instance_listener(self):
        """Listen for signals from new instances to show window"""
        def listen():
            try:
                # Use a high port for local communication
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # Allow address reuse
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(('127.0.0.1', 65432))
                server.listen(1)
                while True:
                    conn, addr = server.accept()
                    data = conn.recv(1024).decode()
                    if data == "show":
                        self.after(0, self.show_window)
                    conn.close()
            except:
                pass # Already running instance handles this

        threading.Thread(target=listen, daemon=True).start()

def check_single_instance():
    """Returns True if this is the only instance, or contacts existing one and returns False"""
    try:
        # Try to contact existing instance
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1.0)
        client.connect(('127.0.0.1', 65432))
        client.send("show".encode())
        client.close()
        return False # Existing instance found and notified
    except:
        return True # No existing instance found

if __name__ == "__main__":
    if check_single_instance():
        app = LegionLightApp()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    else:
        # App is already running and has been notified to show window
        sys.exit(0)
