import type { Analysis, AnalysisCreate } from './types';

const BASE = '';

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
  return request<Analysis>('/api/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export function listAnalyses(): Promise<Analysis[]> {
  return request<Analysis[]>('/api/analyses');
}

export function getAnalysis(id: string): Promise<Analysis> {
  return request<Analysis>(`/api/analyses/${id}`);
}

export function deleteAnalysis(id: string): Promise<void> {
  return request<void>(`/api/analyses/${id}`, { method: 'DELETE' });
}
