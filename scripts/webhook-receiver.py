#!/usr/bin/env python3
"""
Incident Response Webhook Receiver
Receives alerts from Alertmanager and logs them with full context.
Uses only Python stdlib - no external dependencies required.
"""
import datetime
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

ALERT_LOG = os.environ.get("ALERT_LOG", "/var/log/alerts.log")
EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", "/app/evidence")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

os.makedirs(EVIDENCE_DIR, exist_ok=True)


GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")

SEVERITY_CONFIG = {
    "critical": {"color": 0xFF0000, "emoji": "\U0001f6a8"},
    "warning": {"color": 0xFFA500, "emoji": "\u26a0\ufe0f"},
    "info": {"color": 0x3498DB, "emoji": "\u2139\ufe0f"},
}


def forward_to_discord(data):
    """Forward alert payload to Discord as rich embeds with Grafana links."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        alerts = data.get("alerts", []) if isinstance(data, dict) else []
        for alert in alerts:
            name = alert.get("labels", {}).get("alertname", "Unknown")
            status = alert.get("status", "unknown").upper()
            severity = alert.get("labels", {}).get("severity", "unknown")
            instance = alert.get("labels", {}).get("instance", "unknown")
            summary = alert.get("annotations", {}).get("summary", "")
            desc = alert.get("annotations", {}).get("description", "")
            starts_at = alert.get("startsAt", "")
            ends_at = alert.get("endsAt", "")

            sev_cfg = SEVERITY_CONFIG.get(severity, SEVERITY_CONFIG["warning"])
            color = 0x00FF00 if status == "RESOLVED" else sev_cfg["color"]
            emoji = "\u2705" if status == "RESOLVED" else sev_cfg["emoji"]

            title = "%s %s [%s]" % (emoji, name, status)

            fields = [
                {"name": "Severity", "value": severity, "inline": True},
                {"name": "Instance", "value": instance, "inline": True},
                {"name": "Status", "value": status, "inline": True},
            ]
            if starts_at:
                fields.append({"name": "Started", "value": starts_at[:19], "inline": True})
            if status == "RESOLVED" and ends_at:
                fields.append({"name": "Resolved", "value": ends_at[:19], "inline": True})
            fields.append({
                "name": "Dashboard",
                "value": "[Open Grafana](%s)" % GRAFANA_URL,
                "inline": False,
            })

            body = summary if summary else desc

            payload = json.dumps({
                "embeds": [{
                    "title": title,
                    "description": body,
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "PE Hackathon Alert System"},
                }],
            }).encode()

            result = subprocess.run(
                [
                    "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "-X", "POST", DISCORD_WEBHOOK_URL,
                    "-H", "Content-Type: application/json",
                    "-d", payload.decode(),
                ],
                capture_output=True, text=True, timeout=10,
            )
            print("Discord response for %s: HTTP %s" % (name, result.stdout.strip()), flush=True)
            if result.stderr:
                print("Discord curl stderr: %s" % result.stderr.strip(), flush=True)
    except Exception as e:
        print("Discord forward failed: %s" % e, flush=True)


class AlertHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"raw": body.decode("utf-8", errors="replace")}

        log_entry = {"received_at": timestamp, "alerts": data}
        with open(ALERT_LOG, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        if isinstance(data, dict) and "alerts" in data:
            for alert in data["alerts"]:
                alert_name = alert.get("labels", {}).get("alertname", "unknown")
                severity = alert.get("labels", {}).get("severity", "unknown")
                status = alert.get("status", "unknown")
                ts_safe = timestamp.replace(":", "-")
                evidence_file = os.path.join(
                    EVIDENCE_DIR,
                    "alert_%s_%s_%s.json" % (alert_name, status, ts_safe)
                )
                with open(evidence_file, "w") as f:
                    json.dump({
                        "received_at": timestamp,
                        "alert_name": alert_name,
                        "severity": severity,
                        "status": status,
                        "full_alert": alert
                    }, f, indent=2)
                instance = alert.get("labels", {}).get("instance", "unknown")
                msg = "[%s] ALERT %s: %s (severity=%s) on %s"
                print(msg % (timestamp, status.upper(), alert_name, severity, instance), flush=True)

        alert_count = len(data.get("alerts", [])) if isinstance(data, dict) else 0
        print("[%s] Logged %d alert(s) to %s" % (timestamp, alert_count, ALERT_LOG), flush=True)

        forward_to_discord(data)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "received": timestamp}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        alerts = []
        if os.path.exists(ALERT_LOG):
            with open(ALERT_LOG, "r") as f:
                for line in f:
                    try:
                        alerts.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        self.wfile.write(json.dumps({
            "status": "running",
            "total_alerts_received": len(alerts),
            "log_file": ALERT_LOG,
            "evidence_dir": EVIDENCE_DIR
        }, indent=2).encode())

    def log_message(self, format, *args):
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        print("[%s] %s" % (timestamp, format % args), flush=True)

if __name__ == "__main__":
    port = 9094
    server = HTTPServer(("0.0.0.0", port), AlertHandler)
    print("Webhook receiver listening on port %d" % port, flush=True)
    print("Alert log: %s" % ALERT_LOG, flush=True)
    print("Evidence dir: %s" % EVIDENCE_DIR, flush=True)
    print("Discord webhook URL configured: %s" % bool(DISCORD_WEBHOOK_URL), flush=True)
    server.serve_forever()
