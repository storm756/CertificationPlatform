/* The interactive question engine: draws the 13 formats from the server's projection and sends
   the learner's answer back (tokens only). It never scores anything and never sees a key.
   Bundled with esbuild into static/js/engine.js. */

import { t } from "./i18n";
import { clear } from "./dom";
import { renderChat } from "./formats/chat";
import { renderCards, renderHotspot, renderMC, renderPick, renderSpot } from "./formats/choice";
import { renderCrossword } from "./formats/crossword";
import { renderBuild, renderMatch, renderOrder, renderSort } from "./formats/arrange";
import { renderDial, renderSettings } from "./formats/numeric";
import type { Base, Ctx, Renderer } from "./types";

const RENDERERS: Record<string, Renderer> = {
  mc: renderMC,
  cards: renderCards,
  spot: renderSpot,
  hotspot: renderHotspot,
  sort: renderSort,
  match: renderMatch,
  order: renderOrder,
  pick: renderPick,
  build: renderBuild,
  settings: renderSettings,
  dial: renderDial,
  chat: renderChat,
  crossword: renderCrossword,
};

/** Resolves once the server has accepted this question's answer. attempt.js keeps the answer in its
 * outbox, retries a failed save for this same question, and announces "ccfr:saved" when done. */
function waitForSave(form: HTMLFormElement): Promise<void> {
  const position = (form.elements.namedItem("position") as HTMLInputElement | null)?.value;
  return new Promise((resolve) => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail as { position?: string } | undefined;
      if (detail && String(detail.position) === position) {
        document.removeEventListener("ccfr:saved", handler);
        resolve();
      }
    };
    document.addEventListener("ccfr:saved", handler);
  });
}

export function mount(root: HTMLElement): void {
  if (root.dataset.mounted) return;
  root.dataset.mounted = "1";
  const form = root.closest("form") as HTMLFormElement | null;
  const field = form?.querySelector<HTMLInputElement>("[data-response]") ?? null;
  const q = JSON.parse(root.dataset.q ?? "{}") as Base;
  const draw = RENDERERS[q.format];
  if (!draw || !form || !field) {
    root.textContent = t("This question can't be shown.");
    return;
  }
  const ctx: Ctx = {
    root,
    q,
    imageUrl: root.dataset.imageUrl,
    save(response) {
      // Handed over at once: attempt.js copies it into its outbox (tagged with this question's
      // number), so moving on, or a failed save, can never lose it or send it to another question.
      ctx.q.response = response;
      field.value = JSON.stringify(response);
      form.dispatchEvent(new Event("change", { bubbles: true }));
    },
    saved: () => waitForSave(form),
    async refetch() {
      const reply = await fetch(root.dataset.dataUrl ?? "", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!reply.ok) throw new Error("could not load");
      ctx.q = (await reply.json()) as Base;
      return ctx.q;
    },
  };
  clear(root);
  draw(ctx);
}

export function boot(): void {
  document.querySelectorAll<HTMLElement>("[data-engine]").forEach(mount);
}

document.addEventListener("DOMContentLoaded", boot);
document.body?.addEventListener("htmx:afterSwap", boot);
boot();
