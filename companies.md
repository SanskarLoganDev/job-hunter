# Companies Tracker

All companies currently monitored by JobHunter.
Config files live in `config/`. Detailed per-ATS lists live in `companies/`.

**Total active: 196 Greenhouse + 1 Amazon + 97 Ashby + 34 Lever = 328 companies**

---

## Per-ATS detail files

| ATS | Companies | Detail file | Config file |
|---|---|---|---|
| Amazon | 1 | — | `config/config-amazon.yaml` |
| Greenhouse | 196 | `companies/greenhouse.md` | `config/config-greenhouse.yaml` |
| Ashby | 97 | `companies/ashby.md` | `config/config-ashby.yaml` |
| Lever | 34 | `companies/lever.md` | `config/config-lever.yaml` |
| Workable | coming soon | `companies/workable.md` | `config/config-workable.yaml` |

---

## Adding a new company

1. Find ATS + slug:
   - Greenhouse: `https://job-boards.greenhouse.io/SLUG`
   - Ashby: `https://jobs.ashbyhq.com/SLUG`
   - Lever: `curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"`
   - Workable: `https://apply.workable.com/SLUG`
2. Add block to the correct config file with `active: false`
3. Run live test to confirm location strings
4. Set `active: true`
5. Add to the relevant `companies/*.md` file

---

## Amazon

| Company | Config |
|---|---|
| Amazon | `config/config-amazon.yaml` |
