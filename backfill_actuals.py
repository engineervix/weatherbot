#!/usr/bin/env python3
"""One-time backfill of actual_temp from Visual Crossing into existing market files.

Reads every market file in data/markets/, fetches the actual high from VC,
and writes back the file with actual_temp populated. Idempotent — skips markets
that already have actual_temp. This unblocks the per-city MAE gate on the first
post-restart cycle.
"""
import json
import glob
import os
import re
import requests
import sys
from datetime import datetime, timezone

os.chdir("/home/juan/weatherbet")
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

VC_KEY = os.environ["VC_KEY"]

# Pull LOCATIONS via regex
src = open("weatherbet.py").read()
m = re.search(r"^LOCATIONS\s*=\s*(\{.*?\n\})", src, re.MULTILINE | re.DOTALL)
LOCATIONS = eval(m.group(1))

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
files = sorted(glob.glob("data/markets/*.json"))
updated = 0
skipped_have = 0
skipped_future = 0
errors = 0
for f in files:
    d = json.load(open(f))
    if d.get("actual_temp") is not None:
        skipped_have += 1
        continue
    date = d.get("date")
    city = d.get("city")
    if not date or not city or date >= today:
        skipped_future += 1
        continue
    loc = LOCATIONS[city]
    unit = loc["unit"]
    vc_unit = "us" if unit == "F" else "metric"
    station = loc["station"]
    url = (
        f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
        f"/{station}/{date}/{date}?unitGroup={vc_unit}&key={VC_KEY}&include=days&elements=tempmax"
    )
    try:
        r = requests.get(url, timeout=(5, 8))
        data = r.json()
        days = data.get("days", [])
        if days and days[0].get("tempmax") is not None:
            d["actual_temp"] = round(float(days[0]["tempmax"]), 1)
            with open(f, "w", encoding="utf-8") as out:
                json.dump(d, out, indent=2, ensure_ascii=False)
            updated += 1
        else:
            errors += 1
    except Exception as e:
        print(f"  ERR {city} {date}: {e}")
        errors += 1

print(f"Backfill complete:")
print(f"  Updated:     {updated}")
print(f"  Had already: {skipped_have}")
print(f"  Future:      {skipped_future}")
print(f"  Errors:      {errors}")
