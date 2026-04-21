const { chromium } = require('playwright');

const env = (name, fallback = '') => process.env[name] || fallback;

const config = {
  baseUrl: env('JIRA_BASE_URL', 'http://jira:8080').replace(/\/$/, ''),
  license: env('JIRA_LICENSE'),
  adminUsername: env('JIRA_ADMIN_USERNAME', 'admin'),
  adminPassword: env('JIRA_ADMIN_PASSWORD', 'adminadmin'),
  adminFullName: env('JIRA_ADMIN_FULL_NAME', 'Clusterizer Admin'),
  adminEmail: env('JIRA_ADMIN_EMAIL', 'admin@example.com'),
  title: env('JIRA_TITLE', 'Clusterizer Test Jira'),
  projectKey: env('JIRA_PROJECT_KEY', 'CLSTR'),
  projectName: env('JIRA_PROJECT_NAME', 'Clusterizer Test Project'),
  dbHost: env('JIRA_DB_HOST', 'jira-db'),
  dbPort: env('JIRA_DB_PORT', '5432'),
  dbName: env('JIRA_DB_NAME', 'jiradb'),
  dbUsername: env('JIRA_DB_USERNAME', 'jira'),
  dbPassword: env('JIRA_DB_PASSWORD', 'jira'),
  stopAfter: env('JIRA_SETUP_STOP_AFTER', '').toLowerCase(),
};

const seedIssues = [
  {
    summary: 'Login fails for SSO users after session timeout',
    description: 'Users are redirected back to the login screen after their SSO session expires.',
    issueType: 'Bug',
  },
  {
    summary: 'Password reset email is not delivered',
    description: 'Reset emails intermittently fail when usernames contain uppercase characters.',
    issueType: 'Bug',
  },
  {
    summary: 'Dashboard takes more than 12 seconds to load',
    description: 'Large projects trigger expensive queries and the dashboard becomes slow.',
    issueType: 'Bug',
  },
  {
    summary: 'Search results timeout when filtering by assignee and priority',
    description: 'Compound filters degrade query performance and eventually time out.',
    issueType: 'Bug',
  },
  {
    summary: 'Dark mode toggle resets after page refresh',
    description: 'The UI does not persist the theme selection in local storage.',
    issueType: 'Bug',
  },
  {
    summary: 'Sidebar overlaps content at 150% browser zoom',
    description: 'The layout breaks and hides the issue details panel at high zoom levels.',
    issueType: 'Bug',
  },
];

function log(message) {
  console.log(`[jira-setup] ${message}`);
}

async function waitForJira(page) {
  const url = `${config.baseUrl}/secure/SetupDatabase!default.jspa`;
  for (let attempt = 1; attempt <= 60; attempt += 1) {
    try {
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      const title = await page.title().catch(() => '');
      const body = await page.locator('body').innerText().catch(() => '');
      if (response && response.ok() && /jira setup/i.test(title + body)) {
        log(`Jira setup page ready after ${attempt} attempts.`);
        return;
      }
    } catch (error) {
      log(`Waiting for Jira (${attempt}/60): ${error.message}`);
    }
    await page.waitForTimeout(10_000);
  }
  throw new Error('Timed out waiting for Jira setup page');
}

async function waitForHeading(page, heading, timeout = 300_000) {
  await page.getByRole('heading', { name: new RegExp(heading, 'i') }).waitFor({ timeout });
}

async function detectStep(page) {
  const url = page.url();
  const body = await page.locator('body').innerText().catch(() => '');
  const combined = `${url}\n${body}`;

  if (/SetupDatabase|Database setup/i.test(combined)) return 'database';
  if (/SetupApplicationProperties|application properties/i.test(combined)) return 'application';
  if (/SetupLicense|license key/i.test(combined)) return 'license';
  if (/SetupAdministrator|administrator/i.test(combined)) return 'administrator';
  if (/SetupMailNotifications|mail notifications|email notifications/i.test(combined)) return 'mail';
  return 'ready';
}

