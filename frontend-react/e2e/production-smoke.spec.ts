import {
  expect,
  openPublicSessionPage,
  sendChatMessage,
  test,
} from './fixtures';

const blockedResponseText = /encountered an issue|connection error|temporarily unavailable|incident id|query limit/i;

test.describe('KRAKEN production smoke', () => {
  test('health endpoint responds', async ({ request, baseURL }) => {
    const response = await request.get(`${baseURL}/health`);
    expect(response.ok()).toBeTruthy();
    expect(await response.text()).toMatch(/ok|healthy|gateway/i);
  });

  test('loads the public synthetic environment shell', async ({ page }) => {
    await openPublicSessionPage(page);
    await expect(page.getByText('KRAKEN', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('SYNTHETIC ENVIRONMENT')).toBeVisible();
    await expect(page.getByPlaceholder('Type your security or helpdesk query...')).toBeVisible();
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
