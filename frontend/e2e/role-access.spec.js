import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('workspace uses the authenticated backend role to restrict actions', async ({ page }) => {
  await signIntoWorkspace(page, { role: 'CLIENT_EMPLOYEE' });
  await expect(page.getByText('BACKEND SESSION')).toBeVisible();
  await page.getByRole('button', { name: 'Reconciliation' }).click();
  await expect(page.getByText('Your backend role does not have reconciliation permission.')).toBeVisible();
});
