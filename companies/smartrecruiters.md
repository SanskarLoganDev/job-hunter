# SmartRecruiters Companies

Full list of companies monitored via the SmartRecruiters ATS.
Config file: `config/config-smartrecruiters.yaml`

API: `GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings`
No authentication required (public Posting API).

**⚠️ companyIdentifier is NOT always the obvious brand name.**
Verify before adding: `https://careers.smartrecruiters.com/{identifier}` or
`https://jobs.smartrecruiters.com/{identifier}`.

**⚠️ A search-engine hit on a careers.smartrecruiters.com URL is NOT sufficient
verification.** It can be a stale or defunct instance that redirects to the
generic SmartRecruiters homepage when actually opened. Always open the URL
directly in a browser and confirm real, current job listings load.
(This happened with "Skechers1" — see Rejected section below.)

**⚠️ The LinkedIn company-page slug does NOT reliably predict the
SmartRecruiters companyIdentifier.** Confirmed by LinkedIn itself: its
`linkedin_username` is `linkedin`, but its real working SmartRecruiters
identifier is `LinkedIn3`. Treat every CamelCase guess below as unverified
until clicked.

---

## Active

| Company | Identifier (slug) | Notes |
|---|---|---|
| Bosch Group | `BoschGroup` | Verified 2026-06-30 — totalFound: 4619 live postings via API. Hardware/automotive/industrial — gets embedded keywords too. |
| Visa | `Visa` | Verified 2026-06-30 by user — careers.smartrecruiters.com/Visa loads real jobs in browser. |
| LinkedIn | `LinkedIn3` | Verified 2026-06-30 by user — careers.smartrecruiters.com/LinkedIn3 loads real jobs in browser. (A second candidate, `LinkedInQA`, was not tested — likely a staging board, discarded.) |

---

## Rejected (do not re-add without solid new evidence)

| Company | Candidate identifier | Why rejected |
|---|---|---|
| Skechers | `Skechers1` | Search snippet showed an indexed page at this URL, but opening it directly just loads the generic SmartRecruiters homepage — not a real Skechers job board. Skechers' actual current career site is on **Workday** (`skechers.wd5.myworkdayjobs.com`), not SmartRecruiters at all. |

---

## Pending verification — batch from SmartRecruiters_users.csv (46 companies)

Source: a CSV of confirmed SmartRecruiters customers (`linkedin_username`,
domain, company name). All 46 entries below (47 minus 1 LinkedIn duplicate,
already active above under `LinkedIn3`) were added to
`config/config-smartrecruiters.yaml` with `active: false` and a CamelCase
slug **guessed** from each company's LinkedIn username. Each yaml block has
a `# TEST THIS URL:` comment — open every one in a browser, confirm real
job listings load, fix the slug if the guess is wrong (or discard if the
company turns out to use a different ATS, same as the Skechers case),
then flip `active: true`.

