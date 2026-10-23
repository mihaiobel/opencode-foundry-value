# opencode-foundry Value

Which Azure Foundry model should run which opencode agent role, if it has to be hosted in
Sweden Central under the EU data zone? One pick each for orchestrator, dev, reviewer and
researcher, based on Foundry prices and Artificial Analysis benchmarks.

Sister project of opencode-go-value. Same page, same role logic. The Go plan quota is
replaced by the plain token price.

## How it works

- Scope: Microsoft Foundry, region `swedencentral`, deployment `data-zone-standard (EU)`.
- The model list and prices come from modelavailability.com. It sits behind a Cloudflare
  challenge, so `scripts/fetch_foundry.py` needs playwright and chromium.
- Prices are USD per 1M tokens, short context. The source shows no EUR prices.
- A model with no price on the source is marked `no price` and never picked. Nothing is guessed.
- Intelligence Index, speed and cost per task come from Artificial Analysis. A model without
  an index is marked `no AA data`.
- Models with status legacy or deprecating, or retiring within 180 days, are never picked.
- Role rules are in `refresh-prompt.md` and implemented in `app.js`. Each model is used once.

## Files

| File | Purpose |
|---|---|
| `index.html`, `app.js`, `styles.css` | The page, no external requests |
| `data/latest.json` | Model data and metadata |
| `scripts/fetch_foundry.py` | Scrapes region list and EU prices (playwright) |
| `scripts/audit_aa.py` | Fills the Artificial Analysis columns, standard library only |
| `refresh-prompt.md` | Prompt to run the same evaluation in any opencode setup |
| `.github/workflows/pages.yml` | GitHub Pages deploy (copied from opencode-go-value, untested here) |

## Updating the data

```bash
pip install playwright && playwright install chromium
python3 scripts/fetch_foundry.py --data data/latest.json > data/latest.json.tmp
mv data/latest.json.tmp data/latest.json
python3 scripts/audit_aa.py --data data/latest.json --write
```

## Run locally

```bash
python3 -m http.server 8000
```

## License

Site code MIT. Data from [modelavailability.com](https://modelavailability.com/) and
[Artificial Analysis](https://artificialanalysis.ai/), reuse with attribution.
