#!/usr/bin/env python3
"""Score + cluster + installable-probe the daily snapshot into site data.

Outputs:
  site_data/plugins.json   — enriched repo list (quality score, flags, cluster)
  site_data/stats.json     — ecosystem aggregates incl. daily time series
"""
import json
import os
import re
import subprocess
import datetime
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAPSHOTS = os.path.join(HERE, "snapshots")
CACHE = os.path.join(HERE, "cache")
SITE_DATA = os.path.join(ROOT, "site_data")
AWESOME = os.path.join(HERE, "awesome.md")
BUNDLE_CACHE = os.path.join(CACHE, "bundle_probe.json")

CLUSTERS = {
    "余额/用量/计费": [r"usage", r"balance", r"余额", r"quota", r"用量", r"\bcost\b", r"计费", r"token.{0,12}(stats|spend|usage|count)", r"heatmap", r"花费"],
    "宠物/陪伴": [r"\bpet\b", r"宠物", r"mascot", r"吉祥物", r"maid-whale"],
    "视觉/读图": [r"vision", r"视觉", r"image.{0,10}(transcri|to text|reading)", r"\bOCR\b", r"读图", r"多模态", r"识别图片"],
    "语音/听写/TTS": [r"voice", r"语音", r"\bmic\b", r"麦克风", r"speech", r"transcrib", r"\btts\b", r"听写", r"朗读"],
    "主题/皮肤/外观": [r"theme", r"主题", r"\bskin\b", r"皮肤", r"appearance", r"外观"],
    "移动/远程/局域网": [r"mobile", r"移动", r"手机", r"remote", r"\blan\b", r"局域网", r"tailscale", r"公网"],
    "终端/TUI/PTY": [r"\btui\b", r"terminal", r"终端", r"ratatui", r"\bpty\b", r"xterm", r"\bshell\b"],
    "桌面/托盘/窗口": [r"desktop", r"桌面", r"tray", r"托盘", r"WebView2", r"窗口"],
    "上下文/会话/记忆": [r"context", r"上下文", r"session", r"会话", r"memory", r"记忆"],
    "模型/供应商/路由": [r"model", r"provider", r"模型", r"路由", r"newapi", r"api key", r"fallback", r"降级"],
    "市场/发现/安装": [r"market", r"市场", r"plugin find", r"awesome", r"install", r"安装"],
    "工作流/自动化/任务": [r"workflow", r"工作流", r"automation", r"自动化", r"\bcron\b", r"定时", r"\btask\b", r"任务"],
    "代码质量/评审/架构": [r"lint", r"review", r"评审", r"architect", r"架构", r"code quality", r"技术债", r"\beval\b"],
    "Git/文件/工作区": [r"git", r"file", r"文件", r"workspace", r"工作区", r"commit"],
    "通知/集成/消息": [r"notify", r"通知", r"推送", r"飞书", r"钉钉", r"slack", r"discord", r"微信", r"integration", r"集成"],
    "安全/登录/权限/审批": [r"auth", r"login", r"登录", r"permission", r"权限", r"approval", r"审批", r"sandbox", r"沙箱"],
    "写作/导出/分享": [r"writing", r"写作", r"export", r"导出", r"share", r"分享"],
    "技能/Skill/预设": [r"\bskill\b", r"技能", r"preset", r"预设"],
    "趣味/表情/娱乐": [r"meme", r"表情包", r"玩具", r"sticker", r"\bfun\b", r"好玩", r"游戏"],
    "图表/文档/知识": [r"diagram", r"图表", r"mermaid", r"文档", r"wiki", r"知识", r"白板", r"\bdoc\b"],
}

GOOD_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "ISC", "MPL-2.0", "Unlicense"}

def log(msg):
    print(msg, file=os.sys.stderr, flush=True)

def latest_snapshot():
    names = sorted(n for n in os.listdir(SNAPSHOTS) if n.endswith(".json"))
    if not names:
        raise SystemExit("no snapshot found")
    return names[-1], json.load(open(os.path.join(SNAPSHOTS, names[-1])))

def parse_awesome_names():
    names = set()
    with open(AWESOME) as f:
        for line in f:
            m = re.match(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*-\s*", line)
            if m:
                names.add(re.sub(r"#.*$", "", m.group(1).strip().lower()))
    return names

def probe_bundle(repo):
    """Check whether the repo's package.json declares dsh.bundle. Returns dict or None."""
    full, branch = repo["full_name"], repo["default_branch"]
    key = f"{full}@{branch}"
    url = f"https://raw.githubusercontent.com/{full}/{branch}/package.json"
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "10", url],
            capture_output=True, text=True, timeout=12,
        )
        if r.returncode != 0 or not r.stdout:
            return key, False
        pkg = r.stdout[:60000]
        has_bundle = bool(re.search(r'"dsh"\s*:\s*\{[^}]*"bundle"', pkg, re.DOTALL))
        return key, has_bundle
    except Exception:
        return key, False

