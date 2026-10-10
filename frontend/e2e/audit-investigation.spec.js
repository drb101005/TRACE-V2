import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('findings view reports the backend empty state when no runs exist', async ({ page }) => {
  await signIntoWorkspace(page);
  await page.getByRole('button', { name: 'Findings' }).click();
  await expect(page.getByRole('heading', { name: 'Persisted audit findings' })).toBeVisible();
  await expect(page.getByText('Select an audit run to load its findings.')).toBeVisible();
});
