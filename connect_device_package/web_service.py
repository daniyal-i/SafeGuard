#!/usr/bin/env python3
"""Loopback-only bridge between the dashboard and the local detector scripts."""

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError


HOST = "127.0.0.1"
PORT = 8765
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PACKAGE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = PACKAGE_DIR.parent / "dashboard"
IMAGE_DETECTOR_PATH = PACKAGE_DIR / "image-detect.py"
_IMAGE_DETECTOR = None
_IMAGE_DETECTOR_LOCK = threading.Lock()


def load_image_detector():
    global _IMAGE_DETECTOR
    with _IMAGE_DETECTOR_LOCK:
        if _IMAGE_DETECTOR is None:
            spec = importlib.util.spec_from_file_location("safeguard_image_detector", IMAGE_DETECTOR_PATH)
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load the image detector module.")
            _IMAGE_DETECTOR = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_IMAGE_DETECTOR)
        return _IMAGE_DETECTOR


class DetectorController:
    def __init__(self):
        self.lock = threading.RLock()
        self.audio_thread = None
        self.audio_stop = None
        self.audio_status = "Stopped."
        self.audio_running = False
        self.events = []
        self.last_dashboard_seen = 0.0

    def state(self):
        with self.lock:
            self.last_dashboard_seen = time.monotonic()
            return {
                "audio": {
                    "running": self.audio_running,
                    "status": self.audio_status,
                },
                "events": list(self.events),
            }

    def add_event(self, event):
        with self.lock:
            self.events.insert(0, event)
            del self.events[20:]

    def start_audio(self):
        with self.lock:
            if self.audio_thread and self.audio_thread.is_alive():
                return False
            self.last_dashboard_seen = time.monotonic()
            self.audio_stop = threading.Event()
            self.audio_running = True
            self.audio_status = "Starting audio detector…"
            self.audio_thread = threading.Thread(
                target=self._run_audio,
                args=(self.audio_stop,),
                name="safeguard-audio-detector",
                daemon=True,
            )
            self.audio_thread.start()
            return True

    def stop_audio(self):
        with self.lock:
            if not self.audio_running:
                self.audio_status = "Stopped."
                return False
            self.audio_status = "Stopping audio detector…"
            self.audio_stop.set()
            return True

    def _run_audio(self, stop_event):
        error = None

        def set_status(message):
            with self.lock:
                self.audio_status = str(message)

        def record_detection(detection):
            detection["source"] = "audio"
            detection["detected_at"] = datetime.now().astimezone().isoformat()
            self.add_event(detection)

        try:
            spec = importlib.util.spec_from_file_location("safeguard_audio_detector", PACKAGE_DIR / "detect.py")
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load the audio detector module.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.run_detection(
                stop_event=stop_event,
                on_status=set_status,
                on_detection=record_detection,
            )
        except Exception as exc:
            error = f"Audio detector error: {exc}"
        finally:
            with self.lock:
                self.audio_running = False
                self.audio_status = error or "Stopped."

    def analyze_image(self, image):
        module = load_image_detector()
        detections = module.detect_image(image)
        event = {
            "source": "image",
            "label": "Possible firearm detection" if detections else "No firearm detections above the model threshold",
            "detections": detections,
            "detected_at": datetime.now().astimezone().isoformat(),
        }
        self.add_event(event)
        return event


controller = DetectorController()


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SafeGuardLocal/1.0"

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _check_host(self):
        return self.headers.get("Host") == f"{HOST}:{PORT}"

    def _check_origin(self):
        return self.headers.get("Origin") == f"http://{HOST}:{PORT}"

    def do_GET(self):
        if not self._check_host():
            self._json(403, {"error": "Only local dashboard requests are allowed."})
            return

        path = urlsplit(self.path).path
        if path == "/api/state":
            self._json(200, controller.state())
            return

        files = {
            "/": (DASHBOARD_DIR / "index.html", "text/html; charset=utf-8"),
            "/index.html": (DASHBOARD_DIR / "index.html", "text/html; charset=utf-8"),
            "/SafeGuardLogo.png": (DASHBOARD_DIR / "SafeGuardLogo.png", "image/png"),
        }
        entry = files.get(path)
        if entry is None:
            self._json(404, {"error": "Not found."})
            return

        file_path, content_type = entry
        try:
            body = file_path.read_bytes()
        except OSError as exc:
            self._json(500, {"error": f"Could not read dashboard file: {exc}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._check_host() or not self._check_origin():
            self._json(403, {"error": "Only same-origin local dashboard requests are allowed."})
            return

        path = urlsplit(self.path).path
        if path in {"/api/audio/start", "/api/audio/stop"}:
            if self.headers.get("Content-Length", "0") != "0":
                self._json(400, {"error": "This action does not accept a request body."})
                return
            changed = controller.start_audio() if path.endswith("/start") else controller.stop_audio()
            self._json(200, {"started" if path.endswith("/start") else "stopping": changed,
                             **controller.state()})
            return

        if path != "/api/image/detect":
            self._json(404, {"error": "Not found."})
            return

        content_type = self.headers.get_content_type()
        if content_type not in ALLOWED_IMAGE_TYPES:
            self._json(415, {"error": "Use a JPEG, PNG, or WebP image."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid content length."})
            return
        if content_length <= 0 or content_length > MAX_IMAGE_BYTES:
            self._json(413, {"error": "Image must be between 1 byte and 10 MB."})
            return

        try:
            image_bytes = self.rfile.read(content_length)
            if len(image_bytes) != content_length:
                self._json(400, {"error": "Incomplete image upload."})
                return
            with Image.open(io.BytesIO(image_bytes)) as image_file:
                if image_file.format not in {"JPEG", "PNG", "WEBP"}:
                    self._json(415, {"error": "Use a JPEG, PNG, or WebP image."})
                    return
                if image_file.width * image_file.height > MAX_IMAGE_PIXELS:
                    self._json(413, {"error": "Image dimensions exceed the 20-megapixel limit."})
                    return
                image_file.verify()
            with Image.open(io.BytesIO(image_bytes)) as image_file:
                image = image_file.convert("RGB")
            try:
                result = controller.analyze_image(image)
            finally:
                image.close()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            self._json(400, {"error": f"Could not read image: {exc}"})
            return
        except Exception as exc:
            self._json(500, {"error": f"Image analysis failed: {exc}"})
            return
        self._json(200, result)

    def log_message(self, format_string, *args):
        print(f"[dashboard] {self.address_string()} - {format_string % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"SafeGuard dashboard: http://{HOST}:{PORT}/")
    print("Local microphone/camera data is handled on this computer.")
    shutdown_event = threading.Event()

    def stop_orphaned_audio():
        while not shutdown_event.wait(2):
            with controller.lock:
                disconnected = (
                    controller.audio_running
                    and time.monotonic() - controller.last_dashboard_seen > 8
                )
            if disconnected:
                controller.stop_audio()

    watchdog = threading.Thread(target=stop_orphaned_audio, name="safeguard-ui-watchdog", daemon=True)
    watchdog.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SafeGuard dashboard.")
    finally:
        shutdown_event.set()
        controller.stop_audio()
        server.server_close()


if __name__ == "__main__":
    main()
