#!/usr/bin/env python3
"""Daily plugin index refresher.

Fetches the full topic:dsh-plugin census (date-bucket slicing to bypass the
1000-result search cap, star-range slicing for oversized buckets), merges with
the previous snapshot, and writes today's snapshot JSON.

Usage: python3 pipeline/fetch_census.py [--date 2026-08-16]
"""
import json
import subprocess
import sys
import time
import datetime
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS = os.path.join(HERE, "snapshots")

def log(msg):
    print(f"[{datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')}] {msg}", file=sys.stderr, flush=True)

def gh_search(q, page=1, per_page=100):
    args = ["gh", "api", "-X", "GET", "search/repositories",
            "-f", f"q={q}", "-f", f"per_page={per_page}", "-f", f"page={page}",
            "-f", "sort=stars", "-f", "order=desc"]
    for attempt in range(4):
        r = subprocess.run(args, capture_output=True, text=True)
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            log(f"bad json for {q} p{page}: {r.stdout[:120]}")
            time.sleep(6)
    return None

def slim(it):
    return {
        "id": it["id"],
        "full_name": it["full_name"],
        "owner": it["owner"]["login"],
        "owner_type": it["owner"]["type"],
        "html_url": it["html_url"],
        "description": it["description"] or "",
        "stargazers_count": it["stargazers_count"],
        "forks_count": it["forks_count"],
        "language": it["language"],
        "topics": it.get("topics", []),
        "created_at": it["created_at"],
        "pushed_at": it["pushed_at"],
        "open_issues_count": it["open_issues_count"],
        "homepage": it.get("homepage"),
        "license": (it.get("license") or {}).get("spdx_id"),
        "default_branch": it["default_branch"],
        "archived": it.get("archived", False),
        "disabled": it.get("disabled", False),
    }

def fetch_query(q, label):
    """Fetch all pages of one query (up to the 1000-cap), return list of slim dicts."""
    items = []
    page = 1
    while page <= 10:
        data = gh_search(q, page=page)
        if data is None:
            log(f"page failed {label} p{page}")
            break
        got = data.get("items", [])
        items.extend(slim(it) for it in got)
        log(f"{label} p{page}: +{len(got)} (total {len(items)})")
        if len(got) < 100:
            break
        page += 1
        time.sleep(1.0)
    time.sleep(1.0)
    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"))
    args = ap.parse_args()
    today = args.date

    # 1) probe date buckets (today and the last 7 days; earlier mass already covered)
    log("probing buckets...")
    buckets = []
    today_d = datetime.date.fromisoformat(today)
    pre_start = (today_d - datetime.timedelta(days=8)).isoformat()
    probes = [f"created:<{pre_start}"] + [f"created:{d}" for d in [(today_d - datetime.timedelta(days=i)).isoformat() for i in range(7, -1, -1)]] + [f"created:>={today}"]
    seen = set()
    for b in probes:
        if b in seen: continue
        seen.add(b)
        data = gh_search(f"topic:dsh-plugin {b}", page=1, per_page=1)
        total = data.get("total_count", 0) if data else -1
        log(f"bucket {b}: total={total}")
        if total > 0:
            buckets.append((b, total))
        time.sleep(1.0)

    # 2) paginate; re-slice buckets exceeding the 1000-result cap by star ranges
    collected = {}
    STAR_SLICES = ["stars:<1", "stars:1..2", "stars:3..4", "stars:5..9", "stars:10..99", "stars:>=100"]
    for b, total in buckets:
        log(f"== bucket {b} (total {total}) ==")
        if total <= 1000:
            for it in fetch_query(f"topic:dsh-plugin {b}", b):
                collected[it["id"]] = it
        else:
            for sl in STAR_SLICES:
                q = f"topic:dsh-plugin {b} {sl}"
                probe = gh_search(q, page=1, per_page=1)
                sl_total = probe.get("total_count", 0) if probe else 0
                if sl_total <= 0: continue
                log(f"  slice {sl}: {sl_total}")
                for it in fetch_query(q, f"{b} {sl}"):
                    collected[it["id"]] = it

    log(f"fetched {len(collected)} unique repos")

    os.makedirs(SNAPSHOTS, exist_ok=True)
    # 3) merge with previous snapshot (keep yesterday's entries that vanished from search)
    prev_path = None
    for name in sorted(os.listdir(SNAPSHOTS)):
        if name.endswith(".json"):
            prev_path = os.path.join(SNAPSHOTS, name)
    if prev_path:
        prev = json.load(open(prev_path))
        prev_repos = prev.get("repos", prev) if isinstance(prev, dict) else prev
        if isinstance(prev_repos, dict):
            prev_repos = list(prev_repos.values())
        for r in prev_repos:
            collected.setdefault(r["id"], r)
        log(f"merged with {os.path.basename(prev_path)} -> {len(collected)}")

    repos = sorted(collected.values(), key=lambda r: -r["stargazers_count"])
    os.makedirs(SNAPSHOTS, exist_ok=True)
    out = {
        "date": today,
        "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "n_repos": len(repos),
        "bucket_totals": {b: t for b, t in buckets},
        "repos": repos,
    }
    dest = os.path.join(SNAPSHOTS, f"{today}.json")
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    log(f"wrote {dest} ({len(repos)} repos)")

if __name__ == "__main__":
    main()
