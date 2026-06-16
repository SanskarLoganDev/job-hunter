# Companies Tracker

All companies currently monitored by JobHunter, organised by ATS platform.
Config files live in `config/`.

**Legend:**
- ✅ Active — being polled every 30 minutes
- ⏸ Inactive — in config but `active: false`
- 🔍 Unverified — slug not browser-confirmed, commented out in config

---

## Amazon (Custom Scraper)

| Company | Status | Config file |
|---|---|---|
| Amazon | ✅ Active | `config/config.yaml` |

---

## Greenhouse

| Company | Slug | Status | Config file |
|---|---|---|---|
| Anthropic | `anthropic` | ✅ Active | `config/config.yaml` |
| Datadog | `datadog` | ✅ Active | `config/config.yaml` |
| Figma | `figma` | ✅ Active | `config/config.yaml` |
| DoorDash | `doordashusa` | ✅ Active | `config/config.yaml` |
| Okta | `okta` | ✅ Active | `config/config.yaml` |
| Affirm | `affirm` | ✅ Active | `config/config.yaml` |
| ZipRecruiter | `ziprecruiter` | ✅ Active | `config/config.yaml` |
| Scale AI | `scaleai` | ✅ Active | `config/config.yaml` |
| Hightouch | `hightouch` | ✅ Active | `config/config.yaml` |
| Glean | `gleanwork` | ✅ Active | `config/config.yaml` |
| Life360 | `life360` | ✅ Active | `config/config.yaml` |
| Xometry | `xometry` | ✅ Active | `config/config.yaml` |
| SmithRx | `smithrx` | ✅ Active | `config/config.yaml` |
| Canonical | `canonical` | ✅ Active | `config/config.yaml` |
| Robinhood | `robinhood` | ✅ Active | `config/config.yaml` |
| Stripe | `stripe` | ✅ Active | `config/config.yaml` |
| Cloudflare | `cloudflare` | ✅ Active | `config/config.yaml` |

---

## Ashby

| Company | Slug | Status | Config file |
|---|---|---|---|
| Cohere | `cohere` | ✅ Active | `config/config-ashby.yaml` |
| Notion | `notion` | ✅ Active | `config/config-ashby.yaml` |
| Airtable | `airtable` | ✅ Active | `config/config-ashby.yaml` |
| Vercel | `vercel` | ✅ Active | `config/config-ashby.yaml` |
| Linear | `linear` | ✅ Active | `config/config-ashby.yaml` |
| Supabase | `supabase` | ✅ Active | `config/config-ashby.yaml` |
| Harvey | `harvey` | ✅ Active | `config/config-ashby.yaml` |
| Luma AI | `lumaai` | ✅ Active | `config/config-ashby.yaml` |
| Benchling | `benchling` | ✅ Active | `config/config-ashby.yaml` |
| Ramp | `ramp` | ✅ Active | `config/config-ashby.yaml` |

---

## Lever

| Company | Slug | Status | Config file |
|---|---|---|---|
| Voleon Group | `voleon` | ✅ Active | `config/config-lever.yaml` |
| NimbleRx | `nimblerx` | ✅ Active | `config/config-lever.yaml` |
| Level AI | `levelai` | ✅ Active | `config/config-lever.yaml` |

---

## To verify an unverified slug

**Greenhouse:** open `https://boards.greenhouse.io/SLUG` or `https://job-boards.greenhouse.io/SLUG`

**Ashby:** open `https://jobs.ashbyhq.com/SLUG`

**Lever:** open `https://jobs.lever.co/SLUG` or run:
```bat
curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"
```
If you get a JSON array back, the slug is correct. Enable in config and mark ✅.

---

## To add a new company

1. Find the ATS and slug (see verification steps above)
2. Add a new block to the relevant config file in `config/`
3. Set `active: false` initially
4. Run live tests to confirm data
5. Set `active: true`
6. Update this file
