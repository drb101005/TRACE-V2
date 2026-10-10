import { test, expect } from '@playwright/test';
import { signIntoWorkspace } from './helpers.js';

test('workpaper view has a backend empty state until an audit run exists', async ({ page }) => {
  await signIntoWorkspace(page);
  await page.getByRole('button', { name: 'Workpaper' }).click();
  await expect(page.getByRole('heading', { name: 'Backend workpaper export' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load workpaper' })).toBeDisabled();
});
