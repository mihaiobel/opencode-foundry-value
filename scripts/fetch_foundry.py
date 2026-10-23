#!/usr/bin/env python3
"""Refresh the Foundry catalog in data/latest.json.

Source: modelavailability.com, Microsoft Foundry, region swedencentral,
deployment type "data-zone-standard (EU)". The site sits behind a Cloudflare
challenge, so a real browser is needed (playwright, chromium). The region
list gives the models; each model page embeds the Azure pricing and the
deprecation date as JSON in the Next.js payload.

Artificial Analysis values are carried over from the existing data file by
model id. Run scripts/audit_aa.py afterwards to fill gaps.

    python3 scripts/fetch_foundry.py --data data/latest.json > data/latest.json.tmp
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date

from playwright.sync_api import sync_playwright

BASE = "https://modelavailability.com"
REGION = "swedencentral"
DEPLOYMENT = "data-zone-standard (EU)"
REGION_URL = (
    f"{BASE}/platforms/azure/regions/{REGION}"
    "?deployment=data-zone-standard+%28EU%29"
)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# Non-chat models never compete for an agent role.
NON_CHAT = re.compile(
    r"(embed|rerank|ocr|document-ai|transcribe|tts|whisper|realtime|audio|"
    r"image|flux|live|decision|model-router|sora|dall)",
    re.I,
)
AA_KEYS = ("aa_intelligence", "aa_speed_tps", "aa_cost_per_task", "aa_status", "aa_slug")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def region_models(page) -> list[dict]:
    """Rows of the region table: vendor, name, version, status, link."""
    page.goto(REGION_URL, wait_until="load", timeout=90000)
    page.wait_for_selector("a[href^='/models/']", timeout=60000)
    rows = page.evaluate(
        """() => [...document.querySelectorAll('tr')].map(tr => {
            const a = tr.querySelector("a[href^='/models/']");
            if (!a) return null;
            const td = [...tr.querySelectorAll('td')].map(t => t.innerText.trim());
            return {href: a.getAttribute('href'), name: a.innerText.trim(), cells: td};
        }).filter(Boolean)"""
    )
    out = []
    for r in rows:
        cells = r["cells"]
        out.append(
            {
                "id": r["name"],
                "href": r["href"],
                "vendor": cells[0] if cells else None,
                "version": cells[2] if len(cells) > 2 else None,
                "status": cells[3] if len(cells) > 3 else None,
            }
        )
    return out


def azure_entry(html: str) -> dict | None:
    """Find the Azure availability card for DEPLOYMENT and decode it."""
    s = html.replace('\\"', '"')
    dec = json.JSONDecoder()
    needle = '{"availability":{"deploymentType":"%s"' % DEPLOYMENT
    pos, found = 0, None
    while True:
        i = s.find(needle, pos)
        if i < 0:
            return found
        pos = i + 1
        try:
            obj, _ = dec.raw_decode(s[i:])
        except json.JSONDecodeError:
            continue
        if obj.get("provider") != "Azure":
            continue
        pricing = obj["availability"].get("pricing") or []
        # RSC may replace repeated arrays by "$NN:..." references; keep looking.
        if any(isinstance(p, dict) for p in pricing):
            return obj
        found = found or obj


def parse_model(browser, row: dict) -> dict | None:
    # Fresh context per page: a reused one gets a Cloudflare challenge.
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()
    try:
        return _parse_model(page, row)
    finally:
        ctx.close()


def dom_prices(text: str) -> dict:
    """Short-context prices from the rendered card, used when the embedded
    JSON only holds a reference. The page rounds to two decimals."""
    i = text.find(DEPLOYMENT + "\nPricing (per 1M tokens)")
    if i < 0:
        return {}
    block = text[i:]
    block = block.split("\nRegions", 1)[0].split("Priority Pricing", 1)[0]
    out = {}
    for label, key in (
        ("Input", "input"),
        ("Output", "output"),
        ("Cached Input", "cached_input"),
    ):
        m = re.search(r"(?:^|\n)%s\n\$([0-9.,]+)" % label, block)
        if m:
            out[key] = float(m.group(1).replace(",", ""))
    return out


def _parse_model(page, row: dict) -> dict | None:
    page.goto(BASE + row["href"], wait_until="load", timeout=90000)
    obj = None
    # The Cloudflare check can delay the real page by a few seconds.
    for _ in range(20):
        obj = azure_entry(page.content())
        if obj:
            break
        page.wait_for_timeout(1000)
    if not obj:
        log(f"  no Azure {DEPLOYMENT} card: {row['href']}")
        return None
    av = obj["availability"]
    prices = {
        p["type"]: p["prices"] for p in av.get("pricing", []) if isinstance(p, dict)
    }
    short = prices.get("data-zone-standard", {})
    price_src = "json" if short else None
    if not short:
        short = dom_prices(page.inner_text("body"))
        price_src = "page" if short else None
    long_ = prices.get("data-zone-standard_long", {})
    return {
        "id": row["href"].rsplit("/", 1)[-1],
        "name": row["id"],
        "vendor": row["vendor"],
        "status": row["status"],
        "version": row["version"],
        "page": BASE + row["href"],
        "in_region": REGION in av.get("regions", []),
        "regions": av.get("regions", []),
        "deprecation": (av.get("deprecationDate") or "")[:10] or None,
        "price_src": price_src,
        "price_in": short.get("input"),
        "price_out": short.get("output"),
        "price_cached": short.get("cached_input", short.get("cache_read")),
        "price_in_long": long_.get("input"),
        "price_out_long": long_.get("output"),
        "chat": not NON_CHAT.search(row["href"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="existing data file; AA values are carried over")
    args = ap.parse_args()

    old, meta_old = {}, {}
    if args.data:
        try:
            prev = json.load(open(args.data, encoding="utf-8"))
            old = {m["id"]: m for m in prev.get("models", [])}
            meta_old = prev.get("meta", {})
        except (OSError, json.JSONDecodeError):
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_page(user_agent=UA)
        rows = region_models(page)
        log(f"{len(rows)} models in the region table")
        models = []
        for row in rows:
            m = parse_model(browser, row)
            if not m:
                continue
            if any(x["id"] == m["id"] for x in models):
                log(f"  duplicate id skipped: {m['id']}")
                continue
            models.append(m)
        browser.close()

    if not models:
        log("error: no models scraped, keeping old data")
        return 1

    for m in models:
        prev = old.get(m["id"], {})
        for k in AA_KEYS:
            m[k] = prev.get(k)
        if m["aa_status"] is None:
            m["aa_status"] = "no_data"

    meta = {
        **meta_old,
        "as_of": date.today().isoformat(),
        "platform": "Microsoft Foundry",
        "region": REGION,
        "deployment": DEPLOYMENT,
        "currency": "USD",
        "price_unit": "USD per 1M tokens",
        "aa_index_version": "Artificial Analysis Intelligence Index v4.3.2",
        "source_urls": [
            REGION_URL,
            "https://artificialanalysis.ai/models/",
        ],
        "notes": [
            "Prices are the short-context data-zone-standard (EU) prices on modelavailability.com, USD per 1M tokens. The site lists no EUR prices.",
            "price_src json = embedded page data, page = rendered card (two decimals). A model with no price on the site has price_in null and is never picked.",
            "AA values are carried over by model id; scripts/audit_aa.py fills them.",
        ],
    }
    json.dump({"meta": meta, "models": models}, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
