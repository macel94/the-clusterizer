import './styles.css';
import { createAnalysis, listAnalyses, getAnalysis, deleteAnalysis } from './api';
import type { Analysis, AnalysisCreate, ClusterInfo } from './types';

// ── Cluster colour palette ────────────────────────────────────────────────
// Ten distinct hues; opacity is applied via CSS custom property on each card
const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#059669', '#d97706', '#dc2626',
  '#0891b2', '#7c2d12', '#4f46e5', '#0f766e', '#b91c1c',
];

// ── State ─────────────────────────────────────────────────────────────────
let analyses: Analysis[] = [];
let selectedId: string | null = null;
const pollingTimers = new Map<string, ReturnType<typeof setInterval>>();

// ── Bootstrap ────────────────────────────────────────────────────────────
document.querySelector<HTMLDivElement>('#app')!.innerHTML = buildShell();
attachFormListeners();
loadAnalyses();

// ── Shell HTML ────────────────────────────────────────────────────────────
function buildShell(): string {
  return `
    <header>
      <div>
        <h1>🔮 The Clusterizer</h1>
        <p>Discover patterns in your Jira tickets with AI-powered clustering</p>
      </div>
    </header>
    <main>
      <!-- Left panel: form + history -->
      <aside>
        <div class="card" style="margin-bottom:1.5rem">
          <h2>New Analysis</h2>
          <form id="analysis-form" novalidate>
            <div class="form-group">
              <label for="jira_url">Jira URL</label>
              <input id="jira_url" type="url" placeholder="https://mycompany.atlassian.net" required />
            </div>
            <div class="form-group">
              <label for="username">Username / Email</label>
              <input id="username" type="text" placeholder="user@example.com" />
              <div class="hint">Cloud: email + API token &nbsp;·&nbsp; Server/DC: leave blank to use Bearer token</div>
            </div>
            <div class="form-group">
              <label for="pat">API Token / PAT</label>
              <input id="pat" type="password" placeholder="Your API token or PAT" required />
            </div>
            <div class="form-group">
              <label for="jql_filter">JQL Filter</label>
              <input id="jql_filter" type="text" placeholder='project = "MY-PROJ" AND status != Done' required />
            </div>
            <div class="form-group">
              <label for="num_clusters">Number of Clusters (2–20)</label>
              <input id="num_clusters" type="number" min="2" max="20" value="5" required />
            </div>
            <div id="form-error" class="error-box" style="display:none;margin-bottom:.75rem"></div>
            <button type="submit" class="btn-primary" id="submit-btn">
              ✨ Analyze
            </button>
          </form>
        </div>

        <div class="card">
          <h2>Recent Analyses</h2>
          <div id="analyses-list">
            <div class="empty-state">No analyses yet.</div>
          </div>
        </div>
      </aside>

      <!-- Right panel: results -->
      <section id="results-panel">
        <div class="card">
          <div class="empty-state" style="padding:4rem 2rem">
            <p style="font-size:2.5rem;margin-bottom:.75rem">🔮</p>
            <p>Select an analysis or start a new one to see cluster results.</p>
          </div>
        </div>
      </section>
    </main>
  `;
}

// ── Load analyses ─────────────────────────────────────────────────────────
async function loadAnalyses(): Promise<void> {
  try {
    analyses = await listAnalyses();
    renderAnalysisList();
    // Resume polling for any running/pending analyses
    for (const a of analyses) {
      if (a.status === 'pending' || a.status === 'running') {
        startPolling(a.id);
      }
    }
  } catch (err) {
    console.error('Failed to load analyses', err);
  }
}

// ── Render analysis list ──────────────────────────────────────────────────
function renderAnalysisList(): void {
  const container = document.getElementById('analyses-list')!;
  if (analyses.length === 0) {
    container.innerHTML = '<div class="empty-state">No analyses yet.</div>';
    return;
  }
  container.innerHTML = analyses
    .map((a) => renderAnalysisItem(a))
    .join('');

  container.querySelectorAll<HTMLElement>('.analysis-item').forEach((el) => {
    el.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (target.closest('.btn-danger')) return; // handled separately
      selectAnalysis(el.dataset['id']!);
    });
  });

  container.querySelectorAll<HTMLButtonElement>('.delete-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset['id']!;
      if (!confirm('Delete this analysis?')) return;
      await deleteAnalysis(id);
      if (selectedId === id) {
        selectedId = null;
        renderResults(null);
      }
      analyses = analyses.filter((a) => a.id !== id);
      renderAnalysisList();
    });
  });
}

