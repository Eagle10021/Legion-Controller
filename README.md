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
*   **Software-Driven Animations**: Custom-coded patterns that expand hardware capability:
    *   **Police Strobe**: Alternates rapid red and blue flashes across keyboard halves.
    *   **Scanner**: A single beam that bounces back and forth across the four zones.
    *   **Heartbeat**: A cinematic double-pulse rhythm.
    *   **Fire Flicker**: Randomized warm-tone intensities simulating a live flame.
    *   **Soft Wave**: A software-cycled rotation of your four chosen custom colors.
*   **Gradient Generator**: Automatically calculates smooth color transitions for the middle zones by interpolating between your selections for Zone 1 and Zone 4.

### Intelligent Battery Insight
*   **Interactive Keyboard Gauge**: In Battery mode, the physical keyboard becomes a live progress bar.
    *   **Dynamic Progress**: 0-24% (Zone 1), 25-49% (Zones 1-2), 50-94% (Zones 1-3), 95%+ (All Zones).
    *   **Color Mapping**: Transitions from Red (Low) to Orange, Yellow-Gold, and finally Green (above 75%).
    *   **BIOS Optimization**: The 100% "Full" state triggers at 95% charge to account for laptop BIOS limits that often stop charging at 96-98%.
*   **Critical Alerts**:
    *   **Emergency Pulse**: The entire keyboard blinks red when battery drops to 15% or lower while discharging.
    *   **Charging Awareness**: If plugged in but still under 15%, the alarm calms to a single red blink on Zone 1 only.

### System Dashboard and Tools
*   **Hardware Monitoring**: Real-time display of CPU, GPU, and RAM specifications.
*   **Advanced Battery Diagnostics**: Beyond simple percentage, the dashboard tracks:
    *   **Customizable Thresholds**: Set your own limits for Low Battery Alerts (Blink), Safe Levels (Green Shift), and Full Bar Triggers (BIOS Adjustment) directly in the settings menu.
    *   **Real-time Wattage**: Monitor exact discharge or charge speed in Watts.
    *   **Health Tracking**: Compare current Wh capacity against original design capacity.
    *   **Time Estimates**: Dynamic calculations for time until empty or time until full charge.
*   **Power Mode Control**: Direct toggle for Conservation Mode (limiting charge to 60-80% for battery longevity) and Normal/Rapid charging modes.

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

## Installation

### Prerequisites
The application requires pyusb for hardware communication and customtkinter for the interface.

```bash
# Install dependencies
pip install pyusb customtkinter Pillow
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

## Development and Credits
*   **Backend**: Built on reverse-engineering work from the l5p-kbl projects by Drakanio and Shara.
*   **Icon**: Senko Loaf (images/Senko_Loaf.jpg).
*   **Optimization**: Designed for the Lenovo Legion 5 Pro and similar 4-zone RGB laptop models.
