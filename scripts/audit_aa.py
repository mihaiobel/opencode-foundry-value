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
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = "opencode-foundry-value-audit/1.0"
MODELS_URL = "https://artificialanalysis.ai/models/"
DELAY = 1.0
TIMEOUT = 30

L_INTEL = "Artificial Analysis Intelligence Index"
L_SPEED = "Output tokens per second"
L_COST = "Cost per Intelligence Index task"

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


def audit(model_id: str) -> dict:
    slugs = [model_id, "releases/" + model_id]
    for slug in slugs:
        status, body = get(MODELS_URL + slug)
        if status != 200 or not body:
            continue
        intel = _num(_value(body, L_INTEL))
        speed = _num(_value(body, L_SPEED))
        cost = _num(_value(body, L_COST))
        if intel is not None and intel == int(intel):
            intel = int(intel)
        got = [v is not None for v in (intel, speed, cost)]
        return {
            "aa_intelligence": intel,
            "aa_speed_tps": speed,
            "aa_cost_per_task": cost,
            "aa_slug": slug,
            "aa_status": "ok" if all(got) else ("partial" if any(got) else "no_data"),
        }
    return {
        "aa_intelligence": None,
        "aa_speed_tps": None,
        "aa_cost_per_task": None,
        "aa_slug": None,
        "aa_status": "no_data",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/latest.json")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    data = json.load(open(args.data, encoding="utf-8"))

    print(f"{'ID':<22} | {'Intel':>5} | {'Speed':>7} | {'Cost':>6} | Status")
    for m in data["models"]:
        if not m.get("chat"):
            continue
        res = audit(m["id"])
        print(
            f"{m['id']:<22} | {res['aa_intelligence'] or '-':>5} | "
            f"{res['aa_speed_tps'] or '-':>7} | {res['aa_cost_per_task'] or '-':>6} | "
            f"{res['aa_status']}"
        )
        m.update(res)

    if args.write:
        with open(args.data, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
