# Workable Companies

All companies monitored via the Workable public widget API.
Scraper: `scrapers/workable.py`
Config: `config/config-workable.yaml`
API endpoint: `https://apply.workable.com/api/v1/widget/accounts/{slug}`

**To verify a slug:** open `https://apply.workable.com/{SLUG}` in browser.

**Location filtering advantage over Greenhouse:**
Workable returns structured `country_code`, `city`, `region` fields separately.
Use `locations: [US, Remote]` to match all US + remote roles precisely.
No substring guessing needed.

**Total: 1 company (1 pending live test)**

| Company | Slug | Status |
|---|---|---|
| Typeform | `typeform` | ⏸ Pending live test |

### Workable backlog — companies to verify

| Company | Slug to check |
|---|---|
| Intercom | `intercom` |
| Discord | `discord` |
| Netlify | `netlify` |
