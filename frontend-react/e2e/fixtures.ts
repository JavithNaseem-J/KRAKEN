import { expect, test as base, type Locator, type Page } from '@playwright/test';

export const test = base.extend<{ runtimeErrors: string[] }>({
  runtimeErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error') errors.push(`console: ${message.text()}`);
      });
      page.on('pageerror', (error) => errors.push(`page: ${error.message}`));
      await use(errors);
      expect(errors, 'unexpected browser runtime errors').toEqual([]);
    },
    { auto: true },
  ],
});

export { expect } from '@playwright/test';

export interface StreamResult {
  events: unknown[];
  response: Record<string, unknown>;
}

interface ApiFixtureState {
  approvalIp: string;
  approvalStatus: 'PENDING' | 'APPROVED' | 'REJECTED';
  cacheQueries: Map<string, number>;
  persona: string;
}

const SESSION_ID = 'browser-contract-session';
const APPROVAL_ID = 'browser-contract-approval';
const DATASET_GENERATION = 'northstar-v1';

export async function installKrakenApiFixture(page: Page): Promise<void> {
  const state: ApiFixtureState = {
    approvalIp: '198.51.100.44',
    approvalStatus: 'PENDING',
    cacheQueries: new Map(),
    persona: 'tier1_analyst',
  };

  await page.route(/\/v1\/session$/, async (route) => {
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: SESSION_ID,
        csrf_token: 'browser-contract-csrf-token',
        persona: state.persona,
        actor_id: 'synthetic-alice',
        expires_at: '2030-01-01T00:00:00Z',
        query_limit: 20,
        write_limit: 5,
        dataset_generation: DATASET_GENERATION,
        synthetic_environment: true,
      }),
    });
  });

  await page.route(/\/v1\/session\/persona$/, async (route) => {
    const request = route.request().postDataJSON() as { persona?: string };
    state.persona = request.persona ?? state.persona;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ persona: state.persona }),
    });
  });

  await page.route(/\/v1\/session\/status$/, async (route) => {
    const response =
      state.approvalStatus === 'PENDING'
        ? pendingApprovalResponse()
        : state.approvalStatus === 'APPROVED'
          ? approvedActionResponse()
          : { status: 'rejected', session_id: SESSION_ID };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });

  await page.route(/\/v1\/run\/stream$/, async (route) => {
    const request = route.request().postDataJSON() as { message?: string };
    const message = request.message ?? '';
    if (/ignore previous instructions|reveal your system prompt/i.test(message)) {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'prompt_injection', error: 'Prompt injection blocked.' }),
      });
      return;
    }

    let response: Record<string, unknown>;
    if (/quarantine|block .* perimeter/i.test(message)) {
      state.approvalIp = message.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/)?.[0] ?? state.approvalIp;
      state.approvalStatus = 'PENDING';
      response = pendingApprovalResponse();
    } else if (/create .*ticket/i.test(message)) {
      response = queryResponse({
        answer: 'Created synthetic ticket SYN-24051 for Morgan Reed.',
        actionTaken: 'create_ticket',
        actionResult: {
          ticket_id: 'SYN-24051',
          status: 'created',
          synthetic: true,
        },
      });
    } else {
      const normalized = message.trim().toLowerCase();
      const count = state.cacheQueries.get(normalized) ?? 0;
      state.cacheQueries.set(normalized, count + 1);
      response = queryResponse({
        answer:
          'Open GlobalProtect, connect to vpn.northstar.example, and complete MFA. Contact the service desk if the client reports Error 51.',
        sources: ['faq:corporate-vpn'],
        cacheHit: count > 0,
      });
    }

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache' },
      body: sse(response),
    });
  });

  await page.route(new RegExp(`/approve/${APPROVAL_ID}/details$`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        approval_id: APPROVAL_ID,
        action_name: 'quarantine_ip',
        payload: { ip_address: state.approvalIp, synthetic: true },
        risk_level: 'CRITICAL',
        approval_reason:
          'Policy requires human approval before a critical network containment action.',
        synthetic: true,
        dataset_generation: DATASET_GENERATION,
        session_id: SESSION_ID,
        status: state.approvalStatus,
        created_at: new Date().toISOString(),
        initiator_id: 'synthetic-alice',
        initiator_role: 'tier1_analyst',
        csrf_token: 'browser-contract-approval-csrf',
      }),
    });
  });

  await page.route(new RegExp(`/approve/${APPROVAL_ID}/decision$`), async (route) => {
    const decision = new URLSearchParams(route.request().postData() ?? '').get('decision');
    state.approvalStatus = decision === 'approve' ? 'APPROVED' : 'REJECTED';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: SESSION_ID,
        status: state.approvalStatus.toLowerCase(),
        ...(decision === 'approve' ? { agent_response: approvedActionResponse() } : {}),
      }),
    });
  });
}

