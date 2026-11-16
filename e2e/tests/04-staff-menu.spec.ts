// Pilot hardening: the "Staff tools" menu in the header closes on an outside click or tap, on Escape
// (focus back to its button), when an item is chosen and when the page scrolls; aria-expanded follows.
// Read-only: it opens pages as the seeded admin and changes nothing.
import { test, expect, type Browser, type Page } from "@playwright/test";

const SIZES = [
  { name: "1366", viewport: { width: 1366, height: 900 }, mobile: false },
  { name: "390", viewport: { width: 390, height: 844 }, mobile: true },
];

async function adminAt(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ storageState: ".auth/admin.json", viewport });
  return context.newPage();
}

/** The menu's <details> and its button (<summary>); at 390px the mobile menu is opened first. */
async function menu(page: Page, mobile: boolean) {
  if (mobile) {
    await page.locator(".nav-toggle").click();
    await expect(page.locator("#primary-nav")).toHaveClass(/is-open/);
  }
  const details = page.locator("details[data-staff-menu]");
  const button = details.locator("summary");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  return { details, button };
}

async function open(button: ReturnType<Page["locator"]>, details: ReturnType<Page["locator"]>) {
  await button.click();
  await expect(details).toHaveJSProperty("open", true);
  await expect(button).toHaveAttribute("aria-expanded", "true");
}

async function expectClosed(button: ReturnType<Page["locator"]>, details: ReturnType<Page["locator"]>) {
  await expect(details).toHaveJSProperty("open", false);
  await expect(button).toHaveAttribute("aria-expanded", "false");
}

for (const size of SIZES) {
  test.describe(`staff tools menu at ${size.name}px`, () => {
    test("starts closed, also on a /staff/ page", async ({ browser }) => {
      const page = await adminAt(browser, size.viewport);
      await page.goto("/staff/report/");
      const { details, button } = await menu(page, size.mobile);
      await expectClosed(button, details);
      await page.context().close();
    });

    test("an outside click or tap closes it", async ({ browser }) => {
      const page = await adminAt(browser, size.viewport);
      await page.goto("/");
      const { details, button } = await menu(page, size.mobile);
      await open(button, details);
      if (size.mobile) {
        // A tap on the open mobile menu itself, outside the staff submenu (not on a link).
        await page.locator("#primary-nav").dispatchEvent("click");
      } else {
        const box = await page.locator("main").boundingBox();
        if (!box) throw new Error("no main element");
        await page.mouse.click(box.x + box.width - 4, box.y + box.height / 2);
      }
      await expectClosed(button, details);
      await page.context().close();
    });

    test("Escape closes it and puts focus back on its button", async ({ browser }) => {
      const page = await adminAt(browser, size.viewport);
      await page.goto("/");
      const { details, button } = await menu(page, size.mobile);
      await button.focus();
      await page.keyboard.press("Enter"); // keyboard opens it
      await expect(details).toHaveJSProperty("open", true);
      await expect(button).toHaveAttribute("aria-expanded", "true");
      await page.keyboard.press("Tab"); // into the first item
      await page.keyboard.press("Escape");
      await expectClosed(button, details);
      await expect(button).toBeFocused();
      if (size.mobile) await expect(page.locator("#primary-nav")).toHaveClass(/is-open/); // only the submenu closed
      await page.context().close();
    });

    test("choosing an item closes it", async ({ browser }) => {
      const page = await adminAt(browser, size.viewport);
      await page.goto("/");
      const { details, button } = await menu(page, size.mobile);
      await open(button, details);
      const item = details.getByRole("link", { name: "Report" });
      await item.evaluate((link) => link.addEventListener("click", (e) => e.preventDefault())); // stay on the page
      await item.click();
      await expectClosed(button, details);
      await page.context().close();
    });

    test(size.mobile ? "scrolling keeps it open inside the mobile menu" : "scrolling the page closes it", async ({ browser }) => {
      const page = await adminAt(browser, size.viewport);
      await page.goto("/");
      await page.evaluate(() => { document.body.style.minHeight = "3000px"; }); // make sure the page can scroll
      const { details, button } = await menu(page, size.mobile);
      await open(button, details);
      if (size.mobile) {
        // The open drawer may lock the page, so fire the window scroll event the menu listens to.
        await page.evaluate(() => window.dispatchEvent(new Event("scroll")));
        await expect(details).toHaveJSProperty("open", true);
        await expect(button).toHaveAttribute("aria-expanded", "true");
      } else {
        await page.mouse.wheel(0, 400);
        await expectClosed(button, details);
      }
      await page.context().close();
    });
  });
}