async function completeDatabaseSetup(page) {
  await waitForHeading(page, 'Database setup');

  const databaseType = page.getByRole('combobox', { name: 'Database Type' });
  await databaseType.fill('PostgreSQL');
  await page.getByRole('option', { name: /^PostgreSQL$/ }).click();

  await page.getByRole('textbox', { name: 'Hostname' }).fill(config.dbHost);
  await page.getByRole('textbox', { name: 'Port' }).fill(config.dbPort);
  await page.getByRole('textbox', { name: 'Database' }).fill(config.dbName);
  await page.getByRole('textbox', { name: 'Username' }).fill(config.dbUsername);
  await page.getByRole('textbox', { name: 'Password' }).fill(config.dbPassword);

  await page.getByRole('button', { name: 'Test Connection' }).click();
  await page.getByText(/connection test was successful/i).waitFor({ timeout: 120_000 });

  if (config.stopAfter === 'database') {
    log('Stopping after database setup as requested.');
    return false;
  }

  await Promise.all([
    page.waitForURL(/SetupApplicationProperties/i, { timeout: 300_000 }),
    page.getByRole('button', { name: 'Next' }).click(),
  ]);
  return true;
}

async function completeApplicationProperties(page) {
  await waitForHeading(page, 'Set up application properties');
  await page.locator('input[name="title"]').fill(config.title);
  await page.locator('input[name="baseURL"]').fill(config.baseUrl);

  if (config.stopAfter === 'application') {
    log('Stopping after application properties as requested.');
    return false;
  }

  await Promise.all([
    page.waitForURL(/SetupLicense/i, { timeout: 300_000 }),
    page.getByRole('button', { name: /next|submit/i }).click(),
  ]);
  return true;
}

async function completeLicense(page) {
  await waitForHeading(page, 'Specify your license key');

  if (config.stopAfter === 'license') {
    log('Stopping after reaching the license step as requested.');
    return false;
  }

  if (!config.license) {
    throw new Error('JIRA_LICENSE must be set to complete real Jira provisioning');
  }

  await page.locator('#setupLicenseKey').fill(config.license);
  await Promise.all([
    page.waitForURL(/SetupAdministrator/i, { timeout: 300_000 }),
    page.getByRole('button', { name: /submit|next/i }).click(),
  ]);
  return true;
}

async function completeAdministratorSetup(page) {
  await waitForHeading(page, 'administrator');

  const fieldNames = [
    ['Username', config.adminUsername],
    ['Password', config.adminPassword],
    ['Confirm Password', config.adminPassword],
    ['Full Name', config.adminFullName],
    ['Email', config.adminEmail],
  ];

  for (const [label, value] of fieldNames) {
    const locator = page.getByLabel(new RegExp(label, 'i')).first();
    await locator.fill(value);
  }

  if (config.stopAfter === 'administrator') {
    log('Stopping after administrator setup as requested.');
    return false;
  }

  await Promise.all([
    page.waitForLoadState('domcontentloaded'),
    page.getByRole('button', { name: /next|finish|submit/i }).click(),
  ]);
  return true;
}

async function completeMailStepIfPresent(page) {
  const bodyText = await page.locator('body').innerText();
  if (!/mail|email notifications/i.test(bodyText)) {
    return;
  }

  if (config.stopAfter === 'mail') {
    log('Stopping after mail step as requested.');
    return;
  }

  const candidateButtons = ['Later', 'Skip', 'No', 'Next', 'Finish'];
  for (const name of candidateButtons) {
    const button = page.getByRole('button', { name: new RegExp(`^${name}$`, 'i') }).first();
    if (await button.isVisible().catch(() => false)) {
      await Promise.all([
        page.waitForLoadState('domcontentloaded'),
        button.click(),
      ]);
      return;
    }
  }
}

