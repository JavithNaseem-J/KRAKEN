import { expect, test, type Page } from '@playwright/test';

const blockedResponseText = /encountered an issue|connection error|temporarily unavailable|incident id|demo query limit/i;

async function sendChatMessage(page: Page, message: string) {
  const input = page.getByPlaceholder('Type your security or helpdesk query...');
  await expect(input).toBeVisible();
  await input.fill(message);
  await page.getByRole('button', { name: /send/i }).click();
  await expect(page.getByRole('main').getByText(message, { exact: true }).last()).toBeVisible();
  await expect(page.getByText('Agent Processing')).toBeHidden({ timeout: 120_000 });
}

test.describe('KRAKEN production smoke', () => {
  test('health endpoint responds', async ({ request, baseURL }) => {
    const response = await request.get(`${baseURL}/health`);
    expect(response.ok()).toBeTruthy();
    expect(await response.text()).toMatch(/ok|healthy|gateway/i);
  });

  test('loads the public demo shell', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/');
    await expect(page.getByText('KRAKEN', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('DEMO MODE')).toBeVisible();
    await expect(page.getByPlaceholder('Type your security or helpdesk query...')).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });

  test('answers ticket status and VPN FAQ queries', async ({ page }) => {
    await page.goto('/');

    await sendChatMessage(page, 'What is the status of ticket TCK-1001?');
    await expect(
      page.getByRole('main').getByRole('heading', { name: /Ticket Information: TCK-1001/i }),
    ).toBeVisible();
    await expect(page.locator('body')).not.toContainText(blockedResponseText);

    await sendChatMessage(page, 'How do I connect to the corporate VPN?');
    await expect(page.getByRole('main').getByText(/VPN|GlobalProtect|corporate/i).last()).toBeVisible();
    await expect(page.locator('body')).not.toContainText(blockedResponseText);
  });
});
