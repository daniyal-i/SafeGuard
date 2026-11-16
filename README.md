# SafeGuard

![Detector syntax check](https://github.com/daniyal-i/SafeGuard/actions/workflows/detector-check.yml/badge.svg?branch=main)

### Helping people get help sooner when seconds matter.

SafeGuard is a safety-monitoring project exploring how connected sensors and
software could identify signs of danger and help notify the right people sooner.
In an emergency, people may be frightened, unable to call, or unsure what to do.
Our goal is to support faster awareness and response in places such as schools
and other public spaces.

> **Prototype status:** SafeGuard is a work in progress, not an emergency
> response service. The audio prototype analyzes possible gunshot-like sounds
> and can publish detection metadata to AWS IoT Core when configured. The local
> dashboard can control audio and image detection on the same computer, but it
> is not connected to a remote device or first responders. Dashboard demo alerts
> and activity graph values are simulated.

## What we're building

- **Detect:** Explore sensor-based ways to recognize potential threats.
- **Alert:** Share a possible detection, its location, and its confidence so a
  person can assess it.
- **Respond sooner:** Work toward getting useful information to the appropriate
  responders more quickly.

These are project goals, not guarantees. Automated detections can be wrong and
must be verified by a person.

## Current prototype

| Component | Current status |
| --- | --- |
| Audio detector | Uses a microphone and YAMNet to look for gunshot-like sounds; the local dashboard can start and stop it. |
| AWS IoT publishing | `detect.py` can publish a detection to the `sentinel/alerts` topic when valid local credentials and AWS IoT permissions are configured. |
| Alert dashboard | Static demo page with simulated alerts, filters, charts, and an activity graph that updates on each simulation. |
| Detection tab | Local dashboard controls the YAMNet microphone detector and sends camera snapshots to the YOLO image detector. Results are possible detections and require human review. |
| Dashboard data connection | The local dashboard bridge runs only on `127.0.0.1`; it is not a remote device/AWS dashboard connection. |
| First-responder notification | Not implemented or configured by this repository. |

## Project layout

```text
.
├── dashboard/
│   ├── index.html       # Static dashboard demo
│   └── SafeGuardLogo.png
└── connect_device_package/
    ├── detect.py        # Audio detection and optional AWS IoT publishing
    ├── requirements.txt
    └── start.sh         # AWS IoT SDK connectivity sample
```

## Try the dashboard

Install the packages and start the local dashboard bridge from the repository
root:

```bash
python3 -m pip install -r connect_device_package/requirements.txt
python3 connect_device_package/web_service.py
```

Then open `http://127.0.0.1:8765` in a browser. Keep the bridge running while
using the **Detection** tab. The browser buttons start and stop continuous
microphone detection, turn the camera on/off, and capture a camera frame for
image detection. You can also select a JPEG, PNG, or WebP photo up to 10 MB and
analyze it. The audio model and image model may download their weights the
first time and require network access. Allow microphone access to the terminal
or Python app in macOS privacy settings if prompted.

The local service binds only to `127.0.0.1`; camera snapshots are sent to that
local service and are not uploaded to an image cloud service. The audio detector
can publish detection metadata to AWS IoT if its credentials are configured;
raw audio is not sent by this dashboard. If the dashboard stops polling, the
audio detector stops automatically. Model results can be wrong or miss a real
threat; treat them as possible detections that need human review.

The **Run simulation** button on the Alert Dashboard still adds a local sample
alert and updates the activity graph. Hover over a plotted point to view that
simulation's sound, score, and time. Simulations do not send data to AWS.

## Run the audio detector

The detector requires a working microphone, Python dependencies, and an AWS IoT
device connection kit. AWS credentials and certificates are not included in
this repository.

1. Install Python and the system requirements needed by the audio packages.
2. Obtain an AWS IoT device certificate, its private key, and the appropriate
   CA certificate through your AWS administrator or device provisioning
   process. Keep these files private and never commit them.
3. In `connect_device_package/detect.py`, configure the IoT endpoint, client ID,
   topic, and certificate file names for your device. The device certificate
   must have permission to publish to the configured topic.
4. From the device package directory, install dependencies and start the
   detector:

   ```bash
   cd connect_device_package
   python3 -m pip install -r requirements.txt
   python3 detect.py
   ```

The script listens for audio locally and publishes possible detections to AWS
IoT Core. Any downstream routing (for example, an IoT Rule, database, or
notification service) must be configured separately in AWS. The dashboard
does not subscribe to the topic.

### Check detector status

The badge at the top reports whether the detector script passes a Python syntax
check in GitHub Actions. A green badge means the code parses; it does not mean
the microphone, AWS connection, or live alert delivery is working.

The detector reports its status in the terminal where it is running:

- **Connected:** `Connected to AWS IoT Core.`
- **Listening:** `Listening in 'Main Hallway'...`
- **Alert published:** `alert published to sentinel/alerts`
- **Connection or publish problem:** Look for an error message, such as
  `publish FAILED`, or a missing certificate/key message at startup.

No alert message simply means no detection has crossed the configured threshold
yet; it does not by itself mean the detector has stopped. These messages only
show the device script's local status. They are not a remote health check, and
the dashboard cannot display them until a device-to-dashboard connection is
implemented.

## Safety and privacy

- SafeGuard is a prototype and may miss real events or produce false alerts.
- It does not replace emergency services, human judgment, or established
  safety procedures.
- The current detector processes audio on the device and publishes alert
  metadata when configured; review the code and your deployment settings before
  use.
- Protect device credentials. Never put private keys, certificates, or AWS
  secrets in the dashboard or a public repository.
- **If there is immediate danger, call 911 or your local emergency number.**

## What's next

- Connect the dashboard to a secure backend or AWS-backed data source.
- Clearly distinguish live connection status from simulated demo mode.
- Evaluate detection performance and false alarms in appropriate, controlled
  settings.
- Explore additional sensor inputs and carefully designed alert workflows.

---

SafeGuard is a safety-monitoring prototype intended to support people—not
replace them.
