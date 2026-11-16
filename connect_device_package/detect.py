"""
Gunshot detector - hackathon MVP (AWS IoT Core version)
-------------------------------------------------------
Listens to the Mac's microphone, runs Google's pretrained YAMNet audio
classifier, and when it hears a gunshot it publishes an alert to AWS IoT Core
on the topic "sentinel/alerts". Your IoT Rule then sends the email (SNS) and
logs the event (DynamoDB).

Setup:
    1. Put this file in the same folder as your IoT connection kit files
       (the .cert.pem, .private.key and root-CA.crt files).
    2. pip install tensorflow tensorflow-hub sounddevice numpy awsiotsdk
    3. Fill in the four IoT settings below.
    4. python3 gunshot_detector.py
"""

import csv
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import tensorflow as tf
import tensorflow_hub as hub

# ---------------- IoT settings (fill these in) ----------------
# Endpoint: IoT Core > Settings > "Device data endpoint"
#           (also visible after "-e" inside start.sh from the connection kit)
IOT_ENDPOINT = "a64e95diuocuc-ats.iot.us-east-1.amazonaws.com"
CERT_FILE = "MacBookPro.cert.pem"          # file names from your connection kit
KEY_FILE = "MacBookPro.private.key"
CA_FILE = "root-CA.crt"                # start.sh downloads this on first run
# The connection-kit policy usually only allows the client ID "basicPubSub".
CLIENT_ID = "basicPubSub"
TOPIC = "sentinel/alerts"
# ---------------------------------------------------------------

# ---------------- Detector settings you can tune ----------------
ROOM = "Main Hallway"      # shown in the alert and on the dashboard
DEVICE_ID = "mac-01"
THRESHOLD = 0.35           # raise to cut false alarms, lower if real shots are missed
HITS_REQUIRED = 1          # detection windows in a row before alerting
COOLDOWN_SECONDS = 30      # don't send repeat alerts for the same event
# -----------------------------------------------------------------

SAMPLE_RATE = 16000        # YAMNet expects 16 kHz mono
WINDOW_SECONDS = 1.0
HOP_SECONDS = 0.5
TARGET_CLASSES = {"Gunshot, gunfire", "Machine gun", "Fusillade", "Artillery fire", "Cap gun"}


def load_model():
    print("Loading YAMNet model (first run downloads it)...")
    model = hub.load("https://tfhub.dev/google/yamnet/1")
    class_map_path = model.class_map_path().numpy().decode("utf-8")
    with tf.io.gfile.GFile(class_map_path) as f:
        names = [row["display_name"] for row in csv.DictReader(f)]
    target_idx = [i for i, n in enumerate(names) if n in TARGET_CLASSES]
    print("Watching for:", [names[i] for i in target_idx])
    return model, names, target_idx


def connect_iot():
    """Connect to AWS IoT Core. Returns a publish function."""
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder

    base_dir = Path(__file__).resolve().parent
    credentials = [
        Path(name) if Path(name).is_absolute() else base_dir / name
        for name in (CERT_FILE, KEY_FILE, CA_FILE)
    ]
    for path in credentials:
        if not path.is_file():
            raise SystemExit(f"Missing file: {path.name} - put this file in the connection kit folder "
                             f"and check the file names at the top of the script.")

    print(f"Connecting to AWS IoT Core as '{CLIENT_ID}'...")
    conn = mqtt_connection_builder.mtls_from_path(
        endpoint=IOT_ENDPOINT,
        cert_filepath=str(credentials[0]),
        pri_key_filepath=str(credentials[1]),
        ca_filepath=str(credentials[2]),
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
    )
    conn.connect().result()
    print("Connected to AWS IoT Core.")

    def publish(message: dict):
        future, _ = conn.publish(topic=TOPIC, payload=json.dumps(message),
                                 qos=mqtt.QoS.AT_LEAST_ONCE)
        future.result(timeout=10)
        print(f"  -> alert published to {TOPIC}")

    return conn, publish


def run_detection(stop_event=None, on_status=print, on_detection=print, publish_to_iot=True):
    stop_event = stop_event or threading.Event()
    on_status("Loading YAMNet audio model; first run may download it.")
    model, names, target_idx = load_model()
    if stop_event.is_set():
        return
    conn = None
    publish = None
    aws_status = ""
    if publish_to_iot:
        try:
            conn, publish = connect_iot()
        except (Exception, SystemExit) as exc:
            aws_status = f" AWS publishing unavailable: {exc}"

    audio_q = queue.Queue()
    window_len = int(SAMPLE_RATE * WINDOW_SECONDS)
    hop_len = int(SAMPLE_RATE * HOP_SECONDS)
    buffer = np.zeros(window_len, dtype=np.float32)
    pending = np.zeros(0, dtype=np.float32)

    def callback(indata, frames, time_info, status):
        if status:
            on_status(str(status))
        audio_q.put(indata[:, 0].copy())

    hits = 0
    last_alert = 0.0

    on_status(f"Listening in '{ROOM}'.{aws_status}")
    try:
        if stop_event.is_set():
            return
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=hop_len, callback=callback):
            while not stop_event.is_set():
                try:
                    chunk = audio_q.get(timeout=0.25)
                except queue.Empty:
                    continue
                pending = np.concatenate([pending, chunk])
                if len(pending) < hop_len:
                    continue
                chunk, pending = pending[:hop_len], pending[hop_len:]
                buffer = np.concatenate([buffer[hop_len:], chunk])

                scores = model(buffer)[0].numpy()     # (frames, 521)
                frame_max = scores.max(axis=0)
                gun_score = float(frame_max[target_idx].max())
                top = names[int(frame_max.argmax())]
                level = float(np.sqrt(np.mean(buffer ** 2)))
                on_status(
                    f"Listening. Top sound: {top}; possible gunshot score: {gun_score:.2f}; "
                    f"audio level: {level:.3f}.{aws_status}"
                )

                hits = hits + 1 if gun_score >= THRESHOLD else 0
                now = time.time()
                if hits >= HITS_REQUIRED and now - last_alert > COOLDOWN_SECONDS:
                    last_alert = now
                    hits = 0
                    message = {
                        "room": ROOM,
                        "type": "gunshot",
                        "confidence": round(gun_score, 2),
                        "device": DEVICE_ID,
                        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    message["label"] = "Possible gunshot-like sound"
                    if publish:
                        try:
                            publish(message)
                            message["published"] = True
                        except Exception as exc:
                            message["published"] = False
                            on_status(f"Possible sound detection; AWS publish failed: {exc}")
                    else:
                        message["published"] = False
                    on_detection(message)
    finally:
        if conn:
            conn.disconnect().result()


def main():
    def show_status(message):
        print(f"\r{message:<120}", end="", flush=True)

    try:
        run_detection(on_status=show_status)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()