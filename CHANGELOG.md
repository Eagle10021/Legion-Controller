# Changelog

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
