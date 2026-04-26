---
name: export
description: Export polyrouter stats as CSV (summary) or JSON (record arrays) for pandas / Excel / jq
user_invokable: true
---

<!-- POLY:EXPORT:v1 -->
# /polyrouter:export Command

Exports the lifetime stats tracked in `~/.claude/polyrouter-stats.json`
to a portable file format for downstream analysis.

## Usage

```
/polyrouter:export csv                  # → /tmp/polyrouter-export-YYYYMMDD-HHMMSS.csv
/polyrouter:export json                 # → /tmp/polyrouter-export-YYYYMMDD-HHMMSS.json
/polyrouter:export csv ./my-routes.csv  # explicit path override
/polyrouter:export json ~/data/poly.json
```

## Behavior

Run the runner script with the format and (optional) path:

```bash
python3 scripts/poly-export.py <csv|json> [output_path]
```

If `~/.claude/polyrouter-stats.json` does not exist, the script exits with
code 2 and prints `route some queries first` — surface that message to
the user verbatim.

## Output shape

### CSV — long-format summary (one row per dimension)

Three columns: `dimension`, `key`, `value`.

```
dimension,key,value
summary,version,1.0
summary,total_queries,1702
summary,cache_hits,699
summary,estimated_savings,50.2533
summary,last_updated,2026-04-26T07:42:39.932770
routes,fast,935
routes,standard,257
routes,deep,510
languages,en,269
languages,es,1192
session,2026-04-02.queries,24
session,2026-04-02.cache_hits,18
session,2026-04-02.savings,0.704
session,2026-04-02.routes.fast,16
...
```

Stays flat regardless of how many tiers / languages / sessions accumulate
— ideal for `awk`, Excel pivot tables, or `pandas.read_csv()` followed by
`pivot()` to reshape per analysis.

### JSON — record arrays (pandas / jq friendly)

```json
{
  "summary": {
    "version": "1.0",
    "total_queries": 1702,
    "cache_hits": 699,
    "estimated_savings": 50.2533,
    "last_updated": "2026-04-26T07:42:39.932770"
  },
  "routes":     [{"tier": "fast", "count": 935}, ...],
  "languages":  [{"language": "en", "count": 269}, ...],
  "sessions":   [{"date": "2026-04-02", "queries": 24, "cache_hits": 18,
                  "savings": 0.704, "routes_fast": 16, "routes_standard": 0,
                  "routes_deep": 8}, ...]
}
```

Each list-of-records is a clean `pandas.DataFrame()` source. Session
records flatten the nested `routes` dict into `routes_<tier>` columns so
every record shares the same key set (DataFrame requirement).

## Why two formats

- **CSV** — universal interchange (Excel, Google Sheets, R, BI tools).
  Long format keeps the header stable when polyrouter adds new tiers.
- **JSON** — preserves numeric types (no string coercion), supports
  Unicode language codes natively (`ensure_ascii=False`), and round-trips
  cleanly through `pandas.read_json()` and `jq`.
