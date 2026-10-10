import { expect } from '@playwright/test';

export async function stubBackend(page, { role = 'INDEPENDENT_AUDITOR', uploads = [] } = {}) {
  const storedUploads = uploads.map((item) => ({ ...item }));
  const engagement = { id: 'engagement-fixture', organization_id: 'org-fixture', name: 'Engagement fixture', financial_year: '2025-26', period_start: '2025-04-01', period_end: '2026-03-31', status: 'DATA_PENDING', is_demo: false, created_by: 'user-fixture', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname.replace('/api/v1', ''); const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/auth/login' && method === 'POST') return json({ access_token: 'test-access-token', token_type: 'bearer', expires_in: 900, user: { id: 'user-fixture', email: 'user@example.com', full_name: 'Workspace User', role, is_active: true } });
    if (path === '/auth/me') return json({ id: 'user-fixture', email: 'user@example.com', full_name: 'Workspace User', role, is_active: true });
    if (path === '/organizations') return json([{ id: 'org-fixture', name: 'Organization fixture', is_demo: false }]);
    if (path === '/engagements') return json({ items: [engagement], page: 1, page_size: 100, total: 1 });
    if (path === `/engagements/${engagement.id}/uploads` && method === 'GET') return json({ items: storedUploads, page: 1, page_size: 100, total: storedUploads.length });
    if (path === `/engagements/${engagement.id}/audit-runs`) return json({ items: [], page: 1, page_size: 100, total: 0 });
    if (path === '/ai-audit/evidence') return json({ count: 0, items: [] });
    if (path === `/ai-audit/audit-trail/verify`) return json({ engagement_id: engagement.id, valid: true, event_count: 0 });
    if (path === `/engagements/${engagement.id}/uploads` && method === 'POST') {
      const requestData = request.postDataBuffer()?.toString('binary') || '';
      const name = requestData.match(/filename="([^"]+)"/)?.[1] || 'uploaded-file.csv';
      const item = { id: `upload-${storedUploads.length + 1}`, engagement_id: engagement.id, original_filename: name, extension: name.endsWith('.pdf') ? '.pdf' : '.csv', content_type: 'text/csv', size_bytes: requestData.length, sha256: 'a'.repeat(64), dataset_type: name.endsWith('.pdf') ? 'supporting_document' : 'sales_register', status: 'UPLOADED', row_count: 0, validation_summary: null, created_at: new Date().toISOString() };
      storedUploads.unshift(item); return json(item, 201);
    }
    if (path.startsWith('/uploads/') && path.endsWith('/validate')) { const item = storedUploads.find((upload) => path.includes(upload.id)); if (item) { item.status = 'VALIDATED'; item.validation_summary = { valid: true, error_count: 0, errors: [] }; return json({ upload_id: item.id, status: item.status, valid: true, error_count: 0, errors: [] }); } }
    if (path.startsWith('/uploads/') && path.endsWith('/ingest')) return json({ job_id: 'job-fixture', status: 'SUCCEEDED', row_count: 1, message: 'Ingested records.' }, 202);
    if (path === '/ai-audit/reconcile' && method === 'POST') return json({ run_id: 'reconciliation-fixture', status: 'SUCCEEDED', exception_count: 0, findings: [] }, 201);
    if (path.endsWith('/workpaper')) return json({ report_type: 'TRACE_V2_AUDIT_WORKPAPER', findings: [] });
    return json({ detail: `Unhandled test API request: ${method} ${path}` }, 404);
  });
}

export async function signIntoWorkspace(page, options) {
  await stubBackend(page, options);
  await page.goto('/login');
  await page.getByLabel('Email address').fill('user@example.com');
  await page.getByLabel('Password').fill('backend-password');
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
}
