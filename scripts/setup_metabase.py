#!/usr/bin/env python3
"""Provision Metabase through its API: admin user, the Postgres warehouse as a data source, six questions, one dashboard.

  python3 scripts/setup_metabase.py            # Metabase at http://localhost:3000 (profile `bi`)

Idempotent: if the dashboard exists it is left alone. Uses only the standard library.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

MB = "http://localhost:3000"
USER = {"email": os.getenv("MB_EMAIL", "lab@example.com"),
        "password": os.getenv("MB_PASSWORD", "Day9-lab-pass!"),
        "first_name": "Lab", "last_name": "User"}


def call(method, path, body=None, token=None):
    req = urllib.request.Request(MB + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"X-Metabase-Session": token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:400]}")


def wait_ready():
    for _ in range(120):
        try:
            if call("GET", "/api/health").get("status") == "ok":
                return
        except SystemExit:
            pass
        except OSError:
            pass
        time.sleep(3)
    sys.exit("Metabase did not become healthy in 6 minutes")


IMAGE_COL = {"column_settings": {'["name","thumb_url"]': {"view_as": "image"}}}
QUESTIONS = [
    ("Frame funnel: why frames are dropped (kept frames are in the trips table)", "bar",
     "select drive_id, dropped_black as black, dropped_blurry as blurry, dropped_near_dup as near_duplicate, dropped_out_of_sync as out_of_sync from marts.mart_frame_funnel"),
    ("Telemetry quarantine by reason", "bar",
     "select drive_id, rows_duplicate as duplicate, rows_speed_missing as speed_missing, rows_speed_out_of_range as speed_out_of_range from marts.mart_telemetry_quality"),
    ("Split balance (trips are never shared)", "table", "select * from marts.mart_split_balance order by split"),
    ("Speed coverage of the training set", "bar", "select speed_kmh_bucket, drive_id, frames from marts.mart_speed_coverage order by 1"),
    ("Trips: frames kept and split", "table", "select * from marts.mart_trip_summary order by drive_id, trip_id"),
    ("Frame gallery (test split)", "table", "select frame_id, split, speed_kmh, thumb_url from marts.mart_frame_gallery where split = 'test' order by frame_id limit 12"),
]


def main():
    wait_ready()
    props = call("GET", "/api/session/properties")
    if props.get("has-user-setup"):
        token = call("POST", "/api/session", {"username": USER["email"], "password": USER["password"]})["id"]
    else:
        token = call("POST", "/api/setup", {
            "token": props["setup-token"], "user": USER,
            "prefs": {"site_name": "Day 9 lab", "site_locale": "en", "allow_tracking": False}})["id"]
    dbs = call("GET", "/api/database", token=token)
    dbs = dbs["data"] if isinstance(dbs, dict) else dbs
    wh = next((d for d in dbs if d["engine"] == "postgres"), None)
    if wh is None:      # register the Postgres warehouse (the container-network name `postgres`, not localhost)
        wh = call("POST", "/api/database", {"engine": "postgres", "name": "warehouse", "is_full_sync": True, "is_on_demand": False,
                                            "details": {"host": "postgres", "port": 5432, "dbname": "warehouse", "user": "lab",
                                                        "password": "lab", "ssl": False}}, token=token)
    call("POST", f"/api/database/{wh['id']}/sync_schema", token=token)
    existing = {d["name"]: d for d in call("GET", "/api/dashboard", token=token)}
    if "Day 9: video data pipeline" in existing:
        print("dashboard already exists:", f"{MB}/dashboard/{existing['Day 9: video data pipeline']['id']}")
        return
    card_ids = []
    for name, display, sql in QUESTIONS:
        c = call("POST", "/api/card", {"name": name, "display": display, "visualization_settings": IMAGE_COL if "thumb_url" in sql else {},
                                       "dataset_query": {"type": "native", "database": wh["id"], "native": {"query": sql}}}, token=token)
        card_ids.append(c["id"])
    dash = call("POST", "/api/dashboard", {"name": "Day 9: video data pipeline"}, token=token)
    cards = []
    for i, cid in enumerate(card_ids):
        cards.append({"id": -(i + 1), "card_id": cid, "row": (i // 2) * 6, "col": (i % 2) * 12 if i < len(card_ids) - 1 else 0, "size_x": 12 if i < len(card_ids) - 1 else 24, "size_y": 6 if i < len(card_ids) - 1 else 9,
                      "visualization_settings": {}, "parameter_mappings": []})
    call("PUT", f"/api/dashboard/{dash['id']}", {"dashcards": cards}, token=token)
    print("dashboard:", f"{MB}/dashboard/{dash['id']}", "| login", USER["email"], "/", USER["password"])


if __name__ == "__main__":
    main()
