"""Check (and wait for) Vercel deployments of this project. Stdlib only.

    python scripts/vercel_status.py            # latest deployment: state, URL, commit
    python scripts/vercel_status.py --wait     # block until it is READY or fails (exit 1 on failure)
    python scripts/vercel_status.py --logs     # print the build log of the latest deployment

Reads VERCEL_TOKEN from .env (never printed). Every push to `main` deploys automatically;
this script only reports on it.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "fichuapilot"


def _env() -> dict[str, str]:
    path = ROOT / ".env"
    pairs = (l.split("=", 1) for l in path.read_text(encoding="utf-8").splitlines()
             if "=" in l and not l.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


TOKEN = _env().get("VERCEL_TOKEN", "")


def call(path: str):
    req = urllib.request.Request("https://api.vercel.com" + path,
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Vercel API error {e.code}: {e.read()[:300]!r}")


def team_id() -> str:
    return call("/v2/user")["user"]["defaultTeamId"]


def latest(team: str) -> dict:
    deps = call(f"/v6/deployments?projectId={PROJECT}&limit=1&teamId={team}")["deployments"]
    if not deps:
        sys.exit("No deployments yet.")
    return deps[0]


def show(d: dict) -> None:
    meta = d.get("meta") or {}
    print(f"{d.get('state') or d.get('readyState')}  {d.get('target') or 'preview'}  "
          f"https://{d['url']}  commit {meta.get('githubCommitSha', '')[:7]} "
          f"\"{meta.get('githubCommitMessage', '').splitlines()[0] if meta.get('githubCommitMessage') else ''}\"")


def main() -> int:
    if not TOKEN:
        sys.exit("VERCEL_TOKEN missing from .env")
    team = team_id()
    d = latest(team)
    if "--logs" in sys.argv:
        for e in call(f"/v3/deployments/{d['uid']}/events?teamId={team}&limit=-1"):
            text = (e.get("payload") or {}).get("text") or e.get("text")
            if text:
                print(text)
        return 0
    if "--wait" in sys.argv:
        while (d.get("state") or d.get("readyState")) not in ("READY", "ERROR", "CANCELED"):
            time.sleep(5)
            d = latest(team)
    show(d)
    return 0 if (d.get("state") or d.get("readyState")) in ("READY", "BUILDING", "QUEUED", "INITIALIZING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
