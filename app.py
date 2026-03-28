import os
import re
import ssl
import smtplib
import json
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from email.message import EmailMessage
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

import requests
from bs4 import BeautifulSoup

# ---------- .env (optional) ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- FastAPI ----------
app = FastAPI(title="JobWatch Local")
# Use absolute path so the static mount works regardless of where uvicorn is launched from
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "templates", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

# ---------- SQLite ----------
class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), unique=True, nullable=False)
    list_url = Column(Text, nullable=False)
    role_keywords = Column(Text, nullable=True)   # "software,developer,engineer"
    job_link_regex = Column(Text, nullable=True)  # unused for Amazon
    max_age_days = Column(Integer, nullable=False, default=7)
    detail_fetch_limit = Column(Integer, nullable=False, default=40)
    active = Column(Boolean, nullable=False, default=True)

DB_URL = "sqlite:///jobs.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)

# ---------- Helpers ----------
def parse_keywords(csv: Optional[str]) -> List[str]:
    if not csv:
        return []
    return [k.strip().lower() for k in csv.split(",") if k.strip()]

def origin_from(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

# ---------- Date parsing ----------
MONTH_INDEX = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
MONTH_NAME_DATE_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?)\s+(\d{1,2}),\s*(\d{4})\b",
    re.I,
)
RELATIVE_RE = re.compile(r"(\d+)\s+(day|days|hour|hours|week|weeks|month|months)\s+ago", re.I)
UPDATED_LABEL_RE = re.compile(
    r"(Updated|Posted)\s*:?\s*(?P<date>(?:\d{4}-\d{2}-\d{2})|(?:\d{1,2}/\d{1,2}/\d{4})|"
    r"(?:[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}))",
    re.I,
)

def parse_possible_date(text: str):
    if not text:
        return None, None
    m = ISO_DATE_RE.search(text)
    if m:
        try:
            return m.group(1), datetime.strptime(m.group(1), "%Y-%m-%d")
        except:
            pass
    m = MONTH_NAME_DATE_RE.search(text)
    if m:
        try:
            mon = MONTH_INDEX[m.group(1).lower()]
            return m.group(0), datetime(int(m.group(3)), mon, int(m.group(2)))
        except:
            pass
    m = DATE_RE.search(text)
    if m:
        try:
            return m.group(1), datetime.strptime(m.group(1), "%m/%d/%Y")
        except:
            pass
    m = RELATIVE_RE.search(text)
    if m:
        n = int(m.group(1)); unit = m.group(2).lower()
        delta = {
            "hour": timedelta(hours=n), "hours": timedelta(hours=n),
            "day": timedelta(days=n),   "days": timedelta(days=n),
            "week": timedelta(weeks=n), "weeks": timedelta(weeks=n),
            "month": timedelta(days=30*n), "months": timedelta(days=30*n),
        }[unit]
        return m.group(0), datetime.utcnow() - delta
    return None, None

# ---------- Amazon scraping ----------
HTTP_TIMEOUT = 30
AMAZON_BASE = "https://www.amazon.jobs/en/"
AMAZON_ROOT = "https://www.amazon.jobs"
JOB_PATH_RE = re.compile(r"^(/en)?/jobs/")

def normalize_amazon_link(link: str) -> str:
    if not link:
        return ""
    link = link.strip()
    if link.startswith("http"):
        if "amazon.jobs" in link and "/jobs/" in link:
            return link
        return ""
    if JOB_PATH_RE.search(link):
        return urljoin(AMAZON_ROOT, link)
    return ""

def make_amazon_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/119.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "application/json;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": AMAZON_BASE,
        "Cache-Control": "no-cache", "Pragma": "no-cache",
    })
    try:
        s.get(AMAZON_BASE, timeout=HTTP_TIMEOUT)
    except Exception:
        pass
    return s

def try_amazon_json(s: requests.Session, role_keywords: List[str]) -> List[Dict[str, Any]]:
    candidates = [
        ("https://www.amazon.jobs/en/search.json",
         [("result_limit", "100"), ("offset", "0"), ("category[]", "Software Development")]),
        ("https://www.amazon.jobs/en/search.json",
         [("result_limit", "100"), ("offset", "0"), ("job_category[]", "Software Development")]),
        ("https://www.amazon.jobs/en/search.json",
         [("result_limit", "100"), ("offset", "0"), ("query", "software")]),
    ]
    jobs = []
    for url, params in candidates:
        try:
            r = s.get(url, params=params, timeout=HTTP_TIMEOUT)
            if not r.ok:
                continue
            data = r.json()
        except Exception:
            continue

        lists = []
        if isinstance(data, dict):
            for key in ("jobs", "search_results", "results", "hits", "items"):
                if key in data and isinstance(data[key], list):
                    lists.append(data[key])
            if not lists:
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        lists.append(v)

        for lst in lists:
            for it in lst:
                title = (it.get("title") or it.get("job_title") or "").strip()
                if not title or (role_keywords and not any(k in title.lower() for k in role_keywords)):
                    continue
                link = (it.get("job_path") or it.get("absolute_url") or "").strip()
                if not link:
                    link = (it.get("apply_url") or it.get("url_next_step") or "").strip()
                link = normalize_amazon_link(link)
                if not link:
                    continue
                location = (it.get("location") or it.get("normalized_location") or it.get("city") or "") or ""
                posted_text = (it.get("posted_date") or it.get("posting_date") or it.get("posted_at") or "")
                _, posted_dt = parse_possible_date(str(posted_text))
                jobs.append({
                    "title": title, "link": link, "location": location,
                    "posted_text": str(posted_text) if posted_text else "",
                    "_posted_dt": posted_dt,
                })
        if jobs:
            break

    uniq = {(j["title"], j["link"]): j for j in jobs if j.get("link")}
    return list(uniq.values())

