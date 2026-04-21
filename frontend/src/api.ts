import type { Analysis, AnalysisCreate, TicketDetail, TicketSearchResponse } from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function createAnalysis(data: AnalysisCreate): Promise<Analysis> {
  return request<Analysis>('/api/analyses/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export function listAnalyses(): Promise<Analysis[]> {
  return request<Analysis[]>('/api/analyses/');
}

export function getAnalysis(id: string): Promise<Analysis> {
  return request<Analysis>(`/api/analyses/${id}`);
}

export function deleteAnalysis(id: string): Promise<void> {
  return request<void>(`/api/analyses/${id}`, { method: 'DELETE' });
}

export function searchAnalysisTickets(
  analysisId: string,
  params: { query?: string; limit?: number; offset?: number } = {},
): Promise<TicketSearchResponse> {
  const searchParams = new URLSearchParams();
  if (params.query) searchParams.set('query', params.query);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
  const suffix = searchParams.size ? `?${searchParams.toString()}` : '';
  return request<TicketSearchResponse>(`/api/analyses/${analysisId}/tickets${suffix}`);
}

export function getAnalysisTicket(analysisId: string, jiraKey: string): Promise<TicketDetail> {
  return request<TicketDetail>(`/api/analyses/${analysisId}/tickets/by-key/${encodeURIComponent(jiraKey)}`);
}
