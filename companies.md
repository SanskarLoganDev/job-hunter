# Companies Tracker

All companies currently monitored by JobHunter, organised by ATS platform.
Config files live in `config/`.

**Total active: 101 Greenhouse + 1 Amazon + 10 Ashby + 3 Lever = 115 companies**

**Legend:**
- ✅ Active — being polled every 30 minutes
- ⏸ Inactive — in config but `active: false`
- 🔍 Unverified — slug not confirmed, commented out in config

---

## Amazon

Config: `config/config-amazon.yaml`

| Company | Status |
|---|---|
| Amazon | ✅ Active |

---

## Greenhouse (101 companies)

Config: `config/config.yaml` — slugs verified from ATS_Company_Directory.xlsx.
Every company has the full keyword set including `ai engineer` and `ml engineer`.

### Tech / Software

| Company | Slug |
|---|---|
| Anthropic | `anthropic` |
| Datadog | `datadog` |
| Figma | `figma` |
| DoorDash | `doordashusa` |
| Okta | `okta` |
| Affirm | `affirm` |
| ZipRecruiter | `ziprecruiter` |
| Scale AI | `scaleai` |
| Hightouch | `hightouch` |
| Glean | `gleanwork` |
| Life360 | `life360` |
| Xometry | `xometry` |
| SmithRx | `smithrx` |
| Canonical | `canonical` |
| Robinhood | `robinhood` |
| Stripe | `stripe` |
| Cloudflare | `cloudflare` |
| Databricks | `databricks` |
| MongoDB | `mongodb` |
| Samsara | `samsara` |
| Asana | `asana` |
| GitLab | `gitlab` |
| Braze | `braze` |
| HubSpot | `hubspotjobs` |
| Klaviyo | `klaviyo` |
| Twilio | `twilio` |
| Box | `boxinc` |
| DigitalOcean | `digitalocean98` |
| JetBrains | `jetbrains` |
| Dropbox | `dropbox` |
| Workato | `workato` |
| Instacart | `instacart` |
| Fivetran | `fivetran` |
| ClickHouse | `clickhouse` |
| Harness | `harnessinc` |
| Postman | `postman` |
| New Relic | `newrelic` |
| Wiz | `wizinc` |
| Zscaler | `zscaler` |
| Verkada | `verkada` |
| Tenstorrent | `tenstorrent` |
| Elastic | `elastic` |
| Dialpad | `dialpad` |
| MaintainX | `maintainx` |
| DoiT | `doitintl` |
| Celonis | `celonis` |
| Roku | `roku` |
| Reddit | `reddit` |
| SentinelOne | `sentinellabs` |
| Axon | `axon` |
| IonQ | `ionq` |
| Airbnb | `airbnb` |
| Astera Labs | `asteralabs` |
| Oscar Health | `oscar` |
| Spring Health | `springhealth66` |

### AI / ML

| Company | Slug |
|---|---|
| xAI | `xai` |
| CoreWeave | `coreweave` |
| Waymo | `waymo` |
| AlphaSense | `alphasense` |
| Aurora Innovation | `aurorainnovation` |
| Nebius | `nebius` |
| Zipline | `flyzipline` |
| Wayve | `wayve` |
| Nuro | `nuro` |
| Motional | `motional` |
| Graphcore | `graphcore` |
| Speechify | `speechify` |

### Fintech

| Company | Slug |
|---|---|
| Coinbase | `coinbase` |
| Brex | `brex` |
| SoFi | `sofi` |
| Navan | `tripactions` |
| Block | `block` |
| Adyen | `adyen` |
| Addepar | `addepar1` |
| Ripple | `ripple` |
| Lyft | `lyft` |
| Nubank | `nubank` |
| Payoneer | `payoneer` |
| Jane Street | `janestreet` |
| DRW | `drweng` |
| OKX | `okx` |

### E-Commerce / Marketplace

| Company | Slug |
|---|---|
| Coupang | `coupang` |
| HelloFresh | `hellofresh` |
| Agoda | `agoda` |

### Gaming

| Company | Slug |
|---|---|
| Roblox | `roblox` |
| Epic Games | `epicgames` |
| 2K Games | `2k` |
| Scopely | `scopely` |
| PlayStation Global | `sonyinteractiveentertainmentglobal` |

### Media / Content

| Company | Slug |
|---|---|
| Pinterest | `pinterest` |
| The New York Times | `thenewyorktimes` |

### Defense / Aerospace

| Company | Slug |
|---|---|
| SpaceX | `spacex` |
| Anduril Industries | `andurilindustries` |
| Rocket Lab | `rocketlab` |
| Relativity Space | `relativity` |
| Archer Aviation | `archer56` |
| K2 Space | `k2spacecorporation` |
| Astranis | `astranis` |
| Vast | `vast` |

### Healthcare

| Company | Slug |
|---|---|
| Natera | `natera` |
| One Medical | `onemedical` |

### Other

| Company | Slug |
|---|---|
| Lucid Motors | `lucidmotors` |
| On Running | `onrunning` |
| Nscale | `nscaleoperationsukltd` |

---

## Ashby (10 companies)

Config: `config/config-ashby.yaml`

| Company | Slug |
|---|---|
| Cohere | `cohere` |
| Notion | `notion` |
| Airtable | `airtable` |
| Vercel | `vercel` |
| Linear | `linear` |
| Supabase | `supabase` |
| Harvey | `harvey` |
| Luma AI | `lumaai` |
| Benchling | `benchling` |
| Ramp | `ramp` |

---

## Lever (3 active + backlog)

Config: `config/config-lever.yaml`

| Company | Slug | Status |
|---|---|---|
| Voleon Group | `voleon` | ✅ Active |
| NimbleRx | `nimblerx` | ✅ Active |
| Level AI | `levelai` | ✅ Active |

### Lever backlog — from ATS_Company_Directory.xlsx (verify slug then add)

| Company | Slug |
|---|---|
| Netflix | `netflix` |
| Shopify | `shopify` |
| LinkedIn | `linkedin` |
| Palantir | `palantir` |
| Discord | `discord` |
| Duolingo | `duolingo` |
| GitHub | `github` |
| Gusto | `gusto` |
| HashiCorp | `hashicorp` |
| Intercom | `intercom` |
| Loom | `loom` |
| Miro | `miro` |
| OpenAI | `openai` |
| Plaid | `plaid` |
| Replit | `replit` |
| Rubrik | `rubrik` |
| Snyk | `snyk` |
| Webflow | `webflow` |
| Zendesk | `zendesk` |
| Carta | `carta` |
| Chime | `chime` |
| Coursera | `coursera` |
| Klarna | `klarna` |
| Amplitude | `amplitude` |

---

## To verify a slug

**Greenhouse:** open `https://job-boards.greenhouse.io/SLUG`

**Ashby:** open `https://jobs.ashbyhq.com/SLUG`

**Lever:** `curl "https://api.lever.co/v0/postings/SLUG?mode=json&limit=1"`

## To add a new company

1. Find ATS + slug
2. Add block to correct config file with `active: false`
3. Run live test to see real location strings
4. Tune `locations` list
5. Set `active: true`
6. Update this file
