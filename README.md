# Legion Controller

A graphical user interface for controlling keyboard RGB lighting and power modes on Lenovo Legion laptops. This application is designed specifically for 4-zone RGB models and is optimized for Linux environments using Gnome on Wayland.

![Legion Controller Preview](images/preview.png)

## Core Features

### Advanced Lighting Architecture
*   **Zone Management**: Complete control over the four distinct keyboard zones.
    *   **Visual Selection**: Select zones directly by clicking the interactive keyboard preview.
    *   **Power Toggling**: Each zone features an independent power control (lightning bolt icon) to turn specific areas on or off. Active zones display a glowing icon, while inactive zones stay dimmed.
    *   **Deselection Logic**: Click the keyboard bezel or the application background to deselect all zones for global setting application.
*   **Hardware FX**: Direct support for firmware-level Static, Breath, Wave, and Hue effects.
*   **Software-Driven Animations**: Custom-coded patterns that expand hardware capability. Except for the Police effect, these patterns derive their colors from your user-assigned static zone colors.
    *   **Police Strobe**: Alternates rapid red and blue flashes across keyboard halves (Fixed colors).
    *   **Scanner**: A single beam that bounces back and forth across the four zones (Uses Zone 1 color).
    *   **Heartbeat**: A cinematic double-pulse rhythm (Uses all 4 currently assigned zone colors).
    *   **Fire Flicker**: Randomized warm-tone intensities simulating a live flame.
    *   **Soft Wave**: A software-cycled rotation of your four assigned zone colors. Supports direction control (LTR/RTL).
    *   **Battery Gauge**: Transforms the entire keyboard into a live, color-coded power meter that reflects your real-time charge level.
*   **Gradient Generator**: Automatically calculates smooth color transitions for the middle zones by interpolating between your selections for Zone 1 and Zone 4.

### Intelligent Battery Insight
*   **Interactive Keyboard Gauge**: In Battery mode, the physical keyboard becomes a live progress bar.
    *   **Dynamic Progress**: 0-24% (Zone 1), 25-49% (Zones 1-2), 50-94% (Zones 1-3), 95%+ (All Zones).
    *   **Color Mapping**: Transitions from Red (Low) to Orange, Yellow-Gold, and finally Green (above 75%).
    *   **BIOS Optimization**: The 100% "Full" state triggers at 95% charge to account for laptop BIOS limits that often stop charging at 96-98%.
*   **Critical Alerts**:
    *   **Emergency Pulse**: The entire keyboard blinks red when battery drops to 15% or lower while discharging.
    *   **Charging Awareness**: If plugged in but still under the low threshold, the alarm calms to a solid red state on Zone 1 only to acknowledge connection without being distracting.

### System Dashboard and Tools
*   **Hardware Monitoring**: Real-time display of CPU, GPU, and RAM specifications.
*   **Advanced Battery Diagnostics**: Beyond simple percentage, the dashboard tracks:
    *   **Customizable Thresholds**: Set your own limits for Low Battery Alerts (Blink), Safe Levels (Green Shift), and Full Bar Triggers (BIOS Adjustment) via numeric input fields in the settings menu.
    *   **Real-time Wattage**: Monitor exact discharge or charge speed in Watts.
    *   **Health Tracking**: Compare current Wh capacity against original design capacity.
    *   **Time Estimates**: Dynamic calculations for time until empty or time until full charge.
*   **Power Mode Control**: Direct toggle for Conservation Mode (limiting charge to 60-80% for battery longevity) and Normal/Rapid charging modes.
    *   **ACPI Fallback**: Supports raw ACPI calls for Rapid Charge controls on models where standard `ideapad_acpi` drivers are limited (requires `acpi_call` kernel module).

### User Experience and Customization
*   **Focus Utilities**: 
    *   **Blink Focus**: The selected zone pulses to help you identify which area you are editing. Supports color inversion for high-visibility focusing.
    *   **Solo Mode**: Dims all other zones except the one currently selected.
