import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('sign-off is reported unavailable when the backend has no action', async ({ page }) => {
  await signIntoWorkspace(page);
  await page.getByRole('button', { name: 'Sign-off' }).click();
  await expect(page.getByRole('heading', { name: 'Sign-off is unavailable' })).toBeVisible();
  await expect(page.getByText('There is no backend action to submit here.')).toBeVisible();
});
