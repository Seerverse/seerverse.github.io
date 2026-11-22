#!/usr/bin/env python3
"""Rebuild data/profile.json from the public profile pages of 0xSeerBear.

Standard library only. Payout amounts are never read into the output.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "profile.json"
UA = {"User-Agent": "Mozilla/5.0 (seerverse.github.io profile sync)"}

PROFILES = {
    "Sherlock": "https://audits.sherlock.xyz/watson/0xSeerBear",
    "Code4rena": "https://code4rena.com/@0xSeer",
    "Cantina": "https://cantina.xyz/u/0xSeer",
    "HackenProof": "https://hackenproof.com/hackers/0xseerbear",
}
SEVERITIES = ("critical", "high", "medium", "low")
MONTH = re.compile(r"^[A-Z][a-z]{2} '\d\d$")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def text_lines(page: str) -> list[str]:
    page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"<[^>]+>", "\n", page)
    return [s.strip() for s in html.unescape(page).splitlines() if s.strip()]


def month_iso(label: str) -> str:
    return datetime.strptime(label, "%b '%y").strftime("%Y-%m")


def sherlock() -> tuple[dict, list[dict]]:
    """Sherlock's profile lists Sherlock and Code4rena findings together."""
    lines = text_lines(fetch(PROFILES["Sherlock"]))
    stats: dict = {}
    for i, s in enumerate(lines[:-2]):
        if s in ("High", "Medium") and lines[i + 2] == "Total":
            stats[s.lower()] = int(lines[i + 1])
        if s == "#" and lines[i + 2] == "All Time":
            stats["rank"] = int(lines[i + 1].replace(",", ""))
    findings: list[dict] = []
    month = None
    i = 0
    while i < len(lines):
        s = lines[i]
        if MONTH.match(s):
            month = month_iso(s)
        # A contest block: <name> <amount> USDC • N total finding(s) • <platform> • <handle> # <place>
        if s == "USDC" and i >= 2 and lines[i + 2].endswith("•") and "total finding" in lines[i + 2]:
            contest = lines[i - 2]
            platform = lines[i + 3]
            place = int(lines[i + 7]) if lines[i + 6] == "#" else None
            j = i + 8
            while j + 1 < len(lines) and lines[j].lower() in SEVERITIES:
                findings.append({
                    "platform": platform,
                    "competition": contest,
                    "date": month,
                    "severity": lines[j].lower(),
                    "title": lines[j + 1],
                    "placement": place,
                    "status": "accepted",
                })
                j += 2
            i = j
            continue
        i += 1
    return stats, findings


def code4rena() -> dict:
    lines = text_lines(fetch(PROFILES["Code4rena"]))
    stats: dict = {}
    for i, s in enumerate(lines[:-1]):
        if s in ("High", "Medium", "Low") and lines[i - 1].isdigit() and "Valid findings" in lines[max(0, i - 6):i]:
            stats[s.lower()] = int(lines[i - 1])
        if s == "All-time" and lines[i - 2] == "#":
            stats["rank"] = int(lines[i - 1].replace(",", ""))
    return stats


def cantina() -> dict:
    page = fetch(PROFILES["Cantina"])
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S)
    blob = "".join(json.loads('"' + c + '"') for c in chunks)
    stats: dict = {}
    for sev in SEVERITIES:
        m = re.search(rf'"{sev}Findings":(\d+)', blob)
        if m:
            stats[sev] = int(m.group(1))
    m = re.search(r'"reputation":(\d+)', blob)
    if m:
        stats["reputation"] = int(m.group(1))
    return stats


def hackenproof() -> tuple[dict, list[dict]]:
    page = fetch(PROFILES["HackenProof"])
    raw = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not raw:
        raise ValueError("no __NUXT_DATA__")
    d = json.loads(raw.group(1))

    def val(ref):
        return d[ref] if isinstance(ref, int) and 0 <= ref < len(d) else ref

    me = next(x for x in d if isinstance(x, dict) and val(x.get("nickname")) == "0xseerbear"
              and "influenced_programs" in x)
    stats = {"rank": val(me["rank"])}
    profile = val(me["user_profile"])
    if isinstance(profile, dict):
        stats["reputation"] = val(profile.get("reputation"))
    rows = []
    for ref in val(me["influenced_programs"]):
        entry = val(ref)
        prog = val(entry["program"])
        rows.append({
            "platform": "HackenProof",
            "competition": val(prog["title"]),
            "date": None,
            "severity": "undisclosed",
            "title": "Hall of fame; severity not public",
            "count": val(entry["reports_amount"]),
            "placement": val(entry["rank"]),
            "status": "accepted",
            "link": "https://hackenproof.com/programs/" + val(prog["slug"]),
        })
    return stats, rows


def main() -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    old_profiles = {p["platform"]: p for p in old.get("profiles", [])}
    profiles, findings, errors = [], [], []

    def run(platform: str, fn):
        try:
            res = fn()
        except Exception as e:  # keep the last good data for a platform that failed
            errors.append(f"{platform}: {e}")
            prev = old_profiles.get(platform)
            if prev:
                profiles.append(prev)
            findings.extend(f for f in old.get("findings", []) if f.get("source", f["platform"]) == platform)
            return
        stats, rows = res if isinstance(res, tuple) else (res, [])
        profiles.append({"platform": platform, "url": PROFILES[platform], "stats": stats})
        for r in rows:
            r["source"] = platform
        findings.extend(rows)

    run("Sherlock", sherlock)
    run("Code4rena", code4rena)
    run("Cantina", cantina)
    run("HackenProof", hackenproof)

    findings.sort(key=lambda f: f["date"] or "", reverse=True)
    data = {
        "handle": "0xSeerBear",
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profiles": profiles,
        "findings": findings,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for e in errors:
        print("warning:", e, file=sys.stderr)
    print(f"{len(findings)} findings, {len(profiles)} profiles, {len(errors)} errors")
    return 1 if len(errors) == len(PROFILES) else 0


if __name__ == "__main__":
    sys.exit(main())
