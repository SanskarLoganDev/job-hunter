# Companies Tracker

All companies currently monitored by JobHunter.
Config files live in `config/`. Detailed per-ATS lists live in `companies/`.

**Total: 323 Greenhouse + 1 Amazon + 133 Ashby + 44 Lever + 28 SmartRecruiters + 1 Deltek + 1 Google + 2 Eightfold (Microsoft, CBTS) = 533 active company entries**

---

## Per-ATS detail files

| ATS | Count | Detail file | Config file |
|---|---|---|---|
| Amazon | 1 | — | `config/config-amazon.yaml` |
| Greenhouse | 323 | `companies/greenhouse.md` | `config/config-greenhouse.yaml` |
| Ashby | 133 | `companies/ashby.md` | `config/config-ashby.yaml` |
| Lever | 44 | `companies/lever.md` | `config/config-lever.yaml` |
| SmartRecruiters | 28 | `companies/smartrecruiters.md` | `config/config-smartrecruiters.yaml` |
| Deltek | 1 | `companies/deltek.md` | `config/config-deltek.yaml` |
| Google | 1 | — | `config/config-google.yaml` |
| Eightfold | 2 (Microsoft, CBTS) | — | `config/config-eightfold.yaml` |

Note: Workable was removed — too few relevant jobs. `companies/workable.md` kept as reference backlog.
Note: Eightfold is a generic scraper (`scrapers/eightfold.py`) covering any company on the Eightfold AI careers platform, identified by `domain` + `base_url` per company (no slug). Started as Microsoft-only, generalized after CBTS was confirmed to run the identical platform/API. New Eightfold-based companies are a config-only addition.

---

## Adding a new company

1. Find ATS + slug/identifier:
   - Greenhouse: `https://job-boards.greenhouse.io/SLUG`
   - Ashby: `https://jobs.ashbyhq.com/SLUG`
   - Lever: `curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"`
   - SmartRecruiters: `https://careers.smartrecruiters.com/SLUG` — identifier is NOT always the obvious brand name. **Always open in browser to confirm real jobs load** — a search engine hit is not sufficient (stale/defunct boards exist; Skechers was a confirmed example of this).
   - Deltek: fixed tenant (org 2458), no slug — add keywords only
2. Add block to the correct config file with `active: false`
3. Run live test to confirm location strings (see `CLAUDE.md` for commands)
4. Set `active: true`
5. Add to the relevant `companies/*.md` file

---

## Amazon

| Company | Config |
|---|---|
| Amazon | `config/config-amazon.yaml` |

---

## Deltek

| Company | Notes |
|---|---|
| Deltek | Fixed tenant — org 2458, Symphony Talent / m-cloud.io API, Kenexa/BrassRing backend. Scrapes IT + Software Development/Design categories separately (two API calls, deduped by job ID). No slug needed. |
