"""
"Needs attention" tracking: other programs report that they are waiting for the user, and the keyboard flashes.

Reports arrive over the session D-Bus:
    org.legioncontrol.Attention.Set(source: string, waiting: bool)
Each source is tracked separately, so the flash continues until every source has been answered.

KDE windows asking for attention are reported by a KWin script (assets/attention_kwin.js) that the app loads.
tools/attention_hook.py reports Claude Code sessions. Anything else can use gdbus or busctl.
"""
import colorsys
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

SERVICE = "org.legioncontrol.Attention"
OBJECT_PATH = "/org/legioncontrol/Attention"
KWIN_PLUGIN = "legion-control-attention"
KWIN_SCRIPT = os.path.join(os.path.dirname(__file__), "assets", "attention_kwin.js")
MAX_WAIT_S = 3600  # a source that never reports back (crashed terminal, closed session) stops flashing after this

_INTROSPECTION = f"""
<node>
  <interface name="{SERVICE}">
    <method name="Set">
      <arg type="s" name="source" direction="in"/>
      <arg type="b" name="waiting" direction="in"/>
    </method>
  </interface>
</node>
"""


class AttentionTracker:
    """The sources currently waiting for the user. Safe to use from any thread."""

    def __init__(self, max_wait=MAX_WAIT_S, clock=time.monotonic):
        self._lock = threading.Lock()
        self._expiry = {}
        self._max_wait = max_wait
        self._clock = clock

    def set(self, source, waiting, ttl=None):
        with self._lock:
            if waiting:
                self._expiry[source] = self._clock() + (self._max_wait if ttl is None else ttl)
            else:
                self._expiry.pop(source, None)

    def active(self):
        """True while at least one source is still waiting."""
        now = self._clock()
        with self._lock:
            self._expiry = {source: end for source, end in self._expiry.items() if end > now}
            return bool(self._expiry)


def material_you_color():
    """The desktop accent as a vivid 'rrggbb' for the keyboard, or None if KDE's colours can't be read."""
    path = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "kdeglobals")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f]
    except OSError:
        return None
    start = lines.index("[Colors:Selection]") + 1 if "[Colors:Selection]" in lines else None
    if start is None:
        return None
    for line in lines[start:]:
        if line.startswith("["):
            return None
        if line.startswith("DecorationFocus="):
            return _vivid(line.partition("=")[2])
    return None


def _vivid(value):
    """Material You accents are pastel, which RGB keys show as near white: keep the hue, raise the saturation."""
    value = value.strip().lstrip("#")
    try:
        if "," in value:
            rgb = [int(part) for part in value.split(",")[:3]]
        else:
            rgb = [int(value[i:i + 2], 16) for i in range(0, 6, 2)]
        hue, sat, _ = colorsys.rgb_to_hsv(*(max(0, min(255, c)) / 255 for c in rgb))
    except (ValueError, TypeError):
        return None
    if sat < 0.08:  # grey has no hue to keep
        return "ffffff"
    return "".join(f"{round(c * 255):02x}" for c in colorsys.hsv_to_rgb(hue, max(sat, 0.9), 1.0))


def _load_gio():
    """Gio from PyGObject, or None where it is not installed (the flash then has no sources)."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        return Gio, GLib
    except (ImportError, ValueError) as e:
        log.warning("D-Bus is unavailable, so nothing can report that it needs attention: %s", e)
        return None


def start_service(tracker):
    """Publish the D-Bus service on a background thread with its own GLib context (the tray icon uses the default one)."""
    modules = _load_gio()
    if modules:
        threading.Thread(target=_serve, args=(tracker, *modules), daemon=True, name="attention-dbus").start()


def _serve(tracker, Gio, GLib):
    context = GLib.MainContext.new()
    context.push_thread_default()

    def on_call(_conn, _sender, _path, _iface, method, params, invocation):
        if method == "Set":
            source, waiting = params.unpack()
            tracker.set(source, waiting)
        invocation.return_value(None)

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        interface = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION).interfaces[0]
        bus.register_object(OBJECT_PATH, interface, on_call, None, None)
        Gio.bus_own_name_on_connection(bus, SERVICE, Gio.BusNameOwnerFlags.NONE, None, None)
    except GLib.Error as e:
        log.warning("Could not publish %s: %s", SERVICE, e.message)
        return
    GLib.MainLoop.new(context, False).run()


def set_kwin_watcher(enabled):
    """Load or unload the KWin script. Does nothing outside KDE. Blocks briefly, so call it off the UI thread."""
    modules = _load_gio()
    if not modules:
        return
    Gio, GLib = modules

    def scripting(bus, method, args, reply):
        return bus.call_sync("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", method, args,
                             GLib.VariantType(reply), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        scripting(bus, "unloadScript", GLib.Variant("(s)", (KWIN_PLUGIN,)), "(b)")
        if enabled:
            script_id = scripting(bus, "loadScript", GLib.Variant("(ss)", (KWIN_SCRIPT, KWIN_PLUGIN)), "(i)")
            bus.call_sync("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script", "run", None, None,
                          Gio.DBusCallFlags.NONE, 3000, None)
    except GLib.Error as e:
        log.info("KWin window watcher not changed: %s", e.message)
