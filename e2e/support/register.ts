import { type Page } from "@playwright/test";
import { manifest } from "./data";

export const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;

export type Signup = {
  email: string;
  name?: string;
  dob?: string;
  language?: string;
  batch: string;
  guardian?: { name: string; email: string };
};

/** Fill the real registration form (nothing is submitted). */
export async function fillRegistration(page: Page, s: Signup) {
  await page.goto("/register/");
  await page.fill("input[name=certificate_name]", s.name ?? "Journey Person");
  await page.fill("input[name=email]", s.email);
  await page.fill("input[name=password]", manifest.password);
  await page.selectOption("select[name=preferred_language]", s.language ?? "en");
  await page.fill("input[name=date_of_birth]", s.dob ?? "2000-01-01");
  await page.selectOption("select[name=batch]", String(manifest.batches[s.batch]));
  if (s.guardian) {
    await page.fill("input[name=guardian_name]", s.guardian.name);
    await page.fill("input[name=guardian_email]", s.guardian.email);
  }
  await page.check("input[name=accept_privacy]");
}

export const submitRegistration = (page: Page) => page.locator("main form button[type=submit]").last().click();
