/**
 * Playwright smoke-test for the login page (A0.4.1+).
 *
 * Usage:
 *   npx playwright install chromium   # first time only
 *   node frontend/scripts/verify-login.mjs
 *
 * Requires the dev server running on :3000:
 *   cd frontend && npm run dev
 *
 * Set env var CRED_EMAIL / CRED_PASSWORD to also test the happy path.
 */

import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function waitForServer(maxMs = 15_000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/login`);
      if (res.ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(`Dev server not reachable at ${BASE} after ${maxMs}ms`);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

console.log('Waiting for dev server…');
await waitForServer();

// ── Test 1: wrong credentials show inline error ────────────────────────────
console.log('\n=== 1: Wrong credentials → inline error ===');
await page.goto(`${BASE}/login`);
await page.waitForLoadState('networkidle');
await page.fill('#email', 'wrong@example.com');
await page.fill('#password', 'badpassword123');
await page.click('button[type="submit"]');
await page.waitForTimeout(8000); // Cognito round-trip
const urlAfterBad = page.url();
const pageText = await page.evaluate(() => document.body.innerText);
if (urlAfterBad.includes('/dashboard')) {
  console.log('FAIL  navigated to /dashboard with wrong credentials');
} else if (/incorrect|invalid|username|password|not authorized/i.test(pageText)) {
  const errLine = pageText.split('\n').find(l => /incorrect|invalid|username|password|not authorized/i.test(l));
  console.log('PASS  error shown:', errLine?.trim());
} else {
  console.log('WARN  no recognisable error text found. Page text:', pageText.split('\n').slice(0, 6).join(' | '));
}
await page.screenshot({ path: 'scripts/verify-login-bad-creds.png' });
console.log('      screenshot → scripts/verify-login-bad-creds.png');

// ── Test 2: no tokens in storage ───────────────────────────────────────────
console.log('\n=== 2: No tokens in localStorage / sessionStorage ===');
const storageKeys = await page.evaluate(() => {
  const keys = [];
  for (let i = 0; i < localStorage.length; i++) keys.push('ls:' + localStorage.key(i));
  for (let i = 0; i < sessionStorage.length; i++) keys.push('ss:' + sessionStorage.key(i));
  return keys;
});
const tokenKeys = storageKeys.filter(k => /token|access|id|cognito/i.test(k));
if (tokenKeys.length === 0) {
  console.log('PASS  storage clean:', storageKeys.length ? storageKeys : '(empty)');
} else {
  console.log('FAIL  token-related keys found:', tokenKeys);
}

// ── Test 3: loading state ──────────────────────────────────────────────────
console.log('\n=== 3: Loading state while in-flight ===');
await page.goto(`${BASE}/login`);
await page.fill('#email', 'test@example.com');
await page.fill('#password', 'somepassword');
page.click('button[type="submit"]'); // fire-and-forget
await page.waitForTimeout(400);
const btnText = await page.textContent('button[type="submit"]').catch(() => '?');
const btnDisabled = await page.isDisabled('button[type="submit"]').catch(() => false);
if (btnDisabled || /signing in/i.test(btnText ?? '')) {
  console.log('PASS  button loading:', btnText?.trim(), '| disabled:', btnDisabled);
} else {
  console.log('WARN  loading state not observed (may have resolved too fast)');
}

// ── Test 4: empty submit stays on /login ───────────────────────────────────
console.log('\n=== 4: [probe] Empty submit stays on /login ===');
await page.goto(`${BASE}/login`);
await page.click('button[type="submit"]');
await page.waitForTimeout(300);
const urlEmpty = page.url();
console.log(urlEmpty === `${BASE}/login` ? 'PASS  URL unchanged' : `FAIL  navigated to ${urlEmpty}`);

// ── Test 5 (optional): happy path with real credentials ───────────────────
const { CRED_EMAIL, CRED_PASSWORD } = process.env;
if (CRED_EMAIL && CRED_PASSWORD) {
  console.log('\n=== 5: Happy path — correct credentials → /dashboard ===');
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('#email', CRED_EMAIL);
  await page.fill('#password', CRED_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(8000);

  // Handle new-password-required step if triggered
  const newPwdField = page.locator('#new-password');
  if (await newPwdField.isVisible()) {
    const NEW_PASSWORD = process.env.CRED_NEW_PASSWORD;
    if (!NEW_PASSWORD) {
      console.log('SKIP  new-password step reached but CRED_NEW_PASSWORD not set');
      await page.screenshot({ path: 'scripts/verify-login-good-creds.png' });
      await browser.close();
      process.exit(0);
    }
    console.log('      new-password step triggered — completing challenge…');
    await newPwdField.fill(NEW_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForTimeout(8000);
  }

  const urlAfterGood = page.url();
  if (urlAfterGood.includes('/dashboard')) {
    console.log('PASS  navigated to /dashboard');
    const storageKeysAfter = await page.evaluate(() => {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) keys.push('ls:' + localStorage.key(i));
      for (let i = 0; i < sessionStorage.length; i++) keys.push('ss:' + sessionStorage.key(i));
      return keys;
    });
    const tokenKeysAfter = storageKeysAfter.filter(k => /token|access|id|cognito/i.test(k));
    console.log(tokenKeysAfter.length === 0 ? 'PASS  no tokens in storage after success' : 'FAIL  tokens in storage: ' + tokenKeysAfter);
  } else {
    console.log('FAIL  expected /dashboard, got:', urlAfterGood);
  }
  await page.screenshot({ path: 'scripts/verify-login-good-creds.png' });
  console.log('      screenshot → scripts/verify-login-good-creds.png');
} else {
  console.log('\n=== 5: Happy path skipped (set CRED_EMAIL + CRED_PASSWORD to enable) ===');
}

await browser.close();
console.log('\nDone.');
