/* === script.js === */

// ── SPA Navigation ──
document.querySelectorAll('.icon-btn[data-view]').forEach(btn => {
  btn.addEventListener('click', () => {
    const view = btn.getAttribute('data-view');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById('view-' + view);
    if (!target) return;
    target.classList.add('active', 'view-enter');
    target.addEventListener('animationend', () => target.classList.remove('view-enter'), { once: true });
    snack('Switched to ' + view);
    staggerFadeUps(target);
  });
});

// ── Ripple coords ──
document.querySelectorAll('.ripple').forEach(el => {
  el.addEventListener('pointerdown', e => {
    const r = el.getBoundingClientRect();
    el.style.setProperty('--x', (e.clientX - r.left) + 'px');
    el.style.setProperty('--y', (e.clientY - r.top)  + 'px');
  });
});

// ── Progress bar ──
const topProgress = document.getElementById('topProgress');
function prog(on) {
  topProgress.classList.toggle('active', !!on);
}

// ── Snackbar ──
const sb = document.getElementById('snackbar');
function snack(msg) {
  sb.textContent = msg;
  sb.classList.add('show');
  setTimeout(() => sb.classList.remove('show'), 1800);
}

// ── API helpers ──
async function apiGet(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || r.statusText);
  return d;
}

// ── Create company ──
document.getElementById('companyForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    prog(true);
    const payload = {
      name:               document.getElementById('company').value.trim(),
      list_url:           document.getElementById('careers').value.trim(),
      role_keywords:      (document.getElementById('keywords').value || 'software,developer,engineer').trim(),
      max_age_days:       Number(document.getElementById('postdays').value || 7),
      detail_fetch_limit: 40,
      active:             true,
    };
    await apiPost('/companies', payload);
    await renderCompanies();
    snack('Company saved');
    e.target.reset();
  } catch (err) {
    console.error(err);
    snack('Save failed: ' + err.message);
  } finally {
    prog(false);
  }
});

// ── Fill example ──
document.getElementById('loadExample').addEventListener('click', () => {
  document.getElementById('company').value      = 'Amazon';
  document.getElementById('postdays').value     = 7;
  document.getElementById('careers').value      = 'https://www.amazon.jobs/en/search?category=Software%20Development';
  document.getElementById('keywords').value     = 'software, developer, engineer';
  document.getElementById('contactEmail').value = 'you@example.com';
  snack('Example filled');
});

// ── Preview jobs ──
async function previewCompanyJobs(id) {
  try {
    prog(true);
    const data = await apiPost('/run/' + id + '?dry_run=1');
    if (data.ran === false) { snack(data.reason || 'Not supported'); renderJobs([]); return; }
    renderJobs(data.jobs || []);
    snack('Loaded ' + (data.count || (data.jobs || []).length) + ' job(s)');
  } catch (err) {
    console.error(err);
    snack('Preview failed: ' + err.message);
    renderJobs([]);
  } finally {
    prog(false);
  }
}

// ── Email jobs ──
async function emailCompanyJobs(id) {
  const email = (document.getElementById('contactEmail').value || '').trim();
  if (!email) { snack('Enter an email in "Contact email for alerts"'); return; }
  try {
    prog(true);
    const data = await apiPost('/run/' + id, { recipient_email: email });
    snack('Emailed ' + (data.count || 0) + ' job(s) to ' + email);
  } catch (err) {
    console.error(err);
    snack('Email failed: ' + err.message);
  } finally {
    prog(false);
  }
}

// ── Delete company ──
async function deleteCompany(id) {
  if (!confirm('Delete this company?')) return;
  try {
    prog(true);
    await fetch('/companies/' + id, { method: 'DELETE' });
    await renderCompanies();
    document.getElementById('jobsList').innerHTML = '<div class="hint">No jobs to show.</div>';
    snack('Company deleted');
  } catch (err) {
    console.error(err);
    snack('Delete failed: ' + err.message);
  } finally {
    prog(false);
  }
}