def extract_from_amazon_html(html: str, role_keywords: List[str]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    jobs = []
    for a in anchors:
        link = normalize_amazon_link(a["href"].strip())
        if not link:
            continue
        title = a.get_text(strip=True)
        if not title or (role_keywords and not any(k in title.lower() for k in role_keywords)):
            continue
        parent = a.find_parent()
        block_text = parent.get_text(" ", strip=True) if parent else title
        location = ""
        for kw in ["United States", "India", "Canada", "Remote", "Hybrid", "Seattle", "Bangalore", "Hyderabad"]:
            if kw in block_text:
                location = kw; break
        posted_text, posted_dt = parse_possible_date(block_text)
        jobs.append({
            "title": title, "link": link, "location": location,
            "posted_text": posted_text or "", "_posted_dt": posted_dt,
        })
    uniq = {(j["title"], j["link"]): j for j in jobs}
    return list(uniq.values())

def try_amazon_html(s: requests.Session, role_keywords: List[str]) -> List[Dict[str, Any]]:
    jobs = []
    try:
        r = s.get(urljoin(AMAZON_BASE, "job_categories/software-development"), timeout=HTTP_TIMEOUT)
        if r.ok:
            jobs += extract_from_amazon_html(r.text, role_keywords)
    except Exception:
        pass
    for params in ({"category": "Software Development"}, {"query": "software"}):
        try:
            r = s.get(urljoin(AMAZON_BASE, "search"), params=params, timeout=HTTP_TIMEOUT)
            if r.ok:
                jobs += extract_from_amazon_html(r.text, role_keywords)
        except Exception:
            pass
    uniq = {(j["title"], j["link"]): j for j in jobs}
    return list(uniq.values())

def enrich_posted_dates(jobs: List[Dict[str, Any]], s: requests.Session, limit: int):
    fetched = 0
    for j in jobs:
        if j.get("_posted_dt"):
            continue
        if fetched >= limit:
            break
        link = j.get("link")
        if not link:
            continue
        try:
            r = s.get(link, timeout=HTTP_TIMEOUT)
            if not r.ok:
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            # JSON-LD
            found = False
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or script.text or "{}")
                except Exception:
                    continue
                objs = data if isinstance(data, list) else [data]
                for obj in objs:
                    if isinstance(obj, dict):
                        for key in ("datePosted", "dateModified", "datePublished"):
                            if key in obj:
                                txt, dt = parse_possible_date(str(obj[key]))
                                if dt:
                                    j["_posted_dt"] = dt
                                    j["posted_text"] = txt or str(obj[key])
                                    found = True
                                    break
                    if found: break
                if found: break

            # Meta tags
            if not j.get("_posted_dt"):
                for name in ("article:published_time", "article:modified_time", "og:updated_time"):
                    m = soup.find("meta", attrs={"property": name})
                    if m and m.get("content"):
                        txt, dt = parse_possible_date(m["content"])
                        if dt:
                            j["_posted_dt"] = dt
                            j["posted_text"] = txt or m["content"]
                            found = True
                            break

            # Visible labels
            if not j.get("_posted_dt"):
                m = UPDATED_LABEL_RE.search(soup.get_text(" ", strip=True))
                if m:
                    ds = m.group("date")
                    txt, dt = parse_possible_date(ds)
                    if dt:
                        j["_posted_dt"] = dt
                        j["posted_text"] = f"{m.group(1).title()}: {ds}"
        except Exception:
            pass
        fetched += 1

