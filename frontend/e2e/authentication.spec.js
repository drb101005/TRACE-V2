import { test, expect } from '@playwright/test';
import { signIntoWorkspace, stubBackend } from './helpers.js';

test('login form exposes labelled fields', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByLabel('Email address')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
  await expect(page.getByText(/authentication is handled by the TRACE backend/i)).toBeVisible();
});

test('backend credentials open an authenticated workspace', async ({ page }) => {
  await signIntoWorkspace(page);
  await expect(page.getByText('BACKEND SESSION')).toBeVisible();
  await expect(page.getByRole('button', { name: /Engagement fixture 2025-26/ })).toBeVisible();
});

test('backend rejects invalid credentials in the login form', async ({ page }) => {
  await stubBackend(page);
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Email or password is incorrect.' } }) }));
  await page.goto('/login');
  await page.getByLabel('Email address').fill('user@example.com');
  await page.getByLabel('Password').fill('wrong');
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await expect(page.getByRole('alert')).toContainText('Email or password is incorrect.');
});
