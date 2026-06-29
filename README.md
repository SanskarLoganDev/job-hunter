# JobHunter

> **Personal automated job alert system** — scrapes ATS job boards directly via public APIs and emails new matching roles every hour. No third-party job boards, no aggregator lag.

Built initially as **HustleHUB – JobWatch** at a hackathon (local FastAPI + Amazon scraper), then evolved into a full multi-ATS polling engine running on Windows Task Scheduler.

---

## Team (Hackathon)

Abhigna Kandala · Krishnendra Tomar · Heena Khan · Sanskar Vidyarthi

---

## Problem

Targeted job hunting is tedious: you must repeatedly check specific companies' career pages, apply keyword filters, and figure out which postings are actually **new**. Job boards like LinkedIn add noise and lag — many companies publish roles on their own ATS first, hours or days before aggregators pick them up.

---

## Solution

Poll ATS APIs directly at the source, every hour. The moment a recruiter publishes a job in Greenhouse, Ashby, or Lever, it hits your inbox — not LinkedIn's crawl queue.

- **~345 companies** monitored across Amazon, Greenhouse, Ashby, and Lever
- **Keyword filtering** — only roles matching your target titles
- **Seniority filtering** — excludes senior/staff/principal/lead/director/manager
- **Location filtering** — US only (remote + office)
- **Deduplication** — same job never emailed twice (SQLite uid store)
- **Email alerts** — clean HTML table, sorted newest-first, sent to Gmail

---

## Architecture (Local / Windows)

```
Windows Task Scheduler (every hour)
  └─► run_poller.bat
        └─► python poller.py
              ├─ loads all config/config-*.yaml
              ├─ for each active company (~345):
              │    ├─ scraper hits ATS public API → List[Job]
              │    ├─ store.filter_new() → diff vs seen_jobs in SQLite
              │    ├─ if new: send HTML email via Gmail SMTP
              │    └─ store.mark_seen() → save uid to DB
              └─ exits (one-shot, not a daemon)

ATS APIs (all public, no auth required):
  Amazon    → amazon.jobs/en/search.json
  Greenhouse → boards-api.greenhouse.io/v1/boards/{slug}/jobs
  Ashby     → api.ashbyhq.com/posting-api/job-board/{slug}
  Lever     → api.lever.co/v0/postings/{slug}?mode=json
```

---

## Architecture (Cloud / GCP — Hackathon)

Built and demoed at the hackathon: **Cloud Scheduler → Cloud Function (HTTP, 2nd gen) → Gmail SMTP**

```
         (every 10 minutes)
 Cloud Scheduler  ──────────────▶  Cloud Functions (2nd gen, HTTP)
                                        │
                                        │  requests + BeautifulSoup
                                        ▼
                                   Company Sites (amazon.jobs)
                                        │
                                        ▼
                              SMTP (Gmail App Password)
                                   Email summary

         ┌─────────────────────────────────────────┐
         │ Firestore (Datastore mode) — optional   │
         │   • Store companies & settings          │
         │   • Function reads/filters by "active"  │
         └─────────────────────────────────────────┘

         ┌─────────────────────────────────────────┐
         │ Secret Manager                          │
         │   • SMTP_USER / SMTP_PASS               │
         │   • SMTP_HOST / SMTP_PORT               │
         │   • RECIPIENT_EMAIL                     │
         └─────────────────────────────────────────┘
```

### One-Time Cloud Setup

> Replace `$PROJECT_ID` and `$REGION` (e.g. `us-central1`). Run in Cloud Shell or with `gcloud`.

```bash
# 1. Enable APIs
gcloud config set project $PROJECT_ID
gcloud services enable cloudfunctions.googleapis.com cloudscheduler.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com

# 2. (Optional) Firestore
gcloud firestore databases create --region=$REGION

# 3. Store secrets
echo -n "yourname@gmail.com"   | gcloud secrets create SMTP_USER --data-file=-
echo -n "abcd efgh ijkl mnop"  | gcloud secrets create SMTP_PASS --data-file=-
echo -n "smtp.gmail.com"       | gcloud secrets create SMTP_HOST --data-file=-
echo -n "587"                  | gcloud secrets create SMTP_PORT --data-file=-
echo -n "you@example.com"      | gcloud secrets create RECIPIENT_EMAIL --data-file=-

# 4. Deploy function
gcloud functions deploy jobwatch-scan \
  --gen2 \
  --runtime=python312 \
  --region=$REGION \
  --entry-point=scan_jobs_test \
  --trigger-http \
  --allow-unauthenticated=false \
  --set-secrets=SMTP_USER=SMTP_USER:latest,SMTP_PASS=SMTP_PASS:latest,\
SMTP_HOST=SMTP_HOST:latest,SMTP_PORT=SMTP_PORT:latest,\
RECIPIENT_EMAIL=RECIPIENT_EMAIL:latest

# 5. Grant IAM
SA="$(gcloud functions describe jobwatch-scan --gen2 --region $REGION \
  --format='value(serviceConfig.serviceAccountEmail)')"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/datastore.user"

for S in SMTP_USER SMTP_PASS SMTP_HOST SMTP_PORT RECIPIENT_EMAIL; do
  gcloud secrets add-iam-policy-binding $S \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done

# 6. Create Scheduler job (every 10 minutes)
gcloud iam service-accounts create scheduler-sa --display-name="Scheduler SA"

gcloud functions add-iam-policy-binding jobwatch-scan \
  --gen2 --region=$REGION \
  --member="serviceAccount:scheduler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

FUNC_URL="$(gcloud functions describe jobwatch-scan --gen2 --region $REGION \
  --format='value(serviceConfig.uri)')"

gcloud scheduler jobs create http jobwatch-10min \
  --schedule="*/10 * * * *" \
  --uri="$FUNC_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --oidc-token-audience="$FUNC_URL"
```

