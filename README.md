# Legion Controller

A graphical user interface for controlling keyboard lighting and power settings on Lenovo Legion laptops.

## Prerequisites

This application relies on the `l5p-kbl` backend to communicate with the keyboard controller.

**Please follow the installation instructions here first:**
[https://github.com/Drakanio/l5p-kbl-2024-Gen9](https://github.com/Drakanio/l5p-kbl-2024-Gen9)

## Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/Eagle10021/Legion-Controller.git
   cd Legion-Controller
   ```

2. Install Python dependencies:
   ```bash
   pip install customtkinter Pillow PyUSB
   ```

3. Set up the `l5p-kbl` backend as instructed in the link above.

4. Run the application:
   ```bash
   python3 Legion_KBLight.py
   ```

## Creating a Desktop Shortcut

To make the app easily accessible from your applications menu, you can create a `.desktop` file pointing to `Legion_KBLight.py`.
