import { t } from "../i18n";
import { el } from "../dom";
import type { Ctx } from "../types";

const FINISHED = () => t("I have finished this question");
const MARKED = () => t("✓ Marked as finished");

/** A "finished" toggle for formats with nothing to leave blank: it records "done" explicitly. */
export function doneToggle(_ctx: Ctx, done: boolean, onChange: (value: boolean) => void): HTMLElement {
  const button = el("button", { type: "button", class: "btn btn-outline eng-done", "aria-pressed": String(done) }, done ? MARKED() : FINISHED());
  button.addEventListener("click", () => {
    const next = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(next));
    button.textContent = next ? MARKED() : FINISHED();
    onChange(next);
  });
  return button;
}

export function counter(text: string): HTMLElement {
  return el("p", { class: "eng-count", "aria-live": "polite" }, text);
}

export function note(text: string): HTMLElement {
  return el("p", { class: "eng-note" }, text);
}

export const asList = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
export const asMap = <T>(value: unknown): Record<string, T> =>
  value && typeof value === "object" && !Array.isArray(value) ? { ...(value as Record<string, T>) } : {};
