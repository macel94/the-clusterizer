import './styles.css';
import {
  createAnalysis,
  listAnalyses,
  getAnalysis,
  deleteAnalysis,
  searchAnalysisTickets,
  getAnalysisTicket,
} from './api';
import type {
  Analysis,
  AnalysisCreate,
  ClusterInfo,
  TicketDetail,
  TicketSearchItem,
  TicketSearchResponse,
} from './types';

// ── Cluster colour palette ────────────────────────────────────────────────
// Ten distinct hues; opacity is applied via CSS custom property on each card
const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#059669', '#d97706', '#dc2626',
  '#0891b2', '#7c2d12', '#4f46e5', '#0f766e', '#b91c1c',
];
const DEFAULT_TICKET_PAGE_SIZE = 12;

// ── State ─────────────────────────────────────────────────────────────────
let analyses: Analysis[] = [];
let selectedId: string | null = null;
const pollingTimers = new Map<string, ReturnType<typeof setInterval>>();

interface TicketExplorerState {
  analysisId: string | null;
  query: string;
  page: TicketSearchResponse | null;
  loading: boolean;
  error: string | null;
  selectedKey: string | null;
  selectedTicket: TicketDetail | null;
  detailLoading: boolean;
  detailError: string | null;
}

let ticketExplorer = createTicketExplorerState();

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

