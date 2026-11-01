# Companies Tracker

All companies currently monitored by JobHunter.
Config files live in `config/`. Detailed per-ATS lists live in `companies/`.

**Total: 327 Greenhouse + 1 Amazon + 136 Ashby + 46 Lever + 28 SmartRecruiters + 1 Deltek + 1 Google + 2 Eightfold (Microsoft, CBTS) + 1 Infosys + 5 TalentBrew/Radancy + 1 Zwayam/Openings.co + 1 SAP SuccessFactors = 550 active company entries**

---

## Per-ATS detail files

| ATS | Count | Detail file | Config file |
|---|---|---|---|
| Amazon | 1 | — | `config/config-amazon.yaml` |
| Greenhouse | 327 | `companies/greenhouse.md` | `config/config-greenhouse.yaml` |
| Ashby | 136 | `companies/ashby.md` | `config/config-ashby.yaml` |
| Lever | 46 | `companies/lever.md` | `config/config-lever.yaml` |
| SmartRecruiters | 28 | `companies/smartrecruiters.md` | `config/config-smartrecruiters.yaml` |
| Deltek | 1 | `companies/deltek.md` | `config/config-deltek.yaml` |
| Google | 1 | — | `config/config-google.yaml` |
| Eightfold | 2 (Microsoft, CBTS) | — | `config/config-eightfold.yaml` |
| Infosys | 1 | `companies/infosys.md` | `config/config-infosys.yaml` |
| TalentBrew/Radancy | 5 | `companies/talentbrew.md` | `config/config-talentbrew.yaml` |
| Zwayam/Openings.co | 1 | `companies/zwayam.md` | `config/config-zwayam.yaml` |
| SAP SuccessFactors | 1 (Wipro) | `companies/successfactors.md` | `config/config-successfactors.yaml` |

Note: Workable was removed — too few relevant jobs. `companies/workable.md` kept as reference backlog.
Note: Eightfold is a generic scraper (`scrapers/eightfold.py`) covering any company on the Eightfold AI careers platform, identified by `domain` + `base_url` per company (no slug). Started as Microsoft-only, generalized after CBTS was confirmed to run the identical platform/API. New Eightfold-based companies are a config-only addition.
Note: Infosys uses a custom Digital Careers HTML scraper. Its public pages do not expose a reliable posted date, so alerts are based on newly discovered requisition IDs after the initial baseline is stored in SQLite.
Note: TalentBrew/Radancy is a generic HTML scraper for legacy `.search-results__job-title-link` rows and newer `#search-results-list` rows. Some newer boards expose posted dates only on detail pages, so the scraper has a capped detail-date fallback.
Note: Zwayam/Openings.co is a generic API scraper for Angular career sites backed by `public.zwayam.com`. Impetus uses this platform.
Note: SAP SuccessFactors currently covers Wipro with a 10-day posting window and an extra `ai developer` keyword. US-first/worldwide date-sorted listing scans are bounded by page/time budgets and preserve explicitly labelled international remote roles. See its detail file for the disclosed robots.txt restriction and partial-coverage limitations.

---

## Adding a new company

1. Find ATS + slug/identifier:
   - Greenhouse: `https://job-boards.greenhouse.io/SLUG`
   - Ashby: `https://jobs.ashbyhq.com/SLUG`
   - Lever: `curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"`
   - SmartRecruiters: `https://careers.smartrecruiters.com/SLUG` — identifier is NOT always the obvious brand name. **Always open in browser to confirm real jobs load** — a search engine hit is not sufficient (stale/defunct boards exist; Skechers was a confirmed example of this).
   - Deltek: fixed tenant (org 2458), no slug — add keywords only
   - Infosys: custom single-company scraper in `scrapers/infosys.py`
   - TalentBrew/Radancy: verify the page renders parseable `#search-results-list` rows, location, and either listing/detail posted dates; configure `base_url`, `search_path`, and filters
   - Zwayam/Openings.co: identify `domain`, `company_id`, `tenant_group_id`, and optional path prefix from the career site bundle/API
   - SAP SuccessFactors: verify the tenant's `/services/recruiting/v1/jobs` endpoint, date sorting, schema, and access policy; configure `base_url` and pagination/runtime budgets
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
