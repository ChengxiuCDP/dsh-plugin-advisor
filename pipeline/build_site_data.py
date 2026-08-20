#!/usr/bin/env python3
"""Build the site-consumable data bundle (site-data/*.json) from site_data.

Plugins CI runs the full pipeline daily; this step exports exactly the three
files the dsh-plugin-hub site's build consumes, so the site's own workflow
only downloads + rebuilds + redeploys (no second crawl).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE_DATA = os.path.join(ROOT, "site_data")
OUT = os.path.join(ROOT, "site-data")

plugins = json.load(open(os.path.join(SITE_DATA, "plugins.json")))
stats = json.load(open(os.path.join(SITE_DATA, "stats.json")))

def day(iso):
    return iso[:10] if iso else ""

ui = []
index = []
for p in plugins:
    ui.append({
        "full_name": p["full_name"],
        "url": p["html_url"],
        "desc": p["description"],
        "stars": p["stargazers_count"],
        "quality": p["quality"],
        "cluster": p["cluster"],
        "language": p["language"],
        "license": p["license"],
        "installable": p["bundle"],
        "curated": p["curated"],
        "flags": p["flags"],
        "updated": day(p["pushed_at"]),
        "created": day(p["created_at"]),
    })
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

os.makedirs(OUT, exist_ok=True)
json.dump(ui, open(os.path.join(OUT, "plugins.json"), "w"), ensure_ascii=False, separators=(",", ":"))
json.dump(stats, open(os.path.join(OUT, "stats.json"), "w"), ensure_ascii=False)
json.dump(index, open(os.path.join(OUT, "index.json"), "w"), ensure_ascii=False, separators=(",", ":"))
print(f"site-data: plugins={len(ui)}, stats.date={stats.get('date')}, index={len(index)}")
