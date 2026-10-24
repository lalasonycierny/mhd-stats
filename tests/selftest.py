#!/usr/bin/env python3
"""Samotest: lokálny falošný server -> collector --once -> stats. Nepotrebuje internet."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAKE = {"vehicles": [
    {"id": "1001", "line": "50", "type": "tram", "lat": 48.15, "lon": 17.11,
     "speed": 0, "delay": 2.5, "timestamp": 1700000000},
    {"id": "1002", "line": "9", "type": "tram", "lat": "48,16", "lon": "17,12",
     "speed": "25.5", "delay": "-0.5", "timestamp": 1700000001},
    {"id": "bad", "line": "1", "lat": None, "lon": None},          # bez polohy -> preskočí sa
    {"id": "zero", "line": "1", "lat": 0, "lon": 0},                # 0,0 -> preskočí sa
]}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(FAKE).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def run(*cmd):
    return subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)


def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.sqlite")
        r = run("collector.py", "--format", "json", "--vehicles-url", url,
                "--mapping", "mapping.example.json", "--db", db, "--once")
        assert r.returncode == 0, r.stderr
        assert "uložených 2 z 4" in r.stderr, r.stderr

        out = run("stats.py", "summary", "--db", db)
        assert out.returncode == 0, out.stderr
        lines = out.stdout.strip().splitlines()
        assert lines[1].split("\t")[:3] == ["2", "2", "2"], out.stdout

        for rep in ("delay-by-route", "delay-by-hour", "delay-by-weekday",
                    "active-vehicles-by-hour", "busiest-routes", "bottlenecks"):
            o = run("stats.py", rep, "--db", db, "--csv")
            assert o.returncode == 0, (rep, o.stderr)

        d = run("stats.py", "delay-by-route", "--db", db, "--min-samples", "1")
        assert "50" in d.stdout and "2.5" in d.stdout, d.stdout
    print("OK: všetky testy prešli")


if __name__ == "__main__":
    main()