async function login(page) {
  await page.goto(`${config.baseUrl}/login.jsp`, { waitUntil: 'domcontentloaded', timeout: 120_000 });
  const usernameField = page.locator('#login-form-username, input[name="os_username"]').first();
  const passwordField = page.locator('#login-form-password, input[name="os_password"]').first();

  if (await usernameField.isVisible().catch(() => false)) {
    await usernameField.fill(config.adminUsername);
    await passwordField.fill(config.adminPassword);
    await Promise.all([
      page.waitForLoadState('domcontentloaded'),
      page.locator('#login-form-submit, button[type="submit"]').first().click(),
    ]);
  }
}

async function jiraApi(path, options = {}) {
  const headers = options.headers || {};
  headers.Authorization = `Basic ${Buffer.from(`${config.adminUsername}:${config.adminPassword}`).toString('base64')}`;
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(`${config.baseUrl}${path}`, {
    ...options,
    headers,
  });
  return response;
}

async function ensureProject() {
  const projectResponse = await jiraApi(`/rest/api/2/project/${config.projectKey}`);
  if (projectResponse.status === 200) {
    log(`Project ${config.projectKey} already exists.`);
    return;
  }

  if (projectResponse.status !== 404) {
    throw new Error(`Unexpected project lookup status: ${projectResponse.status}`);
  }

  const createResponse = await jiraApi('/rest/api/2/project', {
    method: 'POST',
    body: JSON.stringify({
      key: config.projectKey,
      name: config.projectName,
      projectTypeKey: 'business',
      projectTemplateKey: 'com.atlassian.jira-core-project-templates:jira-core-simplified-project-management',
      lead: config.adminUsername,
      assigneeType: 'PROJECT_LEAD',
    }),
  });

  if (!createResponse.ok()) {
    throw new Error(`Failed to create Jira project: ${createResponse.status} ${await createResponse.text()}`);
  }
  log(`Created project ${config.projectKey}.`);
}

async function ensureIssues() {
  const searchResponse = await jiraApi(`/rest/api/2/search?jql=${encodeURIComponent(`project = ${config.projectKey}`)}`);
  if (!searchResponse.ok()) {
    throw new Error(`Failed to query existing Jira issues: ${searchResponse.status} ${await searchResponse.text()}`);
  }
  const existing = await searchResponse.json();
  if ((existing.total || 0) >= seedIssues.length) {
    log(`Jira already has ${existing.total} seeded issues.`);
    return;
  }

  for (const issue of seedIssues) {
    const createIssueResponse = await jiraApi('/rest/api/2/issue', {
      method: 'POST',
      body: JSON.stringify({
        fields: {
          project: { key: config.projectKey },
          summary: issue.summary,
          description: issue.description,
          issuetype: { name: issue.issueType },
        },
      }),
    });

    if (!createIssueResponse.ok()) {
      throw new Error(
        `Failed to create Jira issue "${issue.summary}": ${createIssueResponse.status} ${await createIssueResponse.text()}`
      );
    }
  }

  log(`Created ${seedIssues.length} Jira issues.`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await waitForJira(page);
    while (true) {
      const step = await detectStep(page);
      log(`Detected Jira setup step: ${step}`);

      if (step === 'database') {
        if (!(await completeDatabaseSetup(page))) return;
        continue;
      }
      if (step === 'application') {
        if (!(await completeApplicationProperties(page))) return;
        continue;
      }
      if (step === 'license') {
        if (!(await completeLicense(page))) return;
        continue;
      }
      if (step === 'administrator') {
        if (!(await completeAdministratorSetup(page))) return;
        continue;
      }
      if (step === 'mail') {
        await completeMailStepIfPresent(page);
        continue;
      }
      break;
    }

    await login(page);
    await ensureProject();
    await ensureIssues();
    log('Real Jira provisioning completed.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`[jira-setup] ${error.stack || error.message}`);
  process.exit(1);
});
