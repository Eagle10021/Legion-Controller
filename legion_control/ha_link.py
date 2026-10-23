"""
Home Assistant link.

Push (laptop -> HA): sensor.legion_battery, sensor.legion_keyboard and sensor.legion_power_profile through
HA's REST API, on every change and at least every 30 s.

Commands (HA -> laptop): an HTTP server on the configured address (meant to be the Tailscale IP):
    POST /keyboard   JSON with any of: effect, color (all zones), colors (4), brightness (Low/High/Off),
                     speed (1-4), profile.   Needs "Authorization: Bearer <command_token>".
Commands are queued; the UI thread picks them up (Tk must only be touched from its own thread).
"""
import json
import logging
import queue
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class HALink:
    def __init__(self, config):
        self.config = config
        self.commands = queue.Queue()
        self._outbox = queue.Queue(maxsize=1)
        self._last_sent = None
        self._server = None
        self._retry = None
        self._closed = False
        self.status = "Off"
        if not config.get("enabled") or not config.get("url") or not config.get("token"):
            return
        threading.Thread(target=self._push_worker, daemon=True, name="ha-push").start()
        if config.get("listen") and config.get("command_token"):
            self._start_server()
        self.status = "Connecting"

    @property
    def enabled(self):
        return self.status != "Off"

    def close(self):
        """Stop pushing and listening (used when the settings change; a new HALink takes over)."""
        self._closed = True
        self.status = "Off"
        if self._retry:
            self._retry.cancel()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self._outbox.put(None)  # wakes the push worker so it can exit

    # --- pushing ---
    def publish(self, snapshot, force=False):
        """Queue a state snapshot; only the newest one is kept. Unchanged snapshots are skipped unless forced."""
        if not self.enabled or (snapshot == self._last_sent and not force):
            return
        try:
            self._outbox.get_nowait()
        except queue.Empty:
            pass
        try:
            self._outbox.put_nowait(snapshot)
        except queue.Full:  # the worker grabbed the old one in between; the next change will catch up
            pass

    def _push_worker(self):
        while True:
            snapshot = self._outbox.get()
            if snapshot is None or self._closed:
                return
            try:
                for entity_id, body in _entities(snapshot):
                    self._post(f"/api/states/{entity_id}", body)
                self._last_sent = snapshot
                self.status = "Connected"
            except Exception as e:  # network down, HA restarting, bad token ...
                self.status = f"Error: {e}"
                log.warning("Home Assistant push failed: %s", e)

    def _post(self, path, body):
        req = urllib.request.Request(self.config["url"].rstrip("/") + path, method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.config['token']}",
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()

    # --- commands ---
    def _start_server(self):
        if self._closed:
            return
        link = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.headers.get("Authorization") != f"Bearer {link.config['command_token']}":
                    return self._reply(401, {"error": "unauthorized"})
                if self.path != "/keyboard":
                    return self._reply(404, {"error": "not found"})
                try:
                    length = min(int(self.headers.get("Content-Length", 0)), 4096)
                    cmd = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(cmd, dict):
                        raise ValueError("expected a JSON object")
                except ValueError as e:
                    return self._reply(400, {"error": str(e)})
                link.commands.put(cmd)
                self._reply(200, {"queued": True})

            def log_message(self, *args):
                pass

        try:
            self._server = ThreadingHTTPServer((self.config["listen"], int(self.config.get("port", 47125))), Handler)
        except OSError as e:  # e.g. Tailscale not up yet
            log.warning("HA command server could not listen on %s: %s (retrying in 30 s)", self.config["listen"], e)
            self._retry = threading.Timer(30, self._start_server)
            self._retry.daemon = True
            self._retry.start()
            return
        threading.Thread(target=self._server.serve_forever, daemon=True, name="ha-commands").start()


def _entities(s):
    """(entity_id, state body) pairs from an app snapshot."""
    b, k = s["battery"], s["keyboard"]
    yield "sensor.legion_battery", {
        "state": b["capacity"],
        "attributes": {"friendly_name": "Legion battery", "unit_of_measurement": "%", "device_class": "battery",
                       "state_class": "measurement", "status": b["status_text"], "charge_mode": s["charge_mode"],
                       "power_w": round(b["wattage"], 1),
                       "health_pct": round(b["health"], 1) if b["health"] is not None else None,
                       "estimate": b["time_str"]}}
    yield "sensor.legion_keyboard", {
        "state": k["effect_label"],
        "attributes": {"friendly_name": "Legion keyboard", "icon": "mdi:keyboard-variant", "effect": k["effect"],
                       "colors": ["#" + c for c in k["colors"]], "brightness": k["brightness"], "speed": k["speed"],
                       "profile": k["profile"], "profiles": k["profiles"], "effects": k["effects"],
                       "theme": s["theme"]}}
    yield "sensor.legion_power_profile", {
        "state": s["power_profile"] or "unknown",
        "attributes": {"friendly_name": "Legion power profile", "icon": "mdi:speedometer"}}