function createTicketExplorerState(analysisId: string | null = null): TicketExplorerState {
  return {
    analysisId,
    query: '',
    page: null,
    loading: false,
    error: null,
    selectedKey: null,
    selectedTicket: null,
    detailLoading: false,
    detailError: null,
  };
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

  let analysis = analyses.find((a) => a.id === id)!;

  if (ticketExplorer.analysisId !== id) {
    ticketExplorer = createTicketExplorerState(analysis.status === 'completed' ? id : null);
  }

  renderResults(analysis);

  if (analysis.status === 'pending' || analysis.status === 'running') {
    startPolling(id);
    return;
  }

  if (analysis.status === 'completed' && !analysis.clusters) {
    const full = await getAnalysis(id);
    updateAnalysis(full);
    analysis = full;
  }

  renderResults(analysis);

  if (analysis.status === 'completed') {
    await ensureTicketExplorer(analysis.id);
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
    ${renderTicketWorkspace(analysis)}
    <div class="clusters-grid">
      ${clusters.map((c, i) => renderClusterCard(c, i)).join('')}
    </div>`;

  attachCompletedAnalysisListeners(analysis);
}

function renderClusterCard(c: ClusterInfo, index: number): string {
  const color = CLUSTER_COLORS[index % CLUSTER_COLORS.length];
  const pct = c.percentage ?? 0;
  const keywords = (c.keywords ?? [])
    .map((k) => `<span class="keyword-tag">${esc(k)}</span>`)
    .join('');
  const tickets = (c.representative_tickets ?? [])
    .map(
      (t) => `<button type="button" class="ticket-jump-btn" data-ticket-key="${esc(t.key)}">
        <span class="ticket-key">${esc(t.key)}</span>
        <span class="ticket-summary">${esc(t.summary)}</span>
      </button>`
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

function renderTicketWorkspace(analysis: Analysis): string {
  const explorer = ticketExplorer.analysisId === analysis.id
    ? ticketExplorer
    : createTicketExplorerState(analysis.id);
  const page = explorer.page;
  const resultCount = page?.items.length ?? 0;
  const from = page && resultCount > 0 ? page.offset + 1 : 0;
  const to = page && resultCount > 0 ? page.offset + resultCount : 0;
  const queryLabel = explorer.query
    ? `Top semantic matches for "${esc(explorer.query)}"`
    : 'Browse embedded tickets or run a semantic search';

  return `
    <div class="ticket-workspace">
      <div class="card">
        <div class="results-header">
          <div>
            <h2>Semantic Ticket Search</h2>
            <div class="subtle-copy">Search across the stored embeddings for this analysis and open any ticket detail.</div>
          </div>
        </div>
        <form id="ticket-search-form" class="ticket-search-form" novalidate>
          <input
            id="ticket-search-input"
            class="ticket-search-input"
            type="search"
            placeholder="Try: login reset problems, reporting export failures, sync timeouts"
            value="${esc(explorer.query)}"
          />
          <button type="submit" class="btn-accent" ${explorer.loading ? 'disabled' : ''}>
            ${explorer.loading ? 'Searching...' : 'Semantic Search'}
          </button>
          <button
            type="button"
            class="btn-ghost"
            id="ticket-search-clear"
            ${!explorer.query && (!page || page.offset === 0) ? 'disabled' : ''}
          >
            Clear
          </button>
        </form>
        <div class="ticket-search-summary-bar">
          <span>${queryLabel}</span>
          ${page ? `<span>${from}-${to} of ${page.total}</span>` : ''}
        </div>
        ${renderTicketSearchResults(explorer)}
        ${renderTicketPager(explorer)}
      </div>
      <div class="card ticket-detail-card">
        ${renderTicketDetail(explorer)}
      </div>
    </div>`;
}

function renderTicketSearchResults(explorer: TicketExplorerState): string {
  if (explorer.loading && !explorer.page) {
    return `
      <div class="empty-state ticket-loading-state">
        <span class="spinner"></span>
        <span>Ranking embedded tickets...</span>
      </div>`;
  }

  if (explorer.error) {
    return `<div class="error-box" style="margin-top:1rem">${esc(explorer.error)}</div>`;
  }

  if (!explorer.page || explorer.page.items.length === 0) {
    return `
      <div class="empty-state ticket-empty-state">
        ${explorer.query
          ? '<p>No embedded tickets matched that query.</p><p>Try a broader concept or shorter phrase.</p>'
          : '<p>No embedded tickets are available yet for this analysis.</p>'}
      </div>`;
  }

  return `
    <div class="ticket-results-list">
      ${explorer.page.items.map((item) => renderTicketResultItem(item, explorer.selectedKey === item.jira_key)).join('')}
    </div>`;
}

function renderTicketResultItem(item: TicketSearchItem, isActive: boolean): string {
  const meta = [item.issue_type, item.priority, item.ticket_status]
    .filter(Boolean)
    .map((part) => esc(part!))
    .join(' · ');
  const score = item.similarity_score !== undefined
    ? `${Math.round(item.similarity_score * 100)}% match`
    : '';

  return `
    <button
      type="button"
      class="ticket-search-item${isActive ? ' active' : ''}"
      data-ticket-key="${esc(item.jira_key)}"
    >
      <div class="ticket-search-item-top">
        <div class="ticket-search-item-heading">
          <span class="ticket-key">${esc(item.jira_key)}</span>
          ${item.cluster_label ? `<span class="ticket-cluster-pill">${esc(item.cluster_label)}</span>` : ''}
        </div>
        ${score ? `<span class="ticket-score">${score}</span>` : ''}
      </div>
      <div class="ticket-search-summary">${esc(item.summary)}</div>
      ${item.description_preview ? `<div class="ticket-search-preview">${esc(item.description_preview)}</div>` : ''}
      ${meta ? `<div class="ticket-search-meta">${meta}</div>` : ''}
    </button>`;
}

function renderTicketPager(explorer: TicketExplorerState): string {
  const page = explorer.page;
  if (!page || page.total <= page.limit) return '';

  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + page.items.length < page.total;

  return `
    <div class="ticket-pager">
      <span class="ticket-pager-meta">Page ${Math.floor(page.offset / page.limit) + 1}</span>
      <div class="ticket-pager-actions">
        <button type="button" class="btn-ghost" id="ticket-page-prev" ${!hasPrevious || explorer.loading ? 'disabled' : ''}>Previous</button>
        <button type="button" class="btn-ghost" id="ticket-page-next" ${!hasNext || explorer.loading ? 'disabled' : ''}>Next</button>
      </div>
    </div>`;
}

function renderTicketDetail(explorer: TicketExplorerState): string {
  if (explorer.detailLoading && !explorer.selectedTicket) {
    return `
      <div class="empty-state ticket-loading-state">
        <span class="spinner"></span>
        <span>Loading ticket detail...</span>
      </div>`;
  }

  if (explorer.detailError) {
    return `<div class="error-box">${esc(explorer.detailError)}</div>`;
  }

  if (!explorer.selectedTicket) {
    return `
      <div class="empty-state ticket-detail-empty">
        <p style="font-size:1.9rem;margin-bottom:.5rem">-></p>
        <p>Select a search result or a representative ticket to inspect the embedded issue detail.</p>
      </div>`;
  }

  const ticket = explorer.selectedTicket;
  const meta = [
    ticket.issue_type ? `Type: ${ticket.issue_type}` : null,
    ticket.priority ? `Priority: ${ticket.priority}` : null,
    ticket.ticket_status ? `Status: ${ticket.ticket_status}` : null,
    ticket.cluster_label ? `Cluster: ${ticket.cluster_label}` : null,
  ].filter(Boolean) as string[];

  return `
    <div class="ticket-detail-header">
      <div>
        <div class="ticket-detail-kicker">Ticket Detail</div>
        <h2>${esc(ticket.jira_key)}</h2>
      </div>
      <div class="detail-actions">
        <a class="btn-ghost detail-link" href="${esc(ticket.jira_issue_url)}" target="_blank" rel="noreferrer">Open in Jira</a>
      </div>
    </div>
    <div class="ticket-detail-summary">${esc(ticket.summary)}</div>
    ${meta.length ? `<div class="ticket-detail-meta">${meta.map((item) => `<span class="detail-pill">${esc(item)}</span>`).join('')}</div>` : ''}
    <div class="ticket-detail-section">
      <div class="ticket-detail-kicker">Description</div>
      <div class="ticket-detail-description">${esc(ticket.description || 'No description was embedded for this ticket.')}</div>
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
    ticketExplorer = createTicketExplorerState(null);
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
      if (selectedId === id) {
        renderResults(updated);
        if (updated.status === 'completed') {
          void ensureTicketExplorer(updated.id);
        }
      }
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

async function ensureTicketExplorer(analysisId: string): Promise<void> {
  if (ticketExplorer.analysisId !== analysisId) {
    ticketExplorer = createTicketExplorerState(analysisId);
  }
  if (ticketExplorer.page || ticketExplorer.loading) {
    renderSelectedAnalysis();
    return;
  }
  await loadTicketPage(analysisId, ticketExplorer.query, 0);
}

async function loadTicketPage(analysisId: string, query: string, offset: number): Promise<void> {
  const previousQuery = ticketExplorer.query;
  const needsAutoSelection = ticketExplorer.analysisId !== analysisId
    || !ticketExplorer.selectedKey
    || previousQuery !== query;

  if (ticketExplorer.analysisId !== analysisId) {
    ticketExplorer = createTicketExplorerState(analysisId);
  }

  ticketExplorer.loading = true;
  ticketExplorer.error = null;
  ticketExplorer.query = query;
  renderSelectedAnalysis();

  try {
    const page = await searchAnalysisTickets(analysisId, {
      query: query || undefined,
      limit: DEFAULT_TICKET_PAGE_SIZE,
      offset,
    });
    ticketExplorer.page = page;
    ticketExplorer.loading = false;
    ticketExplorer.error = null;

    if (page.items.length === 0) {
      ticketExplorer.selectedKey = null;
      ticketExplorer.selectedTicket = null;
      ticketExplorer.detailError = null;
      ticketExplorer.detailLoading = false;
    } else if (needsAutoSelection && offset === 0) {
      ticketExplorer.selectedKey = page.items[0].jira_key;
      ticketExplorer.selectedTicket = null;
      void loadTicketDetail(analysisId, page.items[0].jira_key);
    }
  } catch (err) {
    ticketExplorer.loading = false;
    ticketExplorer.error = String(err instanceof Error ? err.message : err);
  }

  renderSelectedAnalysis();
}

async function loadTicketDetail(analysisId: string, jiraKey: string): Promise<void> {
  if (ticketExplorer.analysisId !== analysisId) {
    ticketExplorer = createTicketExplorerState(analysisId);
  }

  ticketExplorer.selectedKey = jiraKey;
  ticketExplorer.detailLoading = true;
  ticketExplorer.detailError = null;
  renderSelectedAnalysis();

  try {
    ticketExplorer.selectedTicket = await getAnalysisTicket(analysisId, jiraKey);
  } catch (err) {
    ticketExplorer.selectedTicket = null;
    ticketExplorer.detailError = String(err instanceof Error ? err.message : err);
  } finally {
    ticketExplorer.detailLoading = false;
    renderSelectedAnalysis();
  }
}

function attachCompletedAnalysisListeners(analysis: Analysis): void {
  const searchForm = document.getElementById('ticket-search-form') as HTMLFormElement | null;
  searchForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = document.getElementById('ticket-search-input') as HTMLInputElement | null;
    void loadTicketPage(analysis.id, input?.value.trim() ?? '', 0);
  });

  const clearButton = document.getElementById('ticket-search-clear') as HTMLButtonElement | null;
  clearButton?.addEventListener('click', () => {
    const input = document.getElementById('ticket-search-input') as HTMLInputElement | null;
    if (input) input.value = '';
    void loadTicketPage(analysis.id, '', 0);
  });

  document.querySelectorAll<HTMLButtonElement>('.ticket-search-item').forEach((button) => {
    button.addEventListener('click', () => {
      const jiraKey = button.dataset.ticketKey;
      if (!jiraKey) return;
      void loadTicketDetail(analysis.id, jiraKey);
    });
  });

  document.querySelectorAll<HTMLButtonElement>('.ticket-jump-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const jiraKey = button.dataset.ticketKey;
      if (!jiraKey) return;
      void loadTicketDetail(analysis.id, jiraKey);
    });
  });

  const prevButton = document.getElementById('ticket-page-prev') as HTMLButtonElement | null;
  prevButton?.addEventListener('click', () => {
    const page = ticketExplorer.page;
    if (!page) return;
    void loadTicketPage(analysis.id, ticketExplorer.query, Math.max(0, page.offset - page.limit));
  });

  const nextButton = document.getElementById('ticket-page-next') as HTMLButtonElement | null;
  nextButton?.addEventListener('click', () => {
    const page = ticketExplorer.page;
    if (!page) return;
    void loadTicketPage(analysis.id, ticketExplorer.query, page.offset + page.limit);
  });
}

function renderSelectedAnalysis(): void {
  if (!selectedId) return;
  const analysis = analyses.find((item) => item.id === selectedId);
  if (analysis) renderResults(analysis);
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