---

## Companies Monitored (~345 total)

| ATS | Count | Config |
|---|---|---|
| Amazon | 1 | `config/config-amazon.yaml` |
| Greenhouse | ~199 | `config/config-greenhouse.yaml` |
| Ashby | 107 | `config/config-ashby.yaml` |
| Lever | 38 | `config/config-lever.yaml` |

See `companies/` folder for full lists per ATS. Includes pure software companies plus hardware/IoT/embedded companies (Samsara, Verkada, Axon, Waymo, Aurora, SpaceX, Anduril, Gecko Robotics, Harmattan AI, BETA Technologies, E-Space, etc.)

---

## Target Roles (Keywords)

```
software engineer        software developer      python developer
full stack               backend engineer        devops engineer
cloud engineer           ai engineer             ml engineer
forward deployed engineer  application developer  web developer
embedded software engineer  iot engineer          embedded systems engineer (hardware companies only)
```

---

## Project Structure

```
job-hunter/
├── poller.py                  ← entry point (Task Scheduler calls this)
├── store.py                   ← SQLite persistence (seen_jobs + poll_log)
├── notifier.py                ← HTML email builder + Gmail SMTP sender
├── run_poller.bat             ← bat wrapper for Task Scheduler
├── app.py                     ← original hackathon FastAPI web UI
├── config/
│   ├── config-amazon.yaml
│   ├── config-greenhouse.yaml
│   ├── config-ashby.yaml
│   └── config-lever.yaml
├── scrapers/
│   ├── __init__.py            ← Job dataclass + seniority filter
│   ├── amazon.py
│   ├── greenhouse.py
│   ├── ashby.py
│   └── lever.py
├── companies/
│   ├── greenhouse.md
│   ├── ashby.md
│   └── lever.md
├── tests/
│   ├── test_scrapers.py
│   ├── test_store.py
│   ├── test_notifier.py
│   ├── test_greenhouse.py
│   ├── test_ashby.py
│   └── test_lever.py
├── function/
│   └── main.py               ← original hackathon GCP Cloud Function
├── .env                      ← SMTP credentials (gitignored)
└── jobs.db                   ← SQLite DB (gitignored)
```

---

## Local Setup

```bash
# Windows
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**`.env`**
```
SMTP_USER=yourname@gmail.com
SMTP_PASS=abcd efgh ijkl mnop   # 16-char Gmail App Password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
RECIPIENT_EMAIL=you@example.com
```

> Gmail: enable 2-Step Verification → Security → App Passwords → create one for Mail.

**Run manually:**
```bat
.venv\Scripts\python poller.py
```

**Run tests:**
```bat
.venv\Scripts\python -m pytest tests/ -v
```

---

## Windows Task Scheduler

- **Action:** `E:\path\to\job-hunter\run_poller.bat`
- **Trigger:** Daily, repeat every 1 hour, indefinitely, no expiry
- **Settings:** Do not start new instance if already running; run on missed start; run on battery

---

## Troubleshooting

**No email arrives**
- Check `logs/poller.log` for SMTP errors
- Gmail requires a 16-char App Password, not your login password
- Restart poller after editing `.env`

**0 jobs after filters**
- Temporarily set `max_age_days: 30` and `locations: []` in config to see raw data
- Check logs for the company — `scraped 0 job(s)` could mean the slug is wrong

**Logs not rotating**
- `RotatingFileHandler` with `backupCount=7` keeps 8 files total (1 active + 7 backups) — this is correct behaviour

---

## License

MIT — keep `.env` and `jobs.db` out of version control.
