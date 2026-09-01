import { expect, test, type Page } from '@playwright/test';

const blockedResponseText = /encountered an issue|connection error|temporarily unavailable|incident id|query limit/i;

async function openPublicSessionPage(page: Page) {
  const sessionReady = page.waitForResponse(
    (response) =>
      response.url().endsWith('/v1/session') &&
      response.request().method() === 'POST' &&
      response.ok(),
  );
  await page.goto('/');
  await sessionReady;
  await expect(page.getByPlaceholder('Type your security or helpdesk query...')).toBeVisible();
}

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

  test('loads the public synthetic environment shell', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await openPublicSessionPage(page);
    await expect(page.getByText('KRAKEN', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('SYNTHETIC ENVIRONMENT')).toBeVisible();
    await expect(page.getByPlaceholder('Type your security or helpdesk query...')).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });

  test('answers ticket status and VPN FAQ queries', async ({ page }) => {
    await openPublicSessionPage(page);

    await sendChatMessage(page, 'What is the status of ticket TCK-24001?');
    await expect(
      page.getByRole('main').getByRole('heading', { name: /Ticket Information: TCK-24001/i }),
    ).toBeVisible();
    await expect(page.locator('body')).not.toContainText(blockedResponseText);

    await sendChatMessage(page, 'How do I connect to the corporate VPN?');
    await expect(
      page.getByRole('main').getByText(/GlobalProtect|vpn\.northstar\.example|MFA/i).last(),
    ).toBeVisible();
    await expect(page.locator('body')).not.toContainText(blockedResponseText);
  });
});
