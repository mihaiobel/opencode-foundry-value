# Daily prompt

Paste this into any opencode setup to get the same role picks as the page.

---

```text
Re-evaluate Azure Foundry models for opencode, region swedencentral, deployment
data-zone-standard (EU) only, and recommend the best model per agent role.

Sources, primary only, never guess:
- https://modelavailability.com/platforms/azure/regions/swedencentral?deployment=data-zone-standard+%28EU%29
  -> the model list. Open each model page and read the data-zone-standard (EU)
  card: input, output and cached input in USD per 1M tokens (short context),
  status and deprecation date. If that card has no price, use the global-standard
  card price and mark it with an asterisk. If neither has a price, mark it "no price".
- https://artificialanalysis.ai/models/<slug>  -> Intelligence Index, Cost per Task in USD,
  output speed in t/s. If the AA page is missing or has no index, mark it "no AA data".

Skip older releases of the same vendor and tier (gpt-6-sol replaces gpt-5-6-sol, and so on),
embeddings, rerank, OCR, image, audio, realtime, router models, status legacy
or deprecating, and anything retired within 180 days.
Blended price = (3 x input + output) / 4 per 1M tokens.

Role matrix, each model used once:
- orchestrator: lowest cached-input price at AA intel >= 38.
- dev: highest AA speed per blended dollar at AA intel >= 34.
- researcher: lowest blended price at AA intel >= 34.
- reviewer: highest AA intel at output <= $15/1M, from a vendor no other role uses.
  If every priced vendor is taken, use the best remaining model and say "same vendor".

Output:
1. Role table: role | model id | rationale | in/out $/1M, AA intel, AA speed.
2. Table of all chat models with price, AA values, retire date and recommended role.
3. Call out missing prices as "no price" and missing AA data as "no AA data".
```
