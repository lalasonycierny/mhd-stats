#!/usr/bin/env python3
"""Štatistiky z databázy, ktorú plní collector.py.

Príklady:
  python stats.py summary
  python stats.py delay-by-route --days 30
  python stats.py delay-by-hour --csv > hodiny.csv
"""
import argparse
import csv
import os
import sqlite3
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# 'načas' = meškanie od -60 s do +60 s; 'do 5 min' = 61–300 s; 'nad 5 min' = viac
ON_TIME = "SUM(delay_s BETWEEN -60 AND 60)"
UP_TO_5 = "SUM(delay_s BETWEEN 61 AND 300)"
OVER_5 = "SUM(delay_s > 300)"

QUERIES = {
    "summary": """
        SELECT COUNT(*) AS zaznamov,
               COUNT(DISTINCT vehicle_id) AS vozidiel,
               COUNT(DISTINCT route) AS liniek,
               datetime(MIN(ts), 'unixepoch') AS od_utc,
               datetime(MAX(ts), 'unixepoch') AS do_utc,
               ROUND(100.0 * COUNT(delay_s) / COUNT(*), 1) AS pct_so_znamym_meskanim
        FROM p""",
    "delay-by-route": f"""
        SELECT route, COUNT(*) AS vzorky,
               ROUND(AVG(delay_s)/60.0, 2) AS priem_meskanie_min,
               ROUND(100.0*{ON_TIME}/COUNT(*), 1) AS pct_nacas,
               ROUND(100.0*{UP_TO_5}/COUNT(*), 1) AS pct_do_5min,
               ROUND(100.0*{OVER_5}/COUNT(*), 1) AS pct_nad_5min
        FROM p WHERE delay_s IS NOT NULL
        GROUP BY route HAVING vzorky >= {{MIN}}
        ORDER BY priem_meskanie_min DESC LIMIT 40""",
    "delay-by-hour": """
        SELECT local_hour(ts) AS hodina,
               ROUND(AVG(delay_s)/60.0, 2) AS priem_meskanie_min,
               COUNT(*) AS vzorky
        FROM p WHERE delay_s IS NOT NULL
        GROUP BY hodina ORDER BY hodina""",
    "delay-by-weekday": """
        SELECT local_weekday(ts) AS den,
               ROUND(AVG(delay_s)/60.0, 2) AS priem_meskanie_min,
               COUNT(*) AS vzorky
        FROM p WHERE delay_s IS NOT NULL
        GROUP BY den ORDER BY den""",
    "active-vehicles-by-hour": """
        SELECT hodina, ROUND(AVG(n), 1) AS priem_aktivnych_vozidiel, MAX(n) AS max FROM (
            SELECT ts, local_hour(ts) AS hodina, COUNT(DISTINCT vehicle_id) AS n
            FROM p GROUP BY ts)
        GROUP BY hodina ORDER BY hodina""",
    "busiest-routes": """
        SELECT route, ROUND(AVG(n), 1) AS priem_vozidiel, MAX(n) AS max_vozidiel FROM (
            SELECT ts, route, COUNT(DISTINCT vehicle_id) AS n
            FROM p WHERE route IS NOT NULL GROUP BY ts, route)
        GROUP BY route ORDER BY priem_vozidiel DESC LIMIT 25""",
    # Hrubá mriežka ~110 m. Zahŕňa aj konečné a zastávky (tam vozidlá stoja prirodzene),
    # preto výsledok čítajte spolu s mapou.
    "bottlenecks": """
        SELECT ROUND(lat, 3) AS lat, ROUND(lon, 3) AS lon,
               COUNT(*) AS stojace_vzorky, COUNT(DISTINCT route) AS linky
        FROM p WHERE speed_kmh IS NOT NULL AND speed_kmh < 2
        GROUP BY 1, 2 HAVING stojace_vzorky >= {MIN}
        ORDER BY stojace_vzorky DESC LIMIT 40""",
}

WEEKDAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", choices=sorted(QUERIES))
    ap.add_argument("--db", default="mhd.sqlite")
    ap.add_argument("--days", type=int, default=0, help="len posledných N dní (0 = všetko)")
    ap.add_argument("--min-samples", type=int, default=100,
                    help="min. počet vzoriek pre zaradenie linky/miesta do rebríčka (default 100)")
    ap.add_argument("--tz", default="Europe/Bratislava")
    ap.add_argument("--csv", action="store_true", help="výstup vo formáte CSV")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"Databáza {args.db} neexistuje. Najprv spustite collector.py.")
    tz = ZoneInfo(args.tz)
    conn = sqlite3.connect(args.db)
    conn.create_function("local_hour", 1,
                         lambda t: f"{datetime.fromtimestamp(t, tz).hour:02d}", deterministic=True)
    conn.create_function("local_weekday", 1,
                         lambda t: f"{datetime.fromtimestamp(t, tz).weekday()} {WEEKDAYS[datetime.fromtimestamp(t, tz).weekday()]}",
                         deterministic=True)

    since = int(time.time()) - args.days * 86400 if args.days else 0
    # p = dáta v zvolenom období bez zjavných chýb meškania (mimo -30 min .. +2 h)
    conn.execute(f"""CREATE TEMP VIEW p AS SELECT * FROM positions
                     WHERE ts >= {int(since)}
                       AND (delay_s IS NULL OR delay_s BETWEEN -1800 AND 7200)""")

    try:
        cur = conn.execute(QUERIES[args.report].replace("{MIN}", str(int(args.min_samples))))
    except sqlite3.OperationalError as exc:
        sys.exit(f"Chyba databázy: {exc}\n(Existuje {args.db} a bežal už collector.py?)")

    cols = [c[0] for c in cur.description]
    w = csv.writer(sys.stdout, delimiter="," if args.csv else "\t")
    w.writerow(cols)
    for row in cur:
        w.writerow(["" if v is None else v for v in row])


if __name__ == "__main__":
    main()
