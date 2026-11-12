#!/usr/bin/env python3
"""Search Job Alerts by Herakraft for open US intern/new-grad roles.

Keyless free tier: 30 requests/min per IP, up to 20 roles per page.
API reference: https://recruiting.herakraft.co/api/v1/openapi.json

Usage:
    python src/roles.py --track swe --level new-grad --grad 2027 --limit 60 --out shortlist.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

API_URL = "https://recruiting.herakraft.co/api/v1/roles"
REQUEST_DELAY_S = 2.1  # stay under the 30 req/min keyless limit


def fetch_page(params: dict) -> dict:
    url = API_URL + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        # The API 403s the default Python-urllib user agent.
        "User-Agent": "apply-agent/0.1 (+https://recruiting.herakraft.co)",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def search(level: str, track: str | None, q: str | None, grad: str | None,
           since: str | None, limit: int) -> list[dict]:
    roles: list[dict] = []
    cursor = None
    params = {"level": level, "track": track, "q": q, "grad": grad, "since": since, "limit": 20}
    while len(roles) < limit:
        params["cursor"] = cursor
        page = fetch_page(params)
        batch = page.get("data", [])
        if not batch:
            break
        roles.extend(batch)
        cursor = page.get("next_cursor")
        if not cursor:
            break
        time.sleep(REQUEST_DELAY_S)
    return roles[:limit]


def slim(role: dict) -> dict:
    return {
        "id": role.get("id"),
        "title": role.get("title"),
        "company": (role.get("company") or {}).get("name"),
        "track": role.get("track"),
        "level": role.get("level"),
        "location": (role.get("location") or {}).get("raw"),
        "workplace": (role.get("location") or {}).get("workplace"),
        "graduation_window": [
            (role.get("education") or {}).get("graduation_start"),
            (role.get("education") or {}).get("graduation_end"),
        ],
        "sponsorship": (role.get("eligibility") or {}).get("sponsorship"),
        "citizenship_required": (role.get("eligibility") or {}).get("citizenship_required"),
        "first_seen_at": role.get("first_seen_at"),
        "apply_url": role.get("apply_url"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Search Herakraft Job Alerts roles.")
    p.add_argument("--level", default="all", choices=["intern", "new-grad", "all"])
    p.add_argument("--track", default=None, help="e.g. swe, backend, frontend, fullstack, data")
    p.add_argument("--q", default=None, help="free-text query")
    p.add_argument("--grad", default=None, help="graduation year filter, e.g. 2027")
    p.add_argument("--since", default=None, choices=["24h", "7d", "30d"])
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--out", default=None, help="write results JSON here")
    args = p.parse_args()

    roles = search(args.level, args.track, args.q, args.grad, args.since, args.limit)
    results = [slim(r) for r in roles]

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
    print(json.dumps({"count": len(results), "roles": results[:5]}, indent=2))
    print(f"total fetched: {len(results)}" + (f" -> {args.out}" if args.out else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
