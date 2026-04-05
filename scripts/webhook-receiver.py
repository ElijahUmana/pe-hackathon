#!/usr/bin/env python3
"""
Incident Response Webhook Receiver
Receives alerts from Alertmanager and logs them with full context.
Uses only Python stdlib - no external dependencies required.
"""
import datetime
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

ALERT_LOG = "/var/log/alerts.log"
EVIDENCE_DIR = "/root/pe-hackathon/evidence"

os.makedirs(EVIDENCE_DIR, exist_ok=True)

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
                print(msg % (timestamp, status.upper(), alert_name, severity, instance))

        alert_count = len(data.get("alerts", [])) if isinstance(data, dict) else 0
        print("[%s] Logged %d alert(s) to %s" % (timestamp, alert_count, ALERT_LOG))

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
        print("[%s] %s" % (timestamp, format % args))

if __name__ == "__main__":
    port = 9094
    server = HTTPServer(("0.0.0.0", port), AlertHandler)
    print("Webhook receiver listening on port %d" % port)
    print("Alert log: %s" % ALERT_LOG)
    print("Evidence dir: %s" % EVIDENCE_DIR)
    server.serve_forever()