export async function openPublicSessionPage(page: Page): Promise<void> {
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

export async function sendChatMessage(page: Page, message: string): Promise<StreamResult> {
  const streamComplete = page.waitForResponse(
    (response) =>
      response.url().endsWith('/v1/run/stream') &&
      response.request().method() === 'POST' &&
      response.ok(),
  );
  const input = page.getByPlaceholder('Type your security or helpdesk query...');
  await input.fill(message);
  await page.getByRole('button', { name: /send/i }).click();
  const streamResponse = await streamComplete;
  await expect(page.getByRole('main').getByText(message, { exact: true }).last()).toBeVisible();
  await expect(page.getByText('Agent Processing')).toBeHidden({ timeout: 120_000 });

  const events = parseSse(await streamResponse.text());
  const terminal = [...events]
    .reverse()
    .find((event) => isRecord(event) && isRecord(event.response));
  if (!isRecord(terminal) || !isRecord(terminal.response)) {
    throw new Error('SSE stream did not contain a terminal response');
  }
  return { events, response: terminal.response };
}

export async function switchPersona(page: Page, label: string): Promise<void> {
  const openSidebar = page.getByRole('button', { name: 'Open Sidebar' });
  if (await openSidebar.isVisible()) await openSidebar.click();

  const transition = page.waitForResponse(
    (response) =>
      response.url().endsWith('/v1/session/persona') &&
      response.request().method() === 'POST' &&
      response.ok(),
  );
  await page.getByRole('button', { name: new RegExp(`^${label}\\b`) }).click();
  await transition;

  if ((page.viewportSize()?.width ?? 1024) < 768) {
    await page.getByRole('button', { name: 'Close Sidebar' }).click();
  }
}

export function assertNoReasoning(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(assertNoReasoning);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, item] of Object.entries(value)) {
    expect(key.toLowerCase()).not.toBe('reasoning');
    assertNoReasoning(item);
  }
}

export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

export async function assertNoOverlap(first: Locator, second: Locator): Promise<void> {
  const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  if (!firstBox || !secondBox) return;

  const overlapsHorizontally =
    firstBox.x < secondBox.x + secondBox.width && secondBox.x < firstBox.x + firstBox.width;
  const overlapsVertically =
    firstBox.y < secondBox.y + secondBox.height && secondBox.y < firstBox.y + firstBox.height;
  expect(overlapsHorizontally && overlapsVertically).toBe(false);
}

function parseSse(body: string): unknown[] {
  return body
    .split('\n')
    .filter((line) => line.startsWith('data: '))
    .map((line) => JSON.parse(line.slice(6)) as unknown);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function pendingApprovalResponse(): Record<string, unknown> {
  return {
    status: 'pending_approval',
    approval_id: APPROVAL_ID,
    session_id: SESSION_ID,
    message: 'Critical network containment requires human approval.',
  };
}

function approvedActionResponse(): Record<string, unknown> {
  return queryResponse({
    answer: 'The synthetic IP quarantine was approved and executed.',
    actionTaken: 'quarantine_ip',
    actionResult: {
      status: 'executed',
      ip_address: '198.51.100.44',
      synthetic: true,
    },
  });
}

function queryResponse({
  answer,
  actionTaken = null,
  actionResult = null,
  sources = [],
  cacheHit = false,
}: {
  answer: string;
  actionTaken?: string | null;
  actionResult?: unknown;
  sources?: string[];
  cacheHit?: boolean;
}): Record<string, unknown> {
  return {
    session_id: SESSION_ID,
    answer,
    action_taken: actionTaken,
    action_result: actionResult,
    sources,
    timestamp: new Date().toISOString(),
    trace_id: 'browser-contract-trace',
    cache: {
      hit: cacheHit,
      scope: 'public',
      knowledge_version: 'v2',
      embedding_model: 'contract-fixture',
      dataset_generation: DATASET_GENERATION,
    },
  };
}

function sse(response: Record<string, unknown>): string {
  return [
    `data: ${JSON.stringify({ node: 'orchestrator', status: 'start' })}`,
    `data: ${JSON.stringify({ node: 'orchestrator', status: 'end', response })}`,
    '',
  ].join('\n\n');
}