| Company | LinkedIn slug | Guessed SmartRecruiters slug | Domain |
|---|---|---|---|
| Hardin Design and Development | hardin-design-and-development | `HardinDesignAndDevelopment` | hardindd.com |
| Casebook PBC | casebookpbc | `Casebookpbc` | casebook.net |
| AcuStaf Development Corporation | acustaf-development-corporation | `AcustafDevelopmentCorporation` | acustaf.com |
| Silvaco Inc | silvaco | `Silvaco` | silvaco.com |
| Solvios Technology | solviostech | `Solviostech` | solvios.technology |
| Canyon GBS | canyongbs | `Canyongbs` | canyongbs.com |
| HOS247 | hos247 | `Hos247` | hos247.com |
| Wiser Solutions, Inc. | wiser | `Wiser` | wiser.com |
| Jitterbit | jitterbit | `Jitterbit` | jitterbit.com |
| ALIS by Medtelligent | alis-for-al | `AlisForAl` | go-alis.com |
| BCC Software | bcc-software | `BccSoftware` | bccsoftware.com |
| UNIFY Dots | unifydots | `Unifydots` | unifydots.com |
| Campfire Interactive | campfire-interactive | `CampfireInteractive` | campfire-interactive.com |
| Skyward | skyward | `Skyward` | skyward.com |
| Order.co | order-company | `OrderCompany` | order.co |
| IntegriChain | integrichain | `Integrichain` | integrichain.com |
| Redica Systems | redicasystems | `Redicasystems` | redica.com |
| HAMMOQ Inc. | hammoq | `Hammoq` | hammoq.com |
| Hirevue | hirevue | `Hirevue` | hirevue.com |
| Momentus Technologies | momentustechnologies | `Momentustechnologies` | gomomentus.com |
| Intelerad | intelerad | `Intelerad` | intelerad.com |
| The Linux Foundation | the-linux-foundation | `TheLinuxFoundation` | linuxfoundation.org |
| insightsoftware | outcomes-by-insightsoftware | `OutcomesByInsightsoftware` | insightsoftware.com |
| Mirantis | mirantis | `Mirantis` | mirantis.com |
| Sitecore ⚠️ | sitecore | `Sitecore` | sitecore.com — **already active in config-ashby.yaml**, check for duplicate before activating here |
| Zen Planner | zen-planner | `ZenPlanner` | zenplanner.com |
| BigCommerce | bigcommerce | `Bigcommerce` | bigcommerce.com |
| Cricut | cricut | `Cricut` | cricut.com |
| Dataiku | dataiku | `Dataiku` | dataiku.com |
| Docusign | docusign | `Docusign` | docusign.com |
| Fiverr | fiverr-com | `FiverrCom` | fiverr.com |
| Flywire | flywire | `Flywire` | flywire.com |
| Freshworks | freshworks-inc | `FreshworksInc` | freshworks.com |
| Kaseya | kaseya | `Kaseya` | kaseya.com |
| Mindtickle | mindtickle | `Mindtickle` | mindtickle.com |
| New Relic | new-relic-inc- | `NewRelicInc` | newrelic.com |
| NextGen Healthcare | nextgenhealthcareinc | `Nextgenhealthcareinc` | nextgen.com |
| Palantir Technologies | palantir-technologies | `PalantirTechnologies` | palantir.com |
| SeekOut | seek0ut | `Seek0ut` | seekout.com |
| ServiceNow | servicenow | `Servicenow` | servicenow.com |
| ServiceTitan | servicetitan | `Servicetitan` | servicetitan.com |
| Socure | socure | `Socure` | socure.com |
| SolarWinds | solarwinds | `Solarwinds` | solarwinds.com |
| Nielsen | nielsen | `Nielsen` | nielsen.com |
| Upwork | upwork | `Upwork` | upwork.com |
| Workato | workato | `Workato` | workato.com |

(LinkedIn itself, linkedin_username `linkedin`, was in the source CSV too —
skipped here since it's a likely duplicate of the already-active `LinkedIn3`
entry above.)

---

## Adding a new company

1. Guess the identifier (usually CamelCase brand name, sometimes with suffixes/numbers — e.g. `BoschGroup`, `LinkedIn3`).
2. **Open `https://careers.smartrecruiters.com/{identifier}` directly in a browser** — confirm real, current job listings load (not a redirect to the generic homepage, not an empty/stale page). A search engine showing the URL is not enough on its own.
3. Double check via API directly: `https://api.smartrecruiters.com/v1/companies/{identifier}/postings/` — should return `totalFound` > 0.
4. Add to `config/config-smartrecruiters.yaml` with `active: false` first if not 100% confirmed.
5. Set `active: true` once verified in browser.
6. Update this file + `companies.md` summary counts.

## Notes

- Two-step fetch required: list endpoint only returns an API `ref` URL, not a human clickable link. Scraper fetches the detail endpoint (`postingUrl`) per matching job — capped via `detail_fetch_limit`, same pattern as the Amazon scraper.
- Rate limit per SmartRecruiters docs: 2 req/sec, 8 concurrent max. Scraper's built-in sleeps stay well under this.
- Many SmartRecruiters customers are non-tech (retail, healthcare, logistics, manufacturing) — same curation discipline needed as the Greenhouse list, not a blind bulk-add.
- Multiple candidate identifiers can exist for one brand (regional boards, business units, test/staging instances, or stale/defunct ones) — when search turns up more than one, or even just one, verify by opening it directly before trusting it.
- A company can have *some* historical SmartRecruiters presence indexed by search engines while their actual current hiring pipeline has moved to a different ATS entirely (e.g. Skechers → Workday). Browser verification catches this; search snippets alone do not.
- LinkedIn company-page slugs do not reliably predict SmartRecruiters companyIdentifiers — they're different systems maintained independently by each company's HR/recruiting team.