def assign_cluster(r):
    text = (r["full_name"] + " " + r["description"]).lower()
    best, best_n = None, 0
    for name, pats in CLUSTERS.items():
        n = sum(len(re.findall(p, text, re.IGNORECASE)) for p in pats)
        if n > best_n:
            best, best_n = name, n
    return best

def score(r, curated, bundle, now):
    s = 0
    flags = []
    if curated: s += 30
    if bundle: s += 25
    lic = r["license"]
    if lic in GOOD_LICENSES:
        s += 15
    elif lic == "NOASSERTION":
        flags.append("noassertion")
    elif lic is None:
        s -= 10
        flags.append("nolicense")
    import math
    s += min(20, math.log10(r["stargazers_count"] + 1) * 5)
    days = (now - datetime.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))).days
    if days <= 7: s += 10
    elif days <= 30: s += 5
    else: flags.append("stale")
    if r.get("archived"): s -= 20; flags.append("archived")
    if r.get("homepage"): s += 3
    if curated and not bundle:
        flags.append("curated-nobundle")
    return round(max(0, min(100, s)), 1), flags

def main():
    name, snap = latest_snapshot()
    log(f"snapshot: {name} ({snap.get('n_repos')} repos)")
    now = datetime.datetime.now(datetime.timezone.utc)
    curated = parse_awesome_names()
    log(f"curated entries: {len(curated)}")

    cache = {}
    os.makedirs(CACHE, exist_ok=True)
    if os.path.exists(BUNDLE_CACHE):
        cache = json.load(open(BUNDLE_CACHE))
    repos = snap["repos"]
    todo = [r for r in repos if f"{r['full_name']}@{r['default_branch']}" not in cache]
    log(f"bundle probes pending: {len(todo)}")
    if todo:
        with ThreadPoolExecutor(max_workers=16) as ex:
            for i, (key, has) in enumerate(ex.map(probe_bundle, todo)):
                cache[key] = has
                if (i + 1) % 500 == 0:
                    log(f"  probed {i + 1}/{len(todo)}")
        json.dump(cache, open(BUNDLE_CACHE, "w"))

    enriched = []
    for r in repos:
        bundle = bool(cache.get(f"{r['full_name']}@{r['default_branch']}"))
        is_curated = r["full_name"].lower() in curated
        sc, flags = score(r, is_curated, bundle, now)
        r2 = dict(r)
        r2.update({
            "bundle": bundle,
            "curated": is_curated,
            "quality": sc,
            "flags": flags,
            "cluster": assign_cluster(r),
        })
        enriched.append(r2)
    enriched.sort(key=lambda r: -r["quality"])
    os.makedirs(SITE_DATA, exist_ok=True)
    json.dump(enriched, open(os.path.join(SITE_DATA, "plugins.json"), "w"), ensure_ascii=False)
    log(f"wrote site_data/plugins.json ({len(enriched)})")

    # stats
    from collections import Counter
    def days_bucket(iso):
        return iso[:10]
    daily = Counter(days_bucket(r["created_at"]) for r in enriched)
    daily_series = [{"date": d, "count": daily[d]} for d in sorted(daily)]
    stats = {
        "date": snap.get("date") or name,
        "fetched_at": snap.get("fetched_at"),
        "n_repos": len(enriched),
        "star_buckets": {
            "0": sum(1 for r in enriched if r["stargazers_count"] == 0),
            "1-9": sum(1 for r in enriched if 1 <= r["stargazers_count"] < 10),
            "10-99": sum(1 for r in enriched if 10 <= r["stargazers_count"] < 100),
            "100-999": sum(1 for r in enriched if 100 <= r["stargazers_count"] < 1000),
            "1000+": sum(1 for r in enriched if r["stargazers_count"] >= 1000),
        },
        "license": dict(Counter(r["license"] or "(none)" for r in enriched).most_common(12)),
        "language": dict(Counter(r["language"] or "(none)" for r in enriched).most_common(10)),
        "clusters": dict(Counter(r["cluster"] for r in enriched if r["cluster"]).most_common(25)),
        "installable": sum(1 for r in enriched if r["bundle"]),
        "curated": sum(1 for r in enriched if r["curated"]),
        "noassertion": sum(1 for r in enriched if r["license"] == "NOASSERTION"),
        "nolicense": sum(1 for r in enriched if r["license"] is None),
        "active_48h": sum(1 for r in enriched if (now - datetime.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))).days <= 2),
        "daily_series": daily_series,
        "top_star": [{"full_name": r["full_name"], "stars": r["stargazers_count"], "desc": r["description"][:90], "license": r["license"]} for r in sorted(enriched, key=lambda x: -x["stargazers_count"])[:25]],
        "top_quality": [{"full_name": r["full_name"], "quality": r["quality"], "stars": r["stargazers_count"], "cluster": r["cluster"]} for r in enriched[:25]],
    }
    json.dump(stats, open(os.path.join(SITE_DATA, "stats.json"), "w"), ensure_ascii=False, indent=1)
    log(f"wrote site_data/stats.json")

if __name__ == "__main__":
    main()
