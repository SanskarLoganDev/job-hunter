# Companies Tracker

All companies currently monitored by JobHunter, organised by ATS platform.
Config files live in `config/`.

**Total active: 101 Greenhouse + 1 Amazon + 93 Ashby + 9 Lever = 204 companies**

**Legend:**
- ✅ Active — being polled every 30 minutes
- ⏸ Inactive — in config but `active: false`
- 🔍 Unverified — slug not confirmed, commented out in config

---

## Amazon (1)

Config: `config/config-amazon.yaml`

| Company | Status |
|---|---|
| Amazon | ✅ Active |

---

## Greenhouse (101)

Config: `config/config-greenhouse.yaml` — slugs verified from ATS_Company_Directory.xlsx.
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
| ClickHouse (GH) | `clickhouse` |
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

## Ashby (93)

Config: `config/config-ashby.yaml` — all slugs verified from jobs.ashbyhq.com URLs.
Every company has the full keyword set including `ai engineer` and `ml engineer`.

Note: ClickHouse appears on both Greenhouse and Ashby — both are active.
Plaid confirmed on Ashby (slug `plaid`) — removed from Lever backlog.
Miro confirmed on Ashby (slug `miro`) — removed from Lever backlog.
OpenAI confirmed on Ashby (slug `openai`) — removed from Lever backlog.
Amplitude confirmed on Ashby (slug `amplitude`) — removed from Lever backlog.

### Original (10)

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

### Tech / Software

| Company | Slug |
|---|---|
| Snowflake | `snowflake` |
| Miro | `miro` |
| Sitecore | `sitecore` |
| DDN | `ddn` |
| Gainsight | `gainsight` |
| Tekion Corp | `tekion` |
| Amplify | `amplify` |
| Thumbtack | `thumbtack` |
| Redis | `redis` |
| Instructure | `instructure` |
| ClickUp | `clickup` |
| Kayak | `kayak` |
| Centerfield | `centerfield` |
| Sequoia | `sequoia` |
| Confluent | `confluent` |
| Netgear | `netgear` |
| UiPath | `uipath` |
| Boomi | `boomi` |
| Commure | `commure` |
| Delinea | `delinea` |
| Juniper Square | `junipersquare` |
| Perk | `perk` |
| SurveyMonkey | `surveymonkey` |
| Vanta | `vanta` |
| ClickHouse (Ashby) | `clickhouse` |
| WebFX | `webfx` |
| Recharge | `recharge` |
| Headway | `headway` |
| Quantcast | `quantcast` |
| 3E | `3e` |
| Teamworks | `teamworks` |
| ScienceLogic | `sciencelogic` |
| Nexxen | `nexxen` |
| Demandbase | `demandbase` |
| MeridianLink | `meridianlink` |
| Preply | `preply` |
| Payscale | `payscale` |
| Solvd | `solvd` |
| Drata | `drata` |
| Amplitude | `amplitude` |
| Foursquare | `foursquare` |
| Kong | `kong` |
| OpenGov | `opengov` |
| Handshake | `handshake` |
| Tarro | `tarro` |
| AuditBoard | `auditboard` |
| Docker | `docker` |
| Fullstory | `fullstory` |
| LaunchDarkly | `launchdarkly` |
| Mapbox | `mapbox` |
| Mural | `mural` |
| Velocity Global | `pebl` |
| Plaid | `plaid` |
| project44 | `project44` |
| Revinate | `revinate` |
| Salesloft | `salesloft` |
| Weave | `weave` |
| Zapier | `zapier` |
| Zip | `zip` |

### AI / ML

| Company | Slug |
|---|---|
| OpenAI | `openai` |
| Applied Intuition | `applied` |
| Saronic Technologies | `saronic` |
| Crusoe | `crusoe` |
| Cerebras | `cerebras` |
| Lambda | `lambda` |
| Avala AI | `avala` |

### Fintech

| Company | Slug |
|---|---|
| Kraken (Ashby) | — |
| SpotOn | `spoton` |
| Rokt | `rokt` |
| Socure | `socure` |
| Stout | `stout` |
| Chartis | `chartis` |

### Healthcare

| Company | Slug |
|---|---|
| Inovalon | `inovalon` |
| Hinge Health | `hinge-health` |
| Virta Health | `virtahealth` |
| Whoop | `whoop` |
| OpenLoop Health | `openloophealth` |
| Talkiatry | `talkiatry` |

### Other

| Company | Slug |
|---|---|
| Shield AI | `shield-ai` |
| Angi | `angi` |
| Rothy's | `rothys` |
| Bumble | `bumble` |
| Niantic | `niantic` |
| Lime | `lime` |

---

## Lever (9)

Config: `config/config-lever.yaml` — all slugs verified from jobs.lever.co URLs.

| Company | Slug | Category |
|---|---|---|
| Voleon Group | `voleon` | Finance / Quant |
| NimbleRx | `nimblerx` | Healthcare |
| Level AI | `levelai` | AI / ML |
| LinkedIn | `linkedin` | Tech / Software |
| Palantir | `palantir` | AI / ML |
| KPMG | `kpmg` | Consulting |
| Kraken | `kraken` | Fintech |
| Rackspace | `rackspace` | Cloud / Tech |
| Zeta Tech | `zeta` | Fintech |


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
