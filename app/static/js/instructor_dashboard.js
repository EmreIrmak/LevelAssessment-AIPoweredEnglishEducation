(() => {
  const shell = document.querySelector('.instr-shell');
  if (!shell) return;

  const daysSelect = document.getElementById('dashDays');
  const levelSelect = document.getElementById('dashLevel');
  const statusSelect = document.getElementById('dashStatus');
  const searchInput = document.getElementById('dashSearch');
  const clearBtn = document.getElementById('dashClear');
  const exportBtn = document.getElementById('dashExport');
  const countEl = document.getElementById('dashCount');
  const levelChart = document.getElementById('dashLevelChart');
  const moduleBars = document.getElementById('dashModuleBars');
  const heatmap = document.getElementById('dashHeatmap');
  const heatLegend = document.getElementById('dashHeatLegend');
  const mistakes = document.getElementById('dashMistakes');

  const kpiTotalStudents = document.getElementById('kpiTotalStudents');
  const kpiActive = document.getElementById('kpiActive');
  const kpiAvgScore = document.getElementById('kpiAvgScore');
  const kpiCompletion = document.getElementById('kpiCompletion');

  const rows = Array.from(shell.querySelectorAll('table.dash-table tbody tr'))
    .filter((tr) => tr.querySelector('td'));

  const STORAGE_KEY = 'instructorDashFilters:v1';

  const moduleOrder = ['Vocabulary', 'Grammar', 'Reading', 'Writing', 'Listening', 'Speaking'];

  function clamp01(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return 0;
    return Math.max(0, Math.min(1, x));
  }

  function pct(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '0.0%';
    return `${x.toFixed(1)}%`;
  }

  function setText(el, text) {
    if (!el) return;
    el.textContent = String(text ?? '');
  }

  function renderKpis(kpis) {
    setText(kpiTotalStudents, kpis?.total_students ?? 0);
    setText(kpiActive, kpis?.active_this_week ?? 0);
    setText(kpiAvgScore, pct(kpis?.avg_score ?? 0));
    setText(kpiCompletion, pct(kpis?.completion_rate ?? 0));
    if (heatLegend) {
      const days = Number(kpis?.timeframe_days ?? 7);
      heatLegend.textContent = `Last ${Number.isFinite(days) ? days : 7} days`;
    }
  }

  function renderCefr(dist) {
    if (!levelChart) return;
    const items = Array.isArray(dist) ? dist : [];
    const max = Math.max(1, ...items.map((i) => Number(i?.count) || 0));
    levelChart.innerHTML = '';

    items.forEach((item) => {
      const level = String(item?.level ?? '').trim();
      const count = Number(item?.count) || 0;
      const h = Math.round(clamp01(count / max) * 100);

      const btn = document.createElement('button');
      btn.className = 'mini-bar';
      btn.type = 'button';
      btn.setAttribute('data-level', level);
      btn.title = `${level}: ${count}`;

      const col = document.createElement('div');
      col.className = 'mini-bar-col';
      col.style.height = `${h}%`;

      const label = document.createElement('div');
      label.className = 'mini-bar-label';
      label.textContent = level;

      btn.appendChild(col);
      btn.appendChild(label);
      levelChart.appendChild(btn);
    });
  }

  function exportPdf() {
    const url = new URL('/instructor/leaderboard/export.pdf', window.location.origin);
    const days = Number(daysSelect?.value || 7);
    url.searchParams.set('days', String(Number.isFinite(days) ? days : 7));

    const q = (searchInput?.value || '').toString().trim();
    const level = (levelSelect?.value || '').toString().trim();
    const status = (statusSelect?.value || '').toString().trim();

    if (q) url.searchParams.set('q', q);
    if (level) url.searchParams.set('level', level);
    if (status) url.searchParams.set('status', status);

    window.location.assign(url.toString());
  }

  function renderModuleAverages(mods) {
    if (!moduleBars) return;
    const items = Array.isArray(mods) ? mods : [];
    const byName = new Map(items.map((i) => [String(i?.module ?? ''), Number(i?.avg) || 0]));
    moduleBars.innerHTML = '';

    moduleOrder.forEach((name) => {
      const avg = byName.has(name) ? byName.get(name) : 0;
      const safeAvg = Number.isFinite(avg) ? Math.max(0, Math.min(100, avg)) : 0;

      const row = document.createElement('div');
      row.className = 'module-bar';

      const k = document.createElement('div');
      k.className = 'module-bar-k';
      k.textContent = name.slice(0, 1);

      const track = document.createElement('div');
      track.className = 'module-bar-track';
      track.setAttribute('aria-hidden', 'true');

      const fill = document.createElement('div');
      fill.className = 'module-bar-fill';
      fill.style.width = `${safeAvg}%`;

      const v = document.createElement('div');
      v.className = 'module-bar-v';
      v.textContent = `${safeAvg.toFixed(1)}%`;

      track.appendChild(fill);
      row.appendChild(k);
      row.appendChild(track);
      row.appendChild(v);
      moduleBars.appendChild(row);
    });
  }

  function renderHeatmap(series) {
    if (!heatmap) return;
    const items = Array.isArray(series) ? series : [];
    const max = Math.max(1, ...items.map((i) => Number(i?.count) || 0));
    heatmap.innerHTML = '';

    items.forEach((d) => {
      const date = String(d?.date ?? '');
      const count = Number(d?.count) || 0;
      const op = 0.15 + clamp01(count / max) * 0.85;
      const cell = document.createElement('div');
      cell.className = 'heat-cell';
      cell.title = `${date}: ${count} attempts`;
      cell.style.setProperty('--op', String(op));
      heatmap.appendChild(cell);
    });
  }

  function renderMistakes(list) {
    if (!mistakes) return;
    const items = Array.isArray(list) ? list : [];
    mistakes.innerHTML = '';

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'dash-muted';
      empty.textContent = 'No mistake data yet.';
      mistakes.appendChild(empty);
      return;
    }

    items.forEach((m) => {
      const row = document.createElement('div');
      row.className = 'mistake-row';

      const name = document.createElement('div');
      name.className = 'mistake-name';
      name.textContent = String(m?.module ?? 'Unknown');

      const count = document.createElement('div');
      count.className = 'mistake-count';
      count.textContent = String(m?.count ?? 0);

      row.appendChild(name);
      row.appendChild(count);
      mistakes.appendChild(row);
    });
  }

  async function refreshDashboard(days) {
    const apiUrl = shell.getAttribute('data-dashboard-api');
    if (!apiUrl) return;

    const url = new URL(apiUrl, window.location.origin);
    url.searchParams.set('days', String(days || 7));

    shell.setAttribute('aria-busy', 'true');
    if (daysSelect) daysSelect.disabled = true;
    try {
      const res = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (!payload || payload.ok !== true) throw new Error(payload?.error || 'bad response');

      renderKpis(payload.kpis);
      renderCefr(payload?.charts?.cefr_distribution);
      renderModuleAverages(payload?.charts?.avg_by_module);
      renderHeatmap(payload?.charts?.attempts_series);
      renderMistakes(payload?.widgets?.top_mistakes);

      // Keep URL in sync without reloading
      const current = new URL(window.location.href);
      current.searchParams.set('days', String(days || 7));
      window.history.replaceState({}, '', current);
    } finally {
      shell.removeAttribute('aria-busy');
      if (daysSelect) daysSelect.disabled = false;
    }
  }

  function readFilters() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { q: '', level: '', status: '' };
      const parsed = JSON.parse(raw);
      return {
        q: typeof parsed.q === 'string' ? parsed.q : '',
        level: typeof parsed.level === 'string' ? parsed.level : '',
        status: typeof parsed.status === 'string' ? parsed.status : '',
      };
    } catch {
      return { q: '', level: '', status: '' };
    }
  }

  function writeFilters(filters) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
    } catch {
      // ignore
    }
  }

  function normalize(s) {
    return (s || '').toString().trim().toLowerCase();
  }

  function applyFilters() {
    const q = normalize(searchInput?.value);
    const level = (levelSelect?.value || '').trim();
    const status = (statusSelect?.value || '').trim();

    let shown = 0;

    rows.forEach((tr) => {
      const name = tr.getAttribute('data-name') || '';
      const email = tr.getAttribute('data-email') || '';
      const rLevel = (tr.getAttribute('data-level') || '').trim();
      const rStatus = (tr.getAttribute('data-status') || '').trim();

      const matchesQ = !q || name.includes(q) || email.includes(q);
      const matchesLevel = !level || rLevel === level;
      const matchesStatus = !status || rStatus === status;

      const show = matchesQ && matchesLevel && matchesStatus;
      tr.style.display = show ? '' : 'none';
      if (show) shown += 1;
    });

    if (countEl) {
      countEl.textContent = `${shown} student${shown === 1 ? '' : 's'} shown`;
    }

    writeFilters({ q: searchInput?.value || '', level, status });
  }

  function clearFilters() {
    if (searchInput) searchInput.value = '';
    if (levelSelect) levelSelect.value = '';
    if (statusSelect) statusSelect.value = '';
    applyFilters();
  }

  function updateDaysParam(days) {
    // Prefer async refresh; fallback to full reload if fetch fails.
    refreshDashboard(days).catch(() => {
      const url = new URL(window.location.href);
      url.searchParams.set('days', String(days));
      window.location.assign(url.toString());
    });
  }

  function exportCsv() {
    const header = ['Student', 'Email', 'Last Attempt', 'Level', 'Overall', 'Status', 'Report Link'];
    const visible = rows.filter((tr) => tr.style.display !== 'none');

    const lines = [header];
    visible.forEach((tr) => {
      const tds = Array.from(tr.querySelectorAll('td'));
      const student = tds[0]?.innerText?.replace(/\s+/g, ' ').trim() || '';
      const email = tds[1]?.innerText?.trim() || '';
      const lastAttempt = tds[2]?.innerText?.trim() || '';
      const level = tds[3]?.innerText?.trim() || '';
      const overall = tds[4]?.innerText?.trim() || '';
      const status = tds[5]?.innerText?.trim() || '';
      const link = tr.querySelector('a.status-pill')?.getAttribute('href') || '';
      lines.push([student, email, lastAttempt, level, overall, status, link]);
    });

    const escapeCell = (cell) => {
      const s = String(cell ?? '');
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };

    const csv = lines.map((row) => row.map(escapeCell).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'instructor_dashboard_leaderboard.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // Restore saved filters
  const saved = readFilters();
  if (searchInput && saved.q) searchInput.value = saved.q;
  if (levelSelect && saved.level) levelSelect.value = saved.level;
  if (statusSelect && saved.status) statusSelect.value = saved.status;

  // Bind events
  if (searchInput) searchInput.addEventListener('input', applyFilters);
  if (levelSelect) levelSelect.addEventListener('change', applyFilters);
  if (statusSelect) statusSelect.addEventListener('change', applyFilters);
  if (clearBtn) clearBtn.addEventListener('click', clearFilters);

  if (daysSelect) {
    daysSelect.addEventListener('change', () => {
      updateDaysParam(daysSelect.value || '7');
    });
  }

  if (exportBtn) exportBtn.addEventListener('click', exportPdf);

  if (levelChart) {
    levelChart.addEventListener('click', (e) => {
      const target = e.target instanceof Element ? e.target.closest('button[data-level]') : null;
      if (!target) return;
      const level = target.getAttribute('data-level') || '';
      if (levelSelect) {
        levelSelect.value = level;
        applyFilters();
      }
    });
  }

  // Initial apply
  applyFilters();

  // Refresh visuals from backend (ensures widgets aren't just placeholders)
  const initialDays = Number(daysSelect?.value || 7);
  refreshDashboard(Number.isFinite(initialDays) ? initialDays : 7).catch(() => {
    // ignore; server-rendered values remain
  });
})();
