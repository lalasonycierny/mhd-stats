#!/usr/bin/env python3
"""
mhd-stats collector: v pravidelnom intervale ukladá polohy a meškania vozidiel MHD do SQLite.

Zdroje dát:
  gtfs-rt  GTFS-realtime (protobuf), napr. oficiálny open data feed
  json     ľubovoľné JSON API; polia sa mapujú cez mapping súbor (pozri mapping.example.json)

Príklady:
  python collector.py --format gtfs-rt --vehicles-url URL --trips-url URL
  python collector.py --format json --vehicles-url URL --mapping mapping.json
  python collector.py --format json --vehicles-url URL --mapping mapping.json --once
"""
import argparse
import json
import logging
import signal
import sqlite3
import sys
import time

import requests

log = logging.getLogger("mhd")

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    ts           INTEGER NOT NULL,   -- unix čas zberu (UTC)
    src_ts       INTEGER,            -- čas z feedu (ak ho feed poskytuje)
    vehicle_id   TEXT,
    route        TEXT,
    trip_id      TEXT,
    vehicle_type TEXT,               -- bus / trolleybus / tram (ak je známy)
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    speed_kmh    REAL,
    delay_s      INTEGER             -- meškanie v sekundách (záporné = predstih)
);
CREATE INDEX IF NOT EXISTS idx_pos_ts ON positions(ts);
CREATE INDEX IF NOT EXISTS idx_pos_route_ts ON positions(route, ts);
CREATE INDEX IF NOT EXISTS idx_pos_vehicle_ts ON positions(vehicle_id, ts);
"""

COLUMNS = ("ts", "src_ts", "vehicle_id", "route", "trip_id", "vehicle_type",
           "lat", "lon", "speed_kmh", "delay_s")

running = True


def stop(*_):
    global running
    running = False


# ---------- pomocné funkcie ----------
def to_float(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_int(v):
    f = to_float(v)
    return None if f is None else int(round(f))


def to_str(v):
    return None if v is None or v == "" else str(v)


def dig(obj, path):
    """Prejde bodkovú cestu ('a.b.0.c') v dict/list štruktúre; pri chybe vráti None."""
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if obj is None:
            return None
    return obj


def fetch(url, headers, timeout=20):
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content


# ---------- GTFS-realtime ----------
def parse_gtfs_rt(vehicles_raw, trips_raw):
    try:
        from google.transit import gtfs_realtime_pb2 as pb
    except ImportError:
        sys.exit("Chýba balík gtfs-realtime-bindings: pip install -r requirements.txt")

    delays = {}  # trip_id -> meškanie (s)
    if trips_raw:
        feed = pb.FeedMessage()
        feed.ParseFromString(trips_raw)
        for e in feed.entity:
            if not e.HasField("trip_update"):
                continue
            tu = e.trip_update
            d = None
            if tu.HasField("delay"):
                d = tu.delay
            elif tu.stop_time_update:
                u = tu.stop_time_update[0]
                if u.HasField("arrival") and u.arrival.HasField("delay"):
                    d = u.arrival.delay
                elif u.HasField("departure") and u.departure.HasField("delay"):
                    d = u.departure.delay
            if d is not None and tu.trip.trip_id:
                delays[tu.trip.trip_id] = d

    feed = pb.FeedMessage()
    feed.ParseFromString(vehicles_raw)
    rows = []
    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        if not v.HasField("position"):
            continue
        trip_id = v.trip.trip_id or None
        rows.append({
            "vehicle_id": v.vehicle.id or e.id,
            "route": v.trip.route_id or None,
            "trip_id": trip_id,
            "vehicle_type": None,
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "speed_kmh": v.position.speed * 3.6 if v.position.HasField("speed") else None,
            "delay_s": delays.get(trip_id),
            "src_ts": v.timestamp if v.HasField("timestamp") else None,
        })
    return rows


# ---------- JSON s mappingom ----------
def parse_json(raw, mapping):
    data = json.loads(raw)
    items = dig(data, mapping.get("list_path", ""))
    if isinstance(items, dict):  # {"id1": {...}, "id2": {...}}
        items = list(items.values())
    fields = mapping["fields"]
    delay_mult = {"s": 1, "min": 60}[mapping.get("delay_unit", "s")]
    speed_mult = {"kmh": 1.0, "ms": 3.6}[mapping.get("speed_unit", "kmh")]
    rows = []
    for it in items or []:
        raw_row = {k: dig(it, p) if p else None for k, p in fields.items()}
        delay = to_float(raw_row.get("delay_s"))
        speed = to_float(raw_row.get("speed_kmh"))
        rows.append({
            "vehicle_id": to_str(raw_row.get("vehicle_id")),
            "route": to_str(raw_row.get("route")),
            "trip_id": to_str(raw_row.get("trip_id")),
            "vehicle_type": to_str(raw_row.get("vehicle_type")),
            "lat": to_float(raw_row.get("lat")),
            "lon": to_float(raw_row.get("lon")),
            "speed_kmh": None if speed is None else speed * speed_mult,
            "delay_s": None if delay is None else int(round(delay * delay_mult)),
            "src_ts": to_int(raw_row.get("src_ts")),
        })
    return rows


# ---------- ukladanie ----------
def valid(r):
    lat, lon = r.get("lat"), r.get("lon")
    return (lat is not None and lon is not None
            and -90 <= lat <= 90 and -180 <= lon <= 180
            and not (lat == 0 and lon == 0))


def save(conn, ts, rows, last_seen):
    """Uloží riadky; preskočí vozidlá, ktorých src_ts sa od minule nezmenil."""
    out = []
    for r in rows:
        if not valid(r):
            continue
        vid, src = r.get("vehicle_id"), r.get("src_ts")
        if vid is not None and src is not None:
            if last_seen.get(vid) == src:
                continue
            last_seen[vid] = src
        out.append((ts, src, vid, r.get("route"), r.get("trip_id"),
                    r.get("vehicle_type"), r["lat"], r["lon"],
                    r.get("speed_kmh"), r.get("delay_s")))
    conn.executemany(f"INSERT INTO positions ({','.join(COLUMNS)}) VALUES ({','.join('?'*len(COLUMNS))})", out)
    conn.commit()
    return len(out), len(rows)


def purge(conn, days):
    cutoff = int(time.time()) - days * 86400
    n = conn.execute("DELETE FROM positions WHERE ts < ?", (cutoff,)).rowcount
    conn.commit()
    if n:
        log.info("zmazaných %d starých záznamov (> %d dní)", n, days)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--format", choices=["gtfs-rt", "json"], required=True)
    ap.add_argument("--vehicles-url", required=True)
    ap.add_argument("--trips-url", help="GTFS-RT trip updates (pre meškania)")
    ap.add_argument("--mapping", help="JSON mapping súbor (pre --format json)")
    ap.add_argument("--db", default="mhd.sqlite")
    ap.add_argument("--interval", type=int, default=60, help="sekundy medzi zbermi (default 60)")
    ap.add_argument("--header", action="append", default=[], metavar="'Meno: hodnota'",
                    help="extra HTTP hlavička (možno opakovať), napr. API kľúč")
    ap.add_argument("--retention-days", type=int, default=0,
                    help="mazať surové dáta staršie než N dní (0 = nemazať)")
    ap.add_argument("--once", action="store_true", help="urobiť jeden zber a skončiť (test)")
    ap.add_argument("--user-agent", default="mhd-stats/0.2 (osobný výskumný projekt)")
    args = ap.parse_args()

    if args.interval < 10:
        ap.error("--interval musí byť aspoň 10 s (šetrite zdroj dát)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    mapping = None
    if args.format == "json":
        if not args.mapping:
            ap.error("--format json vyžaduje --mapping")
        with open(args.mapping, encoding="utf-8") as f:
            mapping = json.load(f)
        if "fields" not in mapping:
            ap.error("mapping súbor musí obsahovať kľúč 'fields'")

    headers = {"User-Agent": args.user_agent}
    for h in args.header:
        if ":" not in h:
            ap.error(f"neplatná hlavička: {h!r} (očakávam 'Meno: hodnota')")
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    last_seen = {}
    last_purge = 0
    fails = 0
    while running:
        started = time.time()
        try:
            vraw = fetch(args.vehicles_url, headers)
            if args.format == "gtfs-rt":
                traw = None
                if args.trips_url:
                    try:
                        traw = fetch(args.trips_url, headers)
                    except requests.RequestException as exc:
                        log.warning("trip updates nedostupné (ukladám bez meškaní): %s", exc)
                rows = parse_gtfs_rt(vraw, traw)
            else:
                rows = parse_json(vraw, mapping)
            saved, total = save(conn, int(started), rows, last_seen)
            fails = 0
            log.info("uložených %d z %d vozidiel", saved, total)
        except Exception as exc:  # sieť padá, feed občas vráti nezmysel – nepadať
            fails += 1
            log.warning("zber zlyhal (%dx v rade): %s", fails, exc)

        if args.retention_days and started - last_purge > 86400:
            purge(conn, args.retention_days)
            last_purge = started

        if args.once:
            break
        while running and time.time() - started < args.interval:
            time.sleep(0.5)

    conn.close()
    log.info("koniec")


if __name__ == "__main__":
    main()
