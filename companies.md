# Companies Tracker

All companies currently monitored by JobHunter.
Config files live in `config/`. Detailed per-ATS lists live in `companies/`.

**Total: ~199 Greenhouse + 1 Amazon + 104 Ashby + 36 Lever = ~340 companies**

---

## Per-ATS detail files

| ATS | Count | Detail file | Config file |
|---|---|---|---|
| Amazon | 1 | — | `config/config-amazon.yaml` |
| Greenhouse | 199 | `companies/greenhouse.md` | `config/config-greenhouse.yaml` |
| Ashby | 104 | `companies/ashby.md` | `config/config-ashby.yaml` |
| Lever | 36 | `companies/lever.md` | `config/config-lever.yaml` |

Note: Workable was removed — too few relevant jobs. `companies/workable.md` kept as reference backlog.

---

## Adding a new company

1. Find ATS + slug:
   - Greenhouse: `https://job-boards.greenhouse.io/SLUG`
   - Ashby: `https://jobs.ashbyhq.com/SLUG`
   - Lever: `curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"`
2. Add block to the correct config file with `active: false`
3. Run live test to confirm location strings (see `CLAUDE.md` for commands)
4. Set `active: true`
5. Add to the relevant `companies/*.md` file

---

## Amazon

| Company | Config |
|---|---|
| Amazon | `config/config-amazon.yaml` |
