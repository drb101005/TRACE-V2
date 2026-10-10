import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('selected file is sent to the backend upload endpoint', async ({ page }) => {
  await signIntoWorkspace(page, { role: 'CLIENT_EMPLOYEE' });
  await page.getByRole('button', { name: 'Evidence & uploads' }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: 'source-register.csv', mimeType: 'text/csv', buffer: Buffer.from('invoice_number,invoice_date,customer_name,total_amount\nA-1,2025-04-01,North Co,1200\n') });
  await page.getByRole('button', { name: 'Upload to selected engagement' }).click();
  await expect(page.getByRole('status')).toContainText('File upload was accepted and stored by the backend.');
  await expect(page.getByText('source-register.csv')).toBeVisible();
});