function renderAnalysisItem(a: Analysis): string {
  const date = new Date(a.created_at).toLocaleString();
  const host = safeHostname(a.jira_url);
  return `
    <div class="analysis-item${selectedId === a.id ? ' active' : ''}" data-id="${a.id}">
      <div class="analysis-item-header">
        <span class="analysis-item-url" title="${esc(a.jira_url)}">${esc(host)}</span>
        <span class="badge badge-${a.status}">${statusLabel(a.status)}</span>
      </div>
      <div class="analysis-item-jql" title="${esc(a.jql_filter)}">${esc(a.jql_filter)}</div>
      <div class="analysis-item-meta">
        <span class="analysis-item-date">${date}</span>
        <button class="btn-danger delete-btn" data-id="${a.id}">Delete</button>
      </div>
    </div>
  `;
}

// ── Select an analysis ────────────────────────────────────────────────────
async function selectAnalysis(id: string): Promise<void> {
  selectedId = id;
  renderAnalysisList(); // update active highlight

  const analysis = analyses.find((a) => a.id === id)!;
  renderResults(analysis);

  if (analysis.status === 'pending' || analysis.status === 'running') {
    startPolling(id);
  } else if (analysis.status === 'completed' && !analysis.clusters) {
    // Fetch full details with clusters
    const full = await getAnalysis(id);
    updateAnalysis(full);
    renderResults(full);
  }
}

// ── Render results panel ──────────────────────────────────────────────────
function renderResults(analysis: Analysis | null): void {
  const panel = document.getElementById('results-panel')!;

  if (!analysis) {
    panel.innerHTML = `
      <div class="card">
        <div class="empty-state" style="padding:4rem 2rem">
          <p style="font-size:2.5rem;margin-bottom:.75rem">🔮</p>
          <p>Select an analysis or start a new one to see cluster results.</p>
        </div>
      </div>`;
    return;
  }

  if (analysis.status === 'pending' || analysis.status === 'running') {
    panel.innerHTML = `
      <div class="card running-state">
        <div class="spinner"></div>
        <h3>Analysis in progress…</h3>
        <p>Fetching Jira tickets, generating embeddings, and clustering.</p>
        <p>This may take up to a minute depending on the number of tickets.</p>
      </div>`;
    return;
  }

  if (analysis.status === 'failed') {
    panel.innerHTML = `
      <div class="card">
        <h2>Analysis Failed</h2>
        <div class="error-box" style="margin-top:.75rem">${esc(analysis.error_message ?? 'Unknown error')}</div>
      </div>`;
    return;
  }

  // Completed
  const clusters = analysis.clusters ?? [];
  panel.innerHTML = `
    <div class="card">
      <div class="results-header">
        <div>
          <h2>Cluster Results</h2>
          <div style="color:var(--text-muted);font-size:.85rem;margin-top:.25rem">
            ${esc(analysis.jira_url)} &nbsp;·&nbsp; ${esc(analysis.jql_filter)}
          </div>
        </div>
      </div>
      <div class="results-summary">
        <div class="stat">
          <div class="stat-value">${analysis.total_tickets}</div>
          <div class="stat-label">Tickets analysed</div>
        </div>
        <div class="stat">
          <div class="stat-value">${clusters.length}</div>
          <div class="stat-label">Clusters found</div>
        </div>
        ${analysis.completed_at
          ? `<div class="stat">
              <div class="stat-value">${formatDuration(analysis.created_at, analysis.completed_at)}</div>
              <div class="stat-label">Analysis time</div>
             </div>`
          : ''}
      </div>
    </div>
    <div class="clusters-grid">
      ${clusters.map((c, i) => renderClusterCard(c, i)).join('')}
    </div>`;
}

