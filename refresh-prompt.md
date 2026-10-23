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
  output speed in t/s. The AA page must be the same revision as the Foundry model:
  compare release dates (within 3 days) and the reasoning variant. If the AA page is
  missing, has no index or is another revision, mark it "no AA data".

Skip older releases of the same vendor and tier (gpt-6-sol replaces gpt-5-6-sol, and so on),
embeddings, rerank, OCR, image, audio, realtime, router models, status legacy
or deprecating, and anything retired within 180 days.
Blended price = (3 x input + output) / 4 per 1M tokens.

Picks:
- worker (orchestrator, dev and researcher in one): lowest blended price at AA intel >= 34.
- reviewer: highest AA intel (at least 34) at output <= $15/1M, a different model than
  the worker, from another vendor if one qualifies.
- escalation: if the worker fails at planning, run the orchestrator on the reviewer model.

Output:
1. Table: role | model id | rationale | in/out $/1M, AA intel, AA speed.
2. Table of all chat models with price, AA values, retire date and recommended role.
3. Call out missing prices as "no price" and missing AA data as "no AA data".
```
