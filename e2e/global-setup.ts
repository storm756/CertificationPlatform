import { chromium, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { signIn } from "./support/auth";

// Staff sign in once per run: an authenticator code works only once, so signing the same mentor in
// twice within 30 seconds would be refused. Journeys reuse these saved sessions.
export default async function globalSetup(config: FullConfig) {
  mkdirSync(".auth", { recursive: true });
  const use = config.projects[0].use;
  const browser = await chromium.launch({ channel: use.channel });
  for (const key of ["mentor1", "mentor2", "admin"]) {
    const context = await browser.newContext({ baseURL: use.baseURL });
    const page = await context.newPage();
    await signIn(page, key, true);
    await context.storageState({ path: `.auth/${key}.json` });
    await context.close();
  }
  await browser.close();
}