def filter_by_age(jobs: List[Dict[str, Any]], max_age_days: int) -> List[Dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    fresh = []
    for j in jobs:
        dt = j.get("_posted_dt")
        if not dt and j.get("posted_text"):
            _, dt = parse_possible_date(j["posted_text"])
        if dt and dt >= cutoff:
            fresh.append(j)
    return fresh

def fetch_amazon_jobs(role_keywords: List[str], max_age_days: int, detail_fetch_limit: int) -> List[Dict[str, Any]]:
    s = make_amazon_session()
    jobs = try_amazon_json(s, role_keywords)
    if not jobs:
        jobs = try_amazon_html(s, role_keywords)
    enrich_posted_dates(jobs, s, limit=detail_fetch_limit)
    jobs = filter_by_age(jobs, max_age_days)
    return jobs

# ---------- Email ----------
def send_email_html(recipient: str, subject: str, html: str):
    import smtplib, ssl
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))  # 587 = STARTTLS, 465 = SSL

    if not smtp_user or not smtp_pass:
        raise RuntimeError("Missing SMTP_USER/SMTP_PASS env vars")

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content("Your client does not support HTML.")
    msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as s:
                s.login(smtp_user, smtp_pass.replace(" ", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.ehlo(); s.starttls(context=ctx); s.ehlo()
                s.login(smtp_user, smtp_pass.replace(" ", ""))
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError("SMTP auth failed. If you use Gmail, enable 2-Step Verification and use a 16-char App Password.") from e
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {type(e).__name__}: {e}") from e

def render_email(company_name: str, role_keywords: List[str], max_age_days: int, jobs: List[Dict[str, Any]]) -> str:
    if jobs:
        rows = "".join(
            f'<tr>'
            f'<td><a href="{j["link"]}">{j["title"]}</a></td>'
            f'<td>{j.get("location","")}</td>'
            f'<td>{j.get("posted_text","")}</td>'
            f'</tr>' for j in jobs
        )
        html = f"""
        <h2>{company_name} careers (last {max_age_days} days)</h2>
        <p>Filter: {", ".join(role_keywords) if role_keywords else "(none)"} </p>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>Title</th><th>Location</th><th>Posted / Updated</th></tr>
          {rows}
        </table>
        <p>Total (fresh): {len(jobs)}</p>
        """
    else:
        html = f"<h2>No recent matches (≤ {max_age_days} days) for {company_name}</h2>"
    return html

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/companies")
def list_companies():
    db = SessionLocal()
    data = [
        {
            "id": c.id, "name": c.name, "list_url": c.list_url,
            "role_keywords": c.role_keywords, "max_age_days": c.max_age_days,
            "detail_fetch_limit": c.detail_fetch_limit, "active": c.active
        }
        for c in db.query(Company).order_by(Company.id.desc()).all()
    ]
    return {"companies": data}

@app.post("/companies")
def create_company(payload: Dict[str, Any]):
    name = payload.get("name") or payload.get("company")
    list_url = payload.get("list_url") or payload.get("careers")
    role_keywords = payload.get("role_keywords") or payload.get("keywords") or "software,developer,engineer"
    max_age_days = int(payload.get("max_age_days") or payload.get("post_days") or payload.get("postdays") or 7)
    detail_fetch_limit = int(payload.get("detail_fetch_limit") or 40)
    active = bool(payload.get("active", True))

    if not name or not list_url:
        raise HTTPException(status_code=400, detail="name/company and list_url/careers are required")

    db = SessionLocal()
    if db.query(Company).filter(Company.name == name).first():
        raise HTTPException(status_code=409, detail="Company with this name already exists")

    c = Company(
        name=name, list_url=list_url, role_keywords=role_keywords,
        job_link_regex=None, max_age_days=max_age_days,
        detail_fetch_limit=detail_fetch_limit, active=active
    )
    db.add(c); db.commit()
    return {"ok": True, "id": c.id}

@app.post("/run/{company_id}")
def run_company(company_id: int, dry_run: bool = Query(False)):
    db = SessionLocal()
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    host = urlparse(c.list_url).netloc.lower()
    role_keys = parse_keywords(c.role_keywords)

    if "amazon.jobs" not in host:
        return {"ok": True, "company": c.name, "ran": False,
                "reason": "Only Amazon is supported in this local prototype."}

    jobs = fetch_amazon_jobs(role_keys, c.max_age_days, c.detail_fetch_limit)

    if dry_run:
        return {"ok": True, "company": c.name, "count": len(jobs), "jobs": jobs}

    # Env-only recipient
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not recipient:
        raise HTTPException(status_code=500, detail="RECIPIENT_EMAIL env var missing")

    html = render_email(c.name, role_keys, c.max_age_days, jobs)
    subject = f"[JobWatch Local] {c.name} roles (≤{c.max_age_days}d)"
    try:
        send_email_html(recipient, subject, html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {e}")

    return {"ok": True, "company": c.name, "count": len(jobs)}

@app.delete("/companies/{company_id}")
def delete_company(company_id: int):
    db = SessionLocal()
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    db.delete(c)
    db.commit()
    return {"ok": True}

@app.post("/companies/reset")
def reset_companies():
    db = SessionLocal()
    db.query(Company).delete()
    db.commit()
    return {"ok": True}
