import { expect, type Browser, type Page } from "@playwright/test";
import { manifest, user } from "./data";
import { totp } from "./totp";

/** Sign in through the real sign-in page. Staff accounts also give the authenticator code. */
export async function signIn(page: Page, key: string, staff = false) {
  await page.goto("/accounts/login/");
  await page.fill("input[name=login]", user(key));
  await page.fill("input[name=password]", manifest.password);
  await page.click("main button[type=submit]");
  if (staff) {
    await page.waitForURL(/\/2fa\/authenticate/);
    // A code works once. If this account signed in within the same 30 s step (a quick re-run),
    // the site refuses it: wait for the next step and try again.
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.fill("input[name=code]", totp(manifest.totp_secret));
      await page.click("main button[type=submit]");
      const left = await page.waitForURL((u) => !/2fa/.test(u.pathname), { timeout: 4000 }).then(() => 0, () => 1);
      if (!left) break;
      await page.waitForTimeout(30_500 - (Date.now() % 30_000));
    }
  }
  await expect(page).not.toHaveURL(/\/accounts\/login|\/2fa\//);
}

export async function signOut(page: Page) {
  await page.context().clearCookies();
}

/** A new browser context already signed in as mentor1, mentor2 or admin (saved by global-setup). */
export async function staffPage(browser: Browser, key: "mentor1" | "mentor2" | "admin") {
  const context = await browser.newContext({ storageState: `.auth/${key}.json` });
  return context.newPage();
}

/** After confirming an e-mail address: sign in if the confirmation did not already (both happen). */
export async function signInIfAsked(page: Page, email: string) {
  await page.waitForURL(/accounts\/login|exam\/|start|waiting|learn/);
  if (!/accounts\/login/.test(page.url())) return;
  await page.fill("input[name=login]", email);
  await page.fill("input[name=password]", manifest.password);
  await page.click("main button[type=submit]");
}
