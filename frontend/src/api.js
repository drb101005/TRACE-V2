// Use the same host as the UI by default so LAN/device access does not send
// browser requests back to that device's own localhost. Set VITE_API_BASE_URL
// when the API is hosted on a different domain or port.
const defaultApiHost = typeof window === 'undefined' ? 'localhost' : window.location.hostname;
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || `http://${defaultApiHost}:8000/api/v1`).replace(/\/$/, '');

export async function apiRequest(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.error?.message || payload?.detail?.message || payload?.detail || `Request failed (${response.status})`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return payload;
}

const json = (method, value) => ({ method, body: JSON.stringify(value) });
export const signIn = (email, password) => apiRequest('/auth/login', json('POST', { email, password }));
export const getMe = (token) => apiRequest('/auth/me', { token });
export const getOrganizations = (token) => apiRequest('/organizations', { token });
export const createEngagement = (token, value) => apiRequest('/engagements', { ...json('POST', value), token });
export const getEngagements = async (token) => {
  const payload = await apiRequest('/engagements?page=1&page_size=100', { token });
  // Support both the paginated API shape and a plain array response.
  const items = Array.isArray(payload) ? payload : payload?.items ?? payload?.data?.items;
  if (!Array.isArray(items)) throw new Error('The engagements endpoint returned an unexpected response. Expected an items list.');
  return { ...(Array.isArray(payload) ? {} : payload), items };
};
export const getUploads = (token, id) => apiRequest(`/engagements/${encodeURIComponent(id)}/uploads?page=1&page_size=100`, { token });
export const uploadFile = (token, id, file, datasetType) => {
  const body = new FormData(); body.append('file', file); body.append('dataset_type', datasetType);
  return apiRequest(`/engagements/${encodeURIComponent(id)}/uploads`, { method: 'POST', token, body });
};
export const validateUpload = (token, id) => apiRequest(`/uploads/${encodeURIComponent(id)}/validate`, { method: 'POST', token });
export const ingestUpload = (token, id) => apiRequest(`/uploads/${encodeURIComponent(id)}/ingest`, { method: 'POST', token });
export const getPreview = (token, id) => apiRequest(`/uploads/${encodeURIComponent(id)}/preview?limit=20`, { token });
export const getMapping = (token, id) => apiRequest(`/uploads/${encodeURIComponent(id)}/mappings`, { token });
export const saveMapping = (token, id, mapping) => apiRequest(`/uploads/${encodeURIComponent(id)}/mappings`, { ...json('PUT', mapping), token });
export const getAuditRuns = (token, engagementId) => apiRequest(`/engagements/${encodeURIComponent(engagementId)}/audit-runs?page=1&page_size=100`, { token });
export const createAuditRun = (token, engagementId, uploadId) => apiRequest(`/engagements/${encodeURIComponent(engagementId)}/audit-runs?upload_id=${encodeURIComponent(uploadId)}`, { method: 'POST', token });
export const getAuditFindings = (token, runId) => apiRequest(`/audit-runs/${encodeURIComponent(runId)}/findings?page=1&page_size=100`, { token });
export const reconcile = (token, body) => apiRequest('/ai-audit/reconcile', { ...json('POST', body), token });
export const verifyAuditTrail = (token, engagementId) => apiRequest(`/ai-audit/audit-trail/verify?engagement_id=${encodeURIComponent(engagementId)}`, { token });
export const getWorkpaper = (token, runId) => apiRequest(`/audit-runs/${encodeURIComponent(runId)}/workpaper`, { token });
export const createEvidence = (token, body) => apiRequest('/ai-audit/evidence', { ...json('POST', body), token });
export const verifyEvidence = (token, evidenceId, body) => apiRequest(`/ai-audit/evidence/${encodeURIComponent(evidenceId)}/verify`, { ...json('POST', body), token });
export const sampleUpload = (token, body) => apiRequest('/ai-audit/sample-sales-tod', { ...json('POST', body), token });