// ── Render jobs list ──
function renderJobs(jobs) {
  const c = document.getElementById('jobsList');
  c.innerHTML = '';
  if (!jobs || !jobs.length) {
    c.innerHTML = '<div class="hint">No jobs to show.</div>';
    return;
  }
  jobs.forEach(j => {
    const card = document.createElement('div');
    card.className = 'job-card fade-up';
    card.innerHTML = `
      <div style="font-weight:600">${esc(j.title)}</div>
      <div class="meta">${esc(j.company || '')} • ${esc(j.location || '—')}</div>
      <a href="${j.link}" target="_blank" rel="noopener">Open ↗</a>
      <div class="meta">${esc(j.posted_text || '')}</div>`;
    c.appendChild(card);
  });
  staggerFadeUps(c);
}

// ── Render companies view ──
async function renderCompanies() {
  const mount = document.getElementById('companiesList');
  if (!mount) return;
  try {
    const data = await apiGet('/companies');
    const rows = (data.companies || []).map(c => `
      <div class="row" style="display:grid;grid-template-columns:2fr 2fr .6fr 1.4fr;gap:10px;border:1px solid var(--g-border);border-radius:10px;padding:10px;background:#fff">
        <div>${esc(c.name)}</div>
        <div><small>${esc(c.list_url)}</small></div>
        <div>${Number(c.max_age_days) || 7}d</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn ripple"        onclick="previewCompanyJobs(${c.id})">Preview</button>
          <button class="btn text ripple"   onclick="emailCompanyJobs(${c.id})">Email</button>
          <button class="btn danger ripple" onclick="deleteCompany(${c.id})">Delete</button>
        </div>
      </div>`).join('');

    mount.innerHTML = `
      <div class="row head" style="display:grid;grid-template-columns:2fr 2fr .6fr 1.4fr;gap:10px;border:1px solid var(--g-border);border-radius:10px;padding:10px;background:#eef3fd;border-color:#c9d7ff;font-weight:600">
        <div>Name</div><div>Careers URL</div><div>Max Age</div><div>Actions</div>
      </div>${rows || '<div class="hint">No companies yet.</div>'}`;
  } catch (err) {
    console.error(err);
    mount.innerHTML = '<div class="hint">Failed to load companies.</div>';
  }
}

// ── Utilities ──
function esc(s) {
  return (s || '').replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[m]));
}

function staggerFadeUps(root = document, baseDelay = 0) {
  const nodes = Array.from(root.querySelectorAll('.fade-up')).filter(n => n.offsetParent !== null);
  nodes.forEach((el, i) => { el.style.animationDelay = (baseDelay + i * 80) + 'ms'; });
}

function animateBrand() {
  const letters = Array.from(document.querySelectorAll('.brand span'));
  letters.forEach((el, i) => {
    el.style.animation      = 'brandPop .45s cubic-bezier(.2,.9,.2,1) forwards';
    el.style.animationDelay = (i * 70) + 'ms';
  });
}

// ── Filter buttons ──
document.getElementById('applyFilters').addEventListener('click', () => snack('Filters applied (demo)'));
document.getElementById('clearFilters').addEventListener('click', () => {
  ['fltRole', 'fltLoc', 'fltAge'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  snack('Filters cleared');
});

// ── Dark mode ──
const darkToggle = document.getElementById('darkModeToggle');
if (darkToggle) {
  darkToggle.addEventListener('change', e => document.body.classList.toggle('dark', e.target.checked));
}

// ── Bootstrap ──
document.addEventListener('DOMContentLoaded', async () => {
  requestAnimationFrame(() => { animateBrand(); staggerFadeUps(); });
  await renderCompanies();
  try {
    const d = await apiGet('/companies');
    if ((d.companies || []).length) {
      await previewCompanyJobs(d.companies[0].id);
    }
  } catch {}
});
