#!/usr/bin/env python3
"""Fill the Artificial Analysis columns of data/latest.json.

Standard library only. For every chat model the page tries
https://artificialanalysis.ai/models/<foundry-id> and, when that is a 404,
the releases/ path. From a 200 page the model-summary block is scraped with a
regex: Intelligence Index, output speed (tokens/s), cost per Intelligence
Index task. A model without an AA page gets aa_status "no_data"; nothing is
guessed and no -pro / -max fallback is tried.

One request per second, 30s timeout.

    python3 scripts/audit_aa.py --data data/latest.json            # print only
    python3 scripts/audit_aa.py --data data/latest.json --write    # update file

Version check: the AA page title and release date are stored (aa_title,
aa_release). If the AA release date differs by more than 3 days from the
Foundry version date, the values belong to another revision of the model. The
row gets aa_status "version_mismatch", the values are dropped and the model is
never picked, until AA_SLUG_OVERRIDES points to the matching AA page.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime

USER_AGENT = "opencode-foundry-value-audit/1.0"
MODELS_URL = "https://artificialanalysis.ai/models/"
DELAY = 1.0
TIMEOUT = 30

L_INTEL = "Artificial Analysis Intelligence Index"
L_SPEED = "Output tokens per second"
L_COST = "Cost per Intelligence Index task"

# Foundry id -> AA slug, where the plain id is a different revision on AA.
AA_SLUG_OVERRIDES = {
    # AA's deepseek-v4-flash is the 0731 revision; Foundry hosts the April one.
    "deepseek-v4-flash": "deepseek-v4-flash-0420",
}
MAX_DAYS_APART = 3

_LAST = 0.0


def get(url: str) -> tuple[int | None, str | None]:
    global _LAST
    wait = DELAY - (time.monotonic() - _LAST)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            _LAST = time.monotonic()
            return resp.status, body
    except urllib.error.HTTPError as exc:
        _LAST = time.monotonic()
        return exc.code, None
    except Exception as exc:  # noqa: BLE001 - report and keep going
        _LAST = time.monotonic()
        print(f"  warn: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None, None


def _value(html: str, label: str) -> str | None:
    before = re.search(
        r"<span[^>]*>([^<]{1,24})</span>\s*</div>\s*<div[^>]*>\s*" + re.escape(label),
        html,
        re.I,
    )
    if before:
        return before.group(1).strip()
    after = re.search(
        re.escape(label) + r"</div>\s*(?:<[^>]+>\s*)*?<span[^>]*>([^<]{1,24})</span>",
        html,
        re.I,
    )
    return after.group(1).strip() if after else None


def _num(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _page_info(body: str) -> tuple[str | None, date | None]:
    title = re.search(r"<title>([^<]*)", body)
    name = html.unescape(title.group(1)).split(" - ")[0].strip() if title else None
    text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)))
    rel = re.search(r"was released on ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    when = None
    if rel:
        try:
            when = datetime.strptime(rel.group(1), "%B %d, %Y").date()
        except ValueError:
            pass
    return name, when


def _ref_date(m: dict) -> date | None:
    """Foundry date to compare with: the version when it is a date, else the release."""
    for key in ("version", "released"):
        try:
            return date.fromisoformat(str(m.get(key)))
        except ValueError:
            continue
    return None


EMPTY = {
    "aa_intelligence": None,
    "aa_speed_tps": None,
    "aa_cost_per_task": None,
    "aa_slug": None,
    "aa_title": None,
    "aa_release": None,
}


def audit(m: dict) -> dict:
    model_id = m["id"]
    base = AA_SLUG_OVERRIDES.get(model_id, model_id)
    for slug in (base, "releases/" + base):
        status, body = get(MODELS_URL + slug)
        if status != 200 or not body:
            continue
        name, when = _page_info(body)
        ref = _ref_date(m)
        info = {"aa_slug": slug, "aa_title": name, "aa_release": when.isoformat() if when else None}
        if when and ref and abs((when - ref).days) > MAX_DAYS_APART:
            return {**EMPTY, **info, "aa_status": "version_mismatch"}
        intel = _num(_value(body, L_INTEL))
        speed = _num(_value(body, L_SPEED))
        cost = _num(_value(body, L_COST))
        if intel is not None and intel == int(intel):
            intel = int(intel)
        got = [v is not None for v in (intel, speed, cost)]
        return {
            **info,
            "aa_intelligence": intel,
            "aa_speed_tps": speed,
            "aa_cost_per_task": cost,
            "aa_status": "ok" if all(got) else ("partial" if any(got) else "no_data"),
        }
    return {**EMPTY, "aa_status": "no_data"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/latest.json")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    data = json.load(open(args.data, encoding="utf-8"))

    print(f"{'ID':<22} | {'Intel':>5} | {'Speed':>7} | {'Cost':>6} | {'Status':<16} | AA page")
    for m in data["models"]:
        if not m.get("chat"):
            continue
        res = audit(m)
        print(
            f"{m['id']:<22} | {res['aa_intelligence'] or '-':>5} | "
            f"{res['aa_speed_tps'] or '-':>7} | {res['aa_cost_per_task'] or '-':>6} | "
            f"{res['aa_status']:<16} | {res['aa_title']} ({res['aa_release']})"
        )
        m.update(res)

    if args.write:
        with open(args.data, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
