# Changelog

## [3.0.0] - 2026-10-23
### Changed
- **Restructured** from one 2,150-line file into the `legion_control/` package (hardware, battery, effects, themes, settings, Home Assistant link, widgets, window). `Legion_KBLight.py` is now a small launcher under the same name, so `run.sh` and existing shortcuts keep working.
- **New UI:** effect buttons with icons (hardware and software rows), battery card with a level-accurate battery icon and stat rows, charging mode as three buttons, header with device name, footer with a Live preview switch, status line and Home Assistant pill.
- **Keyboard drawing** now matches the real Legion 5 Gen 6 layout (20-key function row, numpad with tall + and Enter, arrow keys below the bottom row), redraws at the window's size, and outlines the keys of the selected zone.
- **Icons** are Material Design Icons from a bundled 7.5 KB font subset instead of hand-drawn shapes and emoji.
- **Settings** moved to `~/.config/legion-control/config.json` (written atomically, permissions `0600`); the old `config.json` is migrated automatically. Settings are saved a second after the last change instead of on every keyboard update.
- Fonts: Noto Sans / Noto Sans Mono (the old Segoe UI / Consolas don't exist on Linux).
- Single-instance check uses a Unix socket in `$XDG_RUNTIME_DIR` instead of TCP port 65432.
- Charging mode changes need one password prompt instead of up to two, run without freezing the window, and read back the real state afterwards.

### Added
- Themes: Phrolova, Shorekeeper, Encore and MaoMao (next to Miku, Teto and Neru), with matching colour presets.
- **Home Assistant link:** pushes battery, charging mode, power profile and keyboard state; accepts keyboard commands (effect, colour(s), brightness, speed, profile) over HTTP with a token. Configured in Settings and applied without restarting. Example HA package in `examples/home-assistant/`.
- Power profile (Fn+Q mode) and time estimate in the battery card; "Held by Conservation Mode" instead of a bare "Not charging".
- `--hidden` (start in the tray) and `--verbose` (log to the terminal) launch options.
- `tools/make_icon_font.py` to add icons.
- Home Assistant commands for **charging mode** and **power profile** (Fn+Q), plus example scripts for per-zone colours and animation speed.
- `extras/99-legion-control-power.rules`: optional udev rule so the `power` group can change charging mode and power profile without a password prompt.

### Fixed
- With no zone selected, the colour picker, presets and recent colours silently recoloured **zone 4** (a `-1` index). They now apply to all zones, as the README always described.
- **Gradient Z1 → Z4** referenced a widget that never existed and did nothing visible until the next refresh.
- The **hue bar** was drawn 150 px tall in a 180 px slot, so picking on it chose the wrong hue.
- The **keyboard preview was clipped** on the right at normal window sizes (fixed 500 px drawing, fixed button spacing).
- With Live preview on, the selection blink sent a USB packet every 600 ms **even with no zone selected**.
- The colour square was rebuilt pixel by pixel in Python on every mouse movement (63,000 pixels); it now uses PIL gradients and is cached per hue.
- The battery refresh rebuilt the keyboard image and icons every second.
- Errors were swallowed by bare `except: pass` everywhere; USB and settings errors are now logged and shown in the status line.
- The tray's Exit touched Tk from the tray thread.

### Removed
- The bundled `CTkColorPicker` library (imported but no longer used).

## [2.1.0] - 2026-01-11
### Added
- **Portable Launch System**: 
    - Added `run.sh` entry point script that automatically handles dependency management.
    - Implemented self-building Virtual Environment (`venv`) support to comply with PEP 668 (externally managed environments) on modern Linux distributions (Arch, Fedora, Ubuntu 24.04+).
    - `run.sh` now uses `--system-site-packages` to ensure proper integration with system-level GTK/AppIndicator libraries for tray icon support.
- **Easy Installer**: Added `install.sh` to automatically generate and register the `.desktop` file for the current location.
- **Requirements**: Added `requirements.txt` for transparent dependency tracking.

### Changed
- **Tray Icon**: Updated the system tray icon to be a static **Gold/Yellow Lightning Bolt** (⚡ style, #FFD700), decoupling it from the dynamic UI theme color for better visibility and consistency.
- **Documentation**: Updated `README.md` to reflect the new installation and launch methods (`./run.sh` instead of `python3 ...`), simplifying the process for end-users.

### Fixed
- **System Tray Menu**: Resolved an issue where the tray icon right-click menu would not appear on some GNOME configurations by ensuring the virtual environment can access system GObject Introspection libraries.
- **Launch Failures**: Fixed startup crashes on systems with strict Python package management policies by isolating dependencies.
