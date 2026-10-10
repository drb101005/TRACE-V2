import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('audit-trail verification result is rendered from the backend response', async ({ page }) => {
  await signIntoWorkspace(page);
  await page.getByRole('button', { name: 'Audit trail' }).click();
  await page.getByRole('button', { name: 'Verify backend audit trail' }).click();
  await page.getByText('Verification response').click();
  await expect(page.getByText(/"valid": true/)).toBeVisible();
});
