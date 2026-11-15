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
import os
import queue
import time
from datetime import datetime

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

    for f in (CERT_FILE, KEY_FILE, CA_FILE):
        if not os.path.exists(f):
            raise SystemExit(f"Missing file: {f} - put this script in the connection kit folder "
                             f"and check the file names at the top of the script.")

    print(f"Connecting to AWS IoT Core as '{CLIENT_ID}'...")
    conn = mqtt_connection_builder.mtls_from_path(
        endpoint=IOT_ENDPOINT,
        cert_filepath=CERT_FILE,
        pri_key_filepath=KEY_FILE,
        ca_filepath=CA_FILE,
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


def main():
    model, names, target_idx = load_model()
    conn, publish = connect_iot()

    audio_q = queue.Queue()
    window_len = int(SAMPLE_RATE * WINDOW_SECONDS)
    hop_len = int(SAMPLE_RATE * HOP_SECONDS)
    buffer = np.zeros(window_len, dtype=np.float32)
    pending = np.zeros(0, dtype=np.float32)

    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        audio_q.put(indata[:, 0].copy())

    hits = 0
    last_alert = 0.0

    print(f"Listening in '{ROOM}'... (Ctrl+C to stop)")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=hop_len, callback=callback):
            while True:
                pending = np.concatenate([pending, audio_q.get()])
                if len(pending) < hop_len:
                    continue
                chunk, pending = pending[:hop_len], pending[hop_len:]
                buffer = np.concatenate([buffer[hop_len:], chunk])

                scores = model(buffer)[0].numpy()     # (frames, 521)
                frame_max = scores.max(axis=0)
                gun_score = float(frame_max[target_idx].max())
                top = names[int(frame_max.argmax())]
                level = float(np.sqrt(np.mean(buffer ** 2)))
                print(f"\rtop: {top:<28} gunshot: {gun_score:.2f}  level: {level:.3f}   ", end="")

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
                    print(f"\n\n*** GUNSHOT DETECTED *** {message}")
                    try:
                        publish(message)
                    except Exception as e:
                        print("  -> publish FAILED:", e)
                    print()
    finally:
        conn.disconnect().result()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")