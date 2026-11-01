# SAP SuccessFactors Companies

Scraper: `scrapers/successfactors.py`  
Config: `config/config-successfactors.yaml`

| Company | Careers site | Posting window |
|---|---|---|
| Wipro | [Search jobs](https://careers.wipro.com/search/) | 10 days |

## Implementation and operating limits

- Uses `POST {base_url}/services/recruiting/v1/jobs`, with `sortBy: date`,
  `locale: en_US`, and zero-based `pageNumber`. The verified endpoint returns
  10 rows per page plus `totalJobs`; `pageSize: 100` did not increase that size.
- Each row's `response` contains `id`, `unifiedUrlTitle`,
  `unifiedStandardTitle`, `unifiedStandardStart`, `unifiedStandardEnd`,
  `jobLocationShort`, and `jobLocationCountry`. Missing end dates are allowed.
- `unifiedStandardStart` is the posting date, not a last-modified date.
  Dates have no time-of-day; the entire UTC date 10 days before today is
  included. Unknown dates, future postings, and expired jobs are excluded.
- Fetches US first, then worldwide to keep explicitly labelled international
  remote jobs. All returned offices are retained. Remote status is not guessed
  from country or title, and remote jobs labelled only inside a JD may be missed.
- Shared keywords/seniority/location filters apply locally. Wipro additionally
  matches `ai developer`; other companies' keyword and age settings are unchanged.
- No per-job detail requests. Stable IDs deduplicate the current scan across
  pages/scopes; the existing URL-based SQLite dedup handles repeat notifications.
- A fully old page stops pagination only while observed dates remain complete
  and newest-first. Unsorted/missing dates disable this optimization. Repeated
  pages, premature empty pages, HTTP/schema failures, and runtime/page limits
  generate warnings/errors; partial scans are not advertised as complete.
- Config caps each scope at 200 pages and the whole scrape at a 120-second
  budget, with 0.2 seconds between requests. Request timeouts are limited by the
  remaining budget. Coverage can be partial on a busy board or slow connection;
  check the log before increasing limits. A response still in flight can delay
  exit beyond the nominal budget because Requests timeouts are not wall-clock
  deadlines.

## Access policy

Wipro's [robots.txt](https://careers.wipro.com/robots.txt) disallows `/services/`.
The owner explicitly requested scheduled polling after this was disclosed, so
the config is active. That direction is not permission from Wipro. Review the
site's automation terms/permission before broader deployment. No login, access
control bypass, CAPTCHA solving, or retries around blocks are implemented.

Other SuccessFactors sites must be verified individually; sharing the ATS name
does not guarantee this endpoint or response format is available.

## Verification (November 1, 2026)

A direct, read-only scraper preview using the actual YAML settings completed the
US date-window scan and found 8 matching roles, including the linked Junior
Forward Deployed Engineer (160017). The April AI Developer example (159939) was
excluded. The worldwide scan hit the shared 120-second budget: 207 pages fetched
in 120.1 seconds across both scopes. International remote coverage was partial;
do not interpret an empty remote result as proof that no remote openings exist.
The preview did not open SQLite or send emails.
