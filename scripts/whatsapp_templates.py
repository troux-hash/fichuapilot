"""Create Fichua's WhatsApp message templates in your Meta account, or list their approval status.

    python scripts/whatsapp_templates.py list
    python scripts/whatsapp_templates.py create

Needs WHATSAPP_TOKEN (a system-user token with whatsapp_business_management) and
WHATSAPP_BUSINESS_ACCOUNT_ID in .env. Templates that already exist are left alone. Meta usually approves
utility templates within minutes to a few hours; until then, messages that use them fail and show as
"failed" in Admin -> WhatsApp messages, where "Send unsent messages again" retries them.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fichua.config import settings  # noqa: E402  (also loads .env)
from fichua.services import whatsapp_templates as wt  # noqa: E402

API = f"https://graph.facebook.com/{settings.whatsapp_api_version}"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{API}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {settings.whatsapp_token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Meta answered {exc.code}: {exc.read().decode(errors='replace')[:600]}") from exc


def existing(account: str) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    path: str | None = f"{account}/message_templates?fields=name,language,status&limit=200"
    while path:
        page = call("GET", path)
        for t in page.get("data", []):
            found[(t["name"], t["language"])] = t.get("status", "?")
        nxt = page.get("paging", {}).get("next")
        path = nxt.split(f"/{settings.whatsapp_api_version}/", 1)[1] if nxt else None
    return found


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    account = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
    if command not in ("list", "create"):
        raise SystemExit(__doc__)
    if not settings.whatsapp_token or not account:
        raise SystemExit("Set WHATSAPP_TOKEN and WHATSAPP_BUSINESS_ACCOUNT_ID in .env first.")
    have = existing(account)
    if command == "create":
        for name, lang in wt.all_versions():
            if (name, lang) not in have:
                result = call("POST", f"{account}/message_templates", wt.create_payload(name, lang))
                have[(name, lang)] = result.get("status", "PENDING")
                print(f"created   {name} [{lang}]")
    for name, lang in wt.all_versions():
        print(f"{have.get((name, lang), 'MISSING'):<10} {name} [{lang}]")


if __name__ == "__main__":
    main()
