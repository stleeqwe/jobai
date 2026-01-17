---
name: crawler-maintenance
description: Maintains JobKorea crawler selectors and parsing logic. Use when crawler returns empty results, wrong data, or HTML structure changes detected.
tools: Read, Grep, Glob, Bash
---

# Crawler Maintenance

## Instructions

1. **Verify current selectors work**
   ```bash
   cd crawler && python -c "
   import httpx
   from bs4 import BeautifulSoup
   resp = httpx.get('https://www.jobkorea.co.kr/recruit/joblist')
   soup = BeautifulSoup(resp.text, 'html.parser')
   items = soup.select('li.devloopArea')
   print(f'Found {len(items)} job items')
   "
   ```

2. **Check for HTML structure changes**
   - Inspect JobKorea page manually
   - Compare with current selectors in `crawler/app/scrapers/jobkorea_v2.py`

3. **Update selectors if needed**

## Current Valid Selectors (as of 2026-01)

```python
# Job list items - MUST use "li.devloopArea" not ".devloopArea"
job_items = soup.select("li.devloopArea")
if not job_items:
    job_items = soup.select("li[data-info]")  # fallback

# Title
title_el = item.select_one(".description a .text")

# Company name
company_el = item.select_one(".company .name a")

# Job ID extraction from data-info attribute
data_info = item.get("data-info", "")
parts = data_info.strip().split("|")
job_id = parts[0] if parts and parts[0].isdigit() else None
```

## Selector Issue History

| Date | Issue | Fix |
|------|-------|-----|
| 2026-01-12 | `.devloopArea` returned 702 (wrong) | Changed to `li.devloopArea` (642 correct) |

## Crawling Performance Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Workers | 2 | Page-level parallelism |
| Detail parallel | 5 | Batch parallel calls |
| Batch delay | 0.8-1.2s | Anti-blocking |
| 30-day filter | Check `posted_at` first | Skip old job parsing |

## Debugging

```python
# Test single detail page parsing
from app.scrapers.jobkorea import parse_job_detail
result = await parse_job_detail("job_id_here")
print(result)
```

## Seoul-only Filter

Only save jobs where `location_sido == "서울"`. This is MVP scope.