*   **Color Management**: 
    *   **Integrated Picker**: High-precision SV canvas and Hue bar for custom color selection.
    *   **Persistent History**: A 12-slot color history that saves across sessions.
    *   **Presets**: Quick-select buttons for popular character-inspired palettes (Miku, Teto, Neru, Gumi).
*   **Aesthetic Themes**: Selectable UI skins including Miku (Teal), Teto (Red), and Neru (Gold). The UI dynamically adjusts text contrast to ensure black text on light colors and white text on dark colors.
*   **Profile System**: Save, delete, export, and import complete lighting configurations as JSON files.
*   **Centralized Settings**: A dedicated, scrollable settings menu accessible via the header gear icon for managing advanced feedback, battery thresholds, and background behavior.
*   **Automation Center**: A powerful rules engine (accessible via the lightning bolt icon) for smart laptop management:
    *   **Event Routines**: Trigger specific actions (e.g., Set Profile, Change Brightness) when events occur, such as connecting/disconnecting the charger or app startup.
    *   **Time Schedules**: Schedule commands to run automatically at specific times of day.

### Background Persistence and Instance Control
*   **System Tray Integration**: Closing the main window (X button) now minimizes the app to the system tray instead of quitting. This allows software-driven animations and battery monitoring to continue running in the background.
*   **Single-Instance Lock**: The application uses a local socket to ensure only one instance is active.
*   **Intelligent Shortcut Behavior**: If the app is already running in the background, launching it again from a desktop shortcut or the application menu will automatically restore and focus the existing window.
*   **Tray Menu**: Right-click the tray icon to access quick actions, including "Show Legion Control" or a complete "Exit".

> [!NOTE]
> **GNOME Users**: By default, GNOME Shell does not display system tray icons. To see the Legion Controller icon, you must install and enable the **AppIndicator and KStatusNotifierItem Support** extension. On Arch-based systems, you can install it via: `sudo pacman -S gnome-shell-extension-appindicator`

## Installation

### Prerequisites
The application requires pyusb for hardware communication, customtkinter for the interface, and pystray for system tray support.

```bash
# Install dependencies
pip install pyusb customtkinter Pillow pystray
```

### USB Access Permissions (udev)
By default, Linux limits USB device access. You must create a udev rule to run the controller without sudo.

1.  Identify your Keyboard Controller ID:
    ```bash
    lsusb | grep -i "Integrated Technology Express"
    ```
    (Note the four-digit ID after the colon, e.g., c965)

2.  Create the rules file:
    ```bash
    sudo nano /etc/udev/rules.d/99-kblight.rules
    ```

3.  Insert the following (update idProduct if yours differs from c965):
    ```text
    SUBSYSTEM=="usb", ATTR{idVendor}=="048d", ATTR{idProduct}=="c965", MODE="0666"
    ```

4.  Reload the udev system:
    ```bash
    sudo udevadm control --reload-rules && sudo udevadm trigger
    ```

### Desktop Integration (App Menu)
To make Legion Controller appear in your applications menu, create a desktop entry:

1.  Create the file: `nano ~/.local/share/applications/legion-controller.desktop`
2.  Paste the following (Replace `/path/to/folder/` with the actual path to this repository):

```ini
[Desktop Entry]
Type=Application
Name=Legion Controller
Comment=Keyboard RGB and Power Controller
Exec=python3 /path/to/folder/Legion_KBLight.py
Icon=/path/to/folder/images/Senko_Loaf.jpg
Terminal=false
Categories=System;Utility;
```

3. Save and close. The app should now appear in your launcher (GNOME, KDE, etc.).

## Development and Credits
*   **Backend**: Built on reverse-engineering work from the l5p-kbl projects by Drakanio and Shara.
*   **Icon**: Senko Loaf (images/Senko_Loaf.jpg).
*   **Optimization**: Designed for the Lenovo Legion 5 Pro and similar 4-zone RGB laptop models.
