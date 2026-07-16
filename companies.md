# Companies Tracker

All companies currently monitored by JobHunter.
Config files live in `config/`. Detailed per-ATS lists live in `companies/`.

**Total: ~199 Greenhouse + 1 Amazon + 107 Ashby + 38 Lever + 3 SmartRecruiters (active) + 1 Deltek = ~349 companies active**
**(+46 SmartRecruiters companies pending slug verification, not yet active — see companies/smartrecruiters.md)**

---

## Per-ATS detail files

| ATS | Count | Detail file | Config file |
|---|---|---|---|
| Amazon | 1 | — | `config/config-amazon.yaml` |
| Greenhouse | 199 | `companies/greenhouse.md` | `config/config-greenhouse.yaml` |
| Ashby | 107 | `companies/ashby.md` | `config/config-ashby.yaml` |
| Lever | 38 | `companies/lever.md` | `config/config-lever.yaml` |
| SmartRecruiters | 3 active (+46 pending) | `companies/smartrecruiters.md` | `config/config-smartrecruiters.yaml` |
| Deltek | 1 | `companies/deltek.md` | `config/config-deltek.yaml` |

Note: Workable was removed — too few relevant jobs. `companies/workable.md` kept as reference backlog.

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
