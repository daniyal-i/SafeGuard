# SafeGuard

### Helping people get help sooner when seconds matter.

SafeGuard is a safety-monitoring project exploring how connected sensors and
software could identify signs of danger and help notify the right people sooner.
In an emergency, people may be frightened, unable to call, or unsure what to do.
Our goal is to support faster awareness and response in places such as schools
and other public spaces.

> **Prototype status:** SafeGuard is a work in progress, not an emergency
> response service. The current device prototype analyzes audio for gunshot-like
> sounds and can publish detections to AWS IoT Core when configured. The web
> dashboard currently shows simulated data and is not connected to the device,
> AWS, or first responders.

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
| Audio detector | Uses a microphone and YAMNet to look for gunshot-like sounds. |
| AWS IoT publishing | `detect.py` can publish a detection to the `sentinel/alerts` topic when valid local credentials and AWS IoT permissions are configured. |
| Alert dashboard | Static demo page with simulated alerts, filters, charts, and an animated demo activity graph. |
| Dashboard data connection | Not implemented yet; the dashboard does not receive device or AWS events. |
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

Open [`dashboard/index.html`](dashboard/index.html) in a browser, or host the
`dashboard/` folder as a static site. The **Run simulation** button adds a
sample alert locally; the animated graph also uses generated values. Neither
feature sends data to AWS.

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
