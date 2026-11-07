import type {
  AnalysisResponse,
  AnalyzeRequest,
  EngineeringRequest,
  EngineeringResult,
  MigrationPlan,
} from './types';

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

async function post<T>(path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(`Cannot reach the MigrateAI API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as T;
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`);
  } catch {
    throw new Error(`Cannot reach the MigrateAI API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as T;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, '')).filter(Boolean).join('; ');
    }
  } catch {
    // fall through
  }
  return `Request failed (${res.status})`;
}

export function analyzeRepository(request: AnalyzeRequest): Promise<AnalysisResponse> {
  return post<AnalysisResponse>('/analyze', request);
}

export function analyzeSample(): Promise<AnalysisResponse> {
  return post<AnalysisResponse>('/analyze/sample');
}

export function getMigrationPlan(analysisId: string): Promise<MigrationPlan> {
  return get<MigrationPlan>(`/analysis/${analysisId}/plan`);
}

export function runMigrationPlan(analysisId: string): Promise<MigrationPlan> {
  return post<MigrationPlan>(`/analysis/${analysisId}/migrate`);
}

export function runEngineering(
  analysisId: string,
  request?: EngineeringRequest
): Promise<EngineeringResult> {
  return post<EngineeringResult>(`/analysis/${analysisId}/engineer`, request);
}

export function getMigration(migrationId: string): Promise<EngineeringResult> {
  return get<EngineeringResult>(`/migration/${migrationId}`);
}

export function getMigrationDiff(migrationId: string): Promise<Record<string, string>> {
  return get<Record<string, string>>(`/migration/${migrationId}/diff`);
}
