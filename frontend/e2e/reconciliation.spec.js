import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

const uploads = [
  { id: 'sales-fixture', engagement_id: 'engagement-fixture', original_filename: 'sales.csv', extension: '.csv', size_bytes: 10, sha256: 'a'.repeat(64), dataset_type: 'sales_register', status: 'UPLOADED', row_count: 1, validation_summary: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'ledger-fixture', engagement_id: 'engagement-fixture', original_filename: 'ledger.xlsx', extension: '.xlsx', size_bytes: 10, sha256: 'b'.repeat(64), dataset_type: 'general_ledger', status: 'UPLOADED', row_count: 1, validation_summary: null, created_at: '2026-01-01T00:00:00Z' },
];

test('reconciliation sends selected backend uploads and displays the response', async ({ page }) => {
  await signIntoWorkspace(page, { uploads });
  await page.getByRole('button', { name: 'Reconciliation' }).click();
  await page.getByRole('button', { name: 'Run backend reconciliation' }).click();
  await page.getByText('Reconciliation result').click();
  await expect(page.getByText(/"run_id": "reconciliation-fixture"/)).toBeVisible();
});
