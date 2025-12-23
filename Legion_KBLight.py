#!/usr/bin/env python3

import os
import sys
import json
import re
import platform
import subprocess
import math
import usb.core
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
        self.color_vars = [ctk.StringVar(value="ff0000") for _ in range(4)]
        self.wave_direction_var = ctk.StringVar(value="LTR")
        
        self.cache_file = os.path.join(current_dir, "sys_info_cache.json")
        self.sys_info_cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f: self.sys_info_cache = json.load(f)
            except: pass
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
        
        # 2. Sync theme button (without triggering save)
        self.after(60, lambda: self.theme_seg.set(self.theme_var_str.get()))
        
        # 3. Reload profile colors specialized for swatches
        # MUST CALL THIS AFTER UI IS BUILT
        self.after(80, lambda: self.load_profile(self.current_profile_var.get()))
        
        # 4. Apply final hardware settings
        self.after(150, self.apply_settings)
        
        # 5. Apply theme to all dynamic elements (still locked)
        self.after(200, lambda: self.toggle_theme_str(self.theme_var_str.get()))
        
        # 6. UNLOCK SAVING & ACTIVATE AUTO-SAVE TRACE
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
        
        # --- Header (Packed Top) ---
        header = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        header.pack(side="top", fill="x", padx=40, pady=(35, 20))
        
        # Logo & Title Left
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left")
        
        # Icon Container (simplified - no image loading)
        icon_container = ctk.CTkFrame(title_frame, width=50, height=50, corner_radius=25, 
                                      fg_color="#222", border_width=2, border_color="#333")
        icon_container.pack_propagate(False) 
        icon_container.pack(side="left", padx=(0, 15))
        
        # Icon label (using emoji/unicode icon)
        ctk.CTkLabel(icon_container, text="⚡", font=("Segoe UI", 28), 
                    text_color=self.c_text, fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")
        
        # Track for theme updating
        if not hasattr(self, "accent_frames"): self.accent_frames = []
        icon_container.is_logo = True
        self.accent_frames.append(icon_container)
        
        ctk.CTkLabel(title_frame, text="LEGION CONTROL", font=("Segoe UI", 28, "bold"), text_color=self.c_text).pack(side="left")
        
        # Right Side Header Controls
        theme_frame = ctk.CTkFrame(header, fg_color="transparent")
        theme_frame.pack(side="right")
        
        # System Info Button (Device Name)
        # Use cached device name if available, otherwise use placeholder
        device_name = self.sys_info_cache.get("Device", "System Info") if self.sys_info_cache else "System Info"
        
        ctk.CTkButton(theme_frame, text=device_name, width=150, height=32, fg_color="#2b2b2b", hover_color="#3a3a3a", 
                      corner_radius=8, font=("Segoe UI", 12, "bold"), command=self.show_system_info).pack(side="left", padx=(0, 25))
        
        # Better Theme Toggle (Segmented style)
        self.theme_seg = ctk.CTkSegmentedButton(theme_frame, values=["Miku", "Teto", "Neru"], variable=self.theme_var_str,
                                                width=150,
                                                selected_color=self.c_accent, selected_hover_color=self.c_accent,
                                                unselected_color="#2b2b2b", unselected_hover_color="#3a3a3a")
        self.theme_seg.pack(side="left")

        # --- Footer (Packed Bottom) ---
        # Pack footer BEFORE content to ensure it sticks to the bottom and isn't pushed off by expandable content
        footer = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=40, pady=30)
        
        ctk.CTkCheckBox(footer, text="Live Preview", variable=self.live_preview_var, text_color=self.c_text_sec, font=("Segoe UI", 13), border_width=2).pack(side="left")
        
        self.apply_btn = ctk.CTkButton(footer, text="APPLY SETTINGS", height=45, width=220, 
                                       font=("Segoe UI", 15, "bold"), fg_color=self.c_accent, text_color="#000", corner_radius=8,
                                       command=self.apply_settings)
        self.apply_btn.pack(side="right")

        # --- Content Area (Scrollable, Fills Remaining Space) ---
        content = ctk.CTkScrollableFrame(self.root_frame, fg_color="transparent", corner_radius=0)
        content.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 10))
        
        # Left Column: Profiles & Power
        left_col = ctk.CTkFrame(content, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 20))
        
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
        
        # Battery Status
        self.battery_label = ctk.CTkLabel(power_content_frame, text=f"Battery: {self.get_battery_status()}", 
                                         text_color=self.c_accent, font=("Segoe UI", 12, "bold"))
        self.battery_label.pack(anchor="w", pady=(10,10))
        
        # Update battery status every 30 seconds
        self.update_battery_status()
        
        if self.power_controller.has_conservation or self.power_controller.has_rapid:
            ctk.CTkLabel(power_content_frame, text="Charging Mode", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(10,5))
            
            modes = ["Normal Charging"]
            if self.power_controller.has_conservation: modes.append("Conservation Mode")
            if self.power_controller.has_rapid: modes.append("Rapid Charge")
            
            ctk.CTkOptionMenu(power_content_frame, variable=self.power_mode_var, values=modes, command=self.set_power_mode,
                              fg_color="#333", button_color="#222", corner_radius=6).pack(fill="x", pady=(0, 5))
            
            ctk.CTkLabel(power_content_frame, text="Conservation ~60% or 80% Limit (model dependent). Rapid = Fast Charge. Normal Mode = Standard.", font=("Segoe UI", 11), text_color="#555", wraplength=300).pack(anchor="w", pady=(5,0))
            
            if not self.power_controller.has_rapid:
                 ctk.CTkLabel(power_content_frame, text="Note: Rapid Charge may be missing due to kernel/firmware limitations on Linux.", font=("Segoe UI", 10), text_color="#444", wraplength=300).pack(anchor="w", pady=(5,0))

        else:
             ctk.CTkLabel(power_content_frame, text="Power management not available.", text_color="#555").pack()

        # Right Column: Lighting & Colors (Merged)
        right_col = ctk.CTkFrame(content, fg_color="transparent")
        right_col.pack(side="right", fill="both", expand=True)
        
        light_content_frame = self.create_card(right_col, "LIGHTING & COLOR")
        
        # -- Lighting Controls --
        ctk.CTkLabel(light_content_frame, text="Effect Mode", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(10,5))
        ctk.CTkOptionMenu(light_content_frame, variable=self.effect_var, values=["static","breath","wave","hue","off"], 
                          command=self.on_setting_changed, fg_color="#333", button_color="#222", corner_radius=6).pack(fill="x", pady=(0, 15))
        
        # Brightness & Speed Row
        self.row_bs = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        self.row_bs.pack(fill="x", pady=5)
        
        # Brightness
        b_frame = ctk.CTkFrame(self.row_bs, fg_color="transparent")
        b_frame.pack(side="left", fill="x", expand=True, padx=(0,10))
        ctk.CTkLabel(b_frame, text="Brightness", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(0,5))
        
        b_btns = ctk.CTkFrame(b_frame, fg_color="transparent")
        b_btns.pack(fill="x")
        self.btn_off = ctk.CTkButton(b_btns, text="OFF", width=50, height=30, fg_color="#333", corner_radius=6, border_width=1, border_color="#333", hover_color="#444", command=lambda: [self.effect_var.set("off"), self.on_setting_changed()])
        self.btn_off.pack(side="left", padx=(0,5))
        self.btn_low = ctk.CTkButton(b_btns, text="LOW", width=50, height=30, fg_color="#333", corner_radius=6, border_width=1, border_color="#333", hover_color="#444", command=lambda: [self.brightness_var.set("Low"), self.on_setting_changed()])
        self.btn_low.pack(side="left", padx=5)
        self.btn_high = ctk.CTkButton(b_btns, text="HIGH", width=50, height=30, fg_color="#333", corner_radius=6, border_width=1, border_color="#333", hover_color="#444", command=lambda: [self.brightness_var.set("High"), self.on_setting_changed()])
        self.btn_high.pack(side="left", padx=5)

        # Speed
        s_frame = ctk.CTkFrame(self.row_bs, fg_color="transparent")
        s_frame.pack(side="right", fill="x", expand=True, padx=(10,0))
        ctk.CTkLabel(s_frame, text="Animation Speed", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(0,5))
        
        s_btns = ctk.CTkFrame(s_frame, fg_color="transparent")
        s_btns.pack(fill="x")
        self.speed_btns = []
        for i in range(1, 5):
             btn = ctk.CTkButton(s_btns, text=str(i), width=40, height=30, fg_color="#333", corner_radius=6, border_width=1, border_color="#333", hover_color="#444", 
                                 command=lambda s=i: [self.speed_var.set(s), self.on_setting_changed()])
             btn.pack(side="left", padx=2)
             self.speed_btns.append(btn)

        # Wave Direction
        self.wave_frame = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        ctk.CTkLabel(self.wave_frame, text="Wave Direction", text_color=self.c_text_sec, font=("Segoe UI", 13)).pack(anchor="w", pady=(15,5))
        self.wave_seg = ctk.CTkSegmentedButton(self.wave_frame, values=["LTR", "RTL"], variable=self.wave_direction_var, 
                               command=self.on_setting_changed, selected_color=self.c_accent, corner_radius=6)
        self.wave_seg.pack(fill="x")

        # Separator between Lighting controls and Colors
        ctk.CTkFrame(light_content_frame, height=1, fg_color="#333").pack(fill="x", pady=25)

        # -- Color Controls --
        
        # Tools Row
        ctk.CTkButton(light_content_frame, text="GENERATE GRADIENT", height=28, fg_color="#333", corner_radius=6, hover_color="#444", 
                      font=("Segoe UI", 11, "bold"), command=self.generate_gradient).pack(anchor="e", pady=(0,15))
        
        # Color Grid
        c_grid = ctk.CTkFrame(light_content_frame, fg_color="transparent")
        c_grid.pack(fill="x")
        c_grid.grid_columnconfigure((0,1,2,3), weight=1) # Even spacing
        
        self.color_swatches = []
        for i in range(4):
            f = ctk.CTkFrame(c_grid, fg_color="transparent")
            f.grid(row=0, column=i)
            ctk.CTkLabel(f, text=f"ZONE {i+1}", font=("Segoe UI", 11, "bold"), text_color="#777").pack(pady=(0,5))
            
            # Swatch
            btn = ctk.CTkButton(f, text="", width=55, height=55, corner_radius=27, fg_color="#" + self.color_vars[i].get(),
                                border_width=2, border_color="#333", command=lambda i=i: self.open_color_wheel(i))
            btn.pack(pady=5)
            self.color_swatches.append(btn)
            
            # Hex entry
            e = ctk.CTkEntry(f, textvariable=self.color_vars[i], width=65, height=25, font=("Consolas", 11), justify="center", 
                             fg_color="#1a1a1a", border_width=1, border_color="#333", corner_radius=12)
            e.pack(pady=5)
    
    
    def get_battery_status(self):
        """Get current battery percentage and charging status"""
        try:
            # Read battery capacity
            capacity_path = "/sys/class/power_supply/BAT0/capacity"
            status_path = "/sys/class/power_supply/BAT0/status"
            
            if os.path.exists(capacity_path):
                with open(capacity_path, 'r') as f:
                    capacity = f.read().strip()
                
                status = "Unknown"
                if os.path.exists(status_path):
                    with open(status_path, 'r') as f:
                        status = f.read().strip()
                
                return f"{capacity}% ({status})"
            return "N/A"
        except:
            return "N/A"
    
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
        # But we can simulate it with a quick scale effect
        pass
    
    def update_battery_status(self):
        """Update battery status label periodically"""
        if hasattr(self, 'battery_label'):
            status = self.get_battery_status()
            self.battery_label.configure(text=f"Battery: {status}")
        # Schedule next update in 30 seconds
        self.after(30000, self.update_battery_status)
    
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
        # Non-blocking focus: try to grab focus without wait_visibility if possible
        try:
            top.grab_set()
            top.focus_set()
        except:
            # Fallback for some window managers: try again in 10ms
            self.after(10, lambda: [top.grab_set() if top.winfo_exists() else None])
        
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
        card.pack(fill="x", pady=(0, 20))
        
        # Colored accent line at top
        accent = ctk.CTkFrame(card, height=3, fg_color=self.c_accent, corner_radius=0)
        accent.pack(fill="x")
        
        # Track for theme updating
        if not hasattr(self, "accent_frames"): self.accent_frames = []
        # Mark as header for clarity
        accent.is_header = True 
        self.accent_frames.append(accent)
        
        # Title with padding
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 12, "bold"), text_color="#666").pack(anchor="w", padx=25, pady=(20, 5))
        
        # Content frame (returned to be used as parent for widgets)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=25, pady=(0, 25))
        
        return content

    def toggle_theme_str(self, choice=None):
        # Update colors based on selection
        val = self.theme_var_str.get()
        if val == "Teto":
            self.c_accent = "#d03a58" # Red/Pink
        elif val == "Neru":
             self.c_accent = "#e4d935" # Yellow
        else: # Miku
            self.c_accent = "#39c5bb" # Teal
            
        # Update active UI elements if they exist
        if hasattr(self, "apply_btn"):
            self.apply_btn.configure(fg_color=self.c_accent)
            
        if hasattr(self, "wave_seg"): 
            self.wave_seg.configure(selected_color=self.c_accent)
            
        if hasattr(self, "theme_seg"): 
             self.theme_seg.configure(selected_color=self.c_accent, selected_hover_color=self.c_accent)
             
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
        if hasattr(self, 'battery_label'):
            self.battery_label.configure(text_color=self.c_accent)
        
        if hasattr(self, 'btn_off'): # Simple check to see if UI is ready
            self.update_control_ui()
            
        self.save_settings()

    def update_control_ui(self, *args):
        # Update styling of active buttons (simulating radio behavior for buttons)
        
        # Brightness
        b_val = "Low" if self.brightness_var.get() == "Low" else "High"
        if self.effect_var.get() == "off": b_val = "OFF"
        
        for b, v in [(self.btn_off, "OFF"), (self.btn_low, "Low"), (self.btn_high, "High")]:
             if v == b_val:
                 b.configure(fg_color=self.c_accent, text_color="#000", border_color=self.c_accent)
             else:
                 b.configure(fg_color="transparent", text_color=self.c_text, border_color="#333")

        # Speed
        s_val = self.speed_var.get()
        for b in self.speed_btns:
            if str(s_val) == b.cget("text"):
                 b.configure(fg_color=self.c_accent, text_color="#000", border_color=self.c_accent)
            else:
                 b.configure(fg_color="transparent", text_color=self.c_text, border_color="#333")
                 
        # Wave Visibility
        if self.effect_var.get() == "wave":
            # Pack after brightness/speed row so it's in the right spot
            self.wave_frame.pack(fill="x", pady=5, after=self.row_bs)
        else:
            self.wave_frame.pack_forget()

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
        return "{:02x}{:02x}{:02x}".format(*rgb)

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

    def on_setting_changed(self, *args):
        self.update_control_ui()
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

    def apply_settings(self):
        if not self.controller: return
        colors = [v.get() for v in self.color_vars] if self.effect_var.get() in ["static","breath"] else None
        try:
            data = self.controller.build_control_string(
                self.effect_var.get(), colors, self.speed_var.get(), 
                2 if self.brightness_var.get() == "High" else 1,
                self.wave_direction_var.get() if self.effect_var.get() == "wave" else None
            )
            self.controller.send_control_string(data)
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
        # Hide window immediately so user doesn't see slow destruction
        self.withdraw()
        self.save_settings()
        self.quit()
        self.destroy()

if __name__ == "__main__":
    app = LegionLightApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