function renderClusterCard(c: ClusterInfo, index: number): string {
  const color = CLUSTER_COLORS[index % CLUSTER_COLORS.length];
  const pct = c.percentage ?? 0;
  const keywords = (c.keywords ?? [])
    .map((k) => `<span class="keyword-tag">${esc(k)}</span>`)
    .join('');
  const tickets = (c.representative_tickets ?? [])
    .map(
      (t) => `<div class="ticket-row">
        <span class="ticket-key">${esc(t.key)}</span>
        <span class="ticket-summary">${esc(t.summary)}</span>
      </div>`
    )
    .join('');

  return `
    <div class="cluster-card" style="--cluster-color:${color}">
      <div class="cluster-rank">#${index + 1} · ${pct}% of tickets</div>
      <div class="cluster-label">${esc(c.label)}</div>
      <div class="cluster-bar-wrapper">
        <div class="cluster-bar" style="width:${pct}%"></div>
      </div>
      <div class="cluster-count">
        <span>${c.ticket_count} ticket${c.ticket_count !== 1 ? 's' : ''}</span>
        <span>${pct}%</span>
      </div>
      ${keywords ? `<div class="cluster-keywords">${keywords}</div>` : ''}
      ${tickets
        ? `<div class="cluster-tickets">
            <h4>Representative tickets</h4>
            ${tickets}
           </div>`
        : ''}
    </div>`;
}

// ── Form ──────────────────────────────────────────────────────────────────
function attachFormListeners(): void {
  document.addEventListener('submit', async (e) => {
    const form = (e.target as HTMLElement).closest<HTMLFormElement>('#analysis-form');
    if (!form) return;
    e.preventDefault();
    await handleFormSubmit(form);
  });
}

async function handleFormSubmit(form: HTMLFormElement): Promise<void> {
  const errorBox = document.getElementById('form-error')!;
  const submitBtn = document.getElementById('submit-btn') as HTMLButtonElement;

  const jiraUrl = (form.querySelector<HTMLInputElement>('#jira_url')!).value.trim();
  const username = (form.querySelector<HTMLInputElement>('#username')!).value.trim() || undefined;
  const pat = (form.querySelector<HTMLInputElement>('#pat')!).value.trim();
  const jqlFilter = (form.querySelector<HTMLInputElement>('#jql_filter')!).value.trim();
  const numClusters = parseInt((form.querySelector<HTMLInputElement>('#num_clusters')!).value, 10);

  // Basic validation
  if (!jiraUrl) { showFormError(errorBox, 'Jira URL is required.'); return; }
  if (!pat) { showFormError(errorBox, 'API token / PAT is required.'); return; }
  if (!jqlFilter) { showFormError(errorBox, 'JQL filter is required.'); return; }
  if (isNaN(numClusters) || numClusters < 2 || numClusters > 20) {
    showFormError(errorBox, 'Number of clusters must be between 2 and 20.');
    return;
  }

  errorBox.style.display = 'none';
  submitBtn.disabled = true;
  submitBtn.textContent = '⏳ Starting…';

  try {
    const payload: AnalysisCreate = { jira_url: jiraUrl, username, pat, jql_filter: jqlFilter, num_clusters: numClusters };
    const analysis = await createAnalysis(payload);
    analyses.unshift(analysis);
    renderAnalysisList();
    selectedId = analysis.id;
    renderResults(analysis);
    startPolling(analysis.id);
    form.reset();
    (form.querySelector<HTMLInputElement>('#num_clusters')!).value = '5';
  } catch (err) {
    showFormError(errorBox, String(err instanceof Error ? err.message : err));
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '✨ Analyze';
  }
}

function showFormError(box: HTMLElement, msg: string): void {
  box.textContent = msg;
  box.style.display = 'block';
}

// ── Polling ───────────────────────────────────────────────────────────────
function startPolling(id: string): void {
  if (pollingTimers.has(id)) return;
  const timer = setInterval(async () => {
    try {
      const updated = await getAnalysis(id);
      updateAnalysis(updated);
      if (updated.status === 'completed' || updated.status === 'failed') {
        clearInterval(timer);
        pollingTimers.delete(id);
      }
      if (selectedId === id) renderResults(updated);
      renderAnalysisList();
    } catch {
      clearInterval(timer);
      pollingTimers.delete(id);
    }
  }, 3000);
  pollingTimers.set(id, timer);
}

function updateAnalysis(updated: Analysis): void {
  const idx = analyses.findIndex((a) => a.id === updated.id);
  if (idx !== -1) analyses[idx] = updated;
}

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function safeHostname(url: string): string {
  try { return new URL(url).hostname; } catch { return url; }
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '⏳ Pending', running: '⚙️ Running',
    completed: '✅ Done', failed: '❌ Failed',
  };
  return map[s] ?? s;
}

function formatDuration(start: string, end: string): string {
  const secs = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}
