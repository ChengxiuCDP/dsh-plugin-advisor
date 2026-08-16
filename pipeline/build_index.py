#!/usr/bin/env python3
"""Build the plugin's shipped index from site_data: data/index.json + data/meta.json."""
import json
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE_DATA = os.path.join(ROOT, "site_data")
DATA = os.path.join(ROOT, "data")
SNAPSHOTS = os.path.join(HERE, "snapshots")

plugins = json.load(open(os.path.join(SITE_DATA, "plugins.json")))

def day(iso):
    return iso[:10] if iso else ""

index = []
for p in plugins:
    index.append({
        "full_name": p["full_name"],
        "url": p["html_url"],
        "desc": p["description"],
        "cluster": p["cluster"],
        "quality": p["quality"],
        "stars": p["stargazers_count"],
        "language": p["language"],
        "license": p["license"],
        "installable": p["bundle"],
        "updated": day(p["pushed_at"]),
        "flags": p["flags"],
    })

snap_names = sorted(n for n in os.listdir(SNAPSHOTS) if n.endswith(".json"))
date = snap_names[-1][:10] if snap_names else datetime.date.today().isoformat()

os.makedirs(DATA, exist_ok=True)
json.dump(index, open(os.path.join(DATA, "index.json"), "w"), ensure_ascii=False, separators=(",", ":"))
json.dump({"date": date}, open(os.path.join(DATA, "meta.json"), "w"), ensure_ascii=False)
print(f"index: {len(index)} entries, date: {date}")
