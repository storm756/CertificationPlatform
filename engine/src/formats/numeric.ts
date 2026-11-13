/* settings (switches and segmented options) and dial (steppers for times and numbers). */

import { t } from "../i18n";
import { clear, el } from "../dom";
import type { Base, Ctx, Tokened } from "../types";
import { asMap, doneToggle } from "./shared";

interface SettingsQ extends Base {
  device: string;
  screen: string;
  rows: { token: string; text: string; kind: "switch" | "choice"; options: Tokened[]; start: string | number }[];
}

export function renderSettings(ctx: Ctx<SettingsQ>): void {
  const { q } = ctx;
  const values = asMap<string | number>(q.response.values);
  let done = Boolean(q.response.done);
  const current = (row: SettingsQ["rows"][number]) => (row.token in values ? values[row.token] : row.start);
  const push = () => ctx.save({ values, done });
  const device = el("div", { class: "eng-device" }, el("div", { class: "eng-device__bar" }, el("span", {}, q.screen || t("Settings")), el("small", {}, q.device)));
  for (const row of q.rows) {
    const line = el("div", { class: "eng-setrow" }, el("span", { class: "eng-setrow__label" }, row.text));
    if (row.kind === "switch") {
      const toggle = el("button", { type: "button", role: "switch", class: "eng-switch", "aria-label": row.text, "aria-checked": String(Boolean(current(row))) });
      toggle.addEventListener("click", () => {
        values[row.token] = current(row) ? 0 : 1;
        toggle.setAttribute("aria-checked", String(Boolean(values[row.token])));
        push();
      });
      line.append(toggle);
    } else {
      const group = el("div", { class: "eng-seg", role: "radiogroup", "aria-label": row.text });
      const buttons: [string, HTMLButtonElement][] = [];
      for (const option of row.options) {
        const button = el("button", { type: "button", role: "radio", "aria-checked": String(current(row) === option.token) }, option.text);
        button.addEventListener("click", () => {
          values[row.token] = option.token;
          buttons.forEach(([token, b]) => b.setAttribute("aria-checked", String(token === option.token)));
          push();
        });
        buttons.push([option.token, button]);
        group.append(button);
      }
      line.append(group);
    }
    device.append(line);
  }
  ctx.root.append(device, doneToggle(ctx, done, (value) => { done = value; push(); }));
}

interface DialQ extends Base {
  rows: { token: string; label: string; kind: "time" | "number"; unit: string; start: number; min: number | null; max: number | null; steps: number[] }[];
}

const pad = (n: number) => String(n).padStart(2, "0");
function show(row: DialQ["rows"][number], value: number): string {
  if (row.kind === "time") {
    const minutes = ((value % 1440) + 1440) % 1440;
    return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)} ${row.unit || "IST"}`;
  }
  return `${value}${row.unit ? ` ${row.unit}` : ""}`;
}

export function renderDial(ctx: Ctx<DialQ>): void {
  const { q } = ctx;
  const values = asMap<number>(q.response.values);
  let done = Boolean(q.response.done);
  const push = () => ctx.save({ values, done });
  const wrap = el("div", { class: "eng-dials" });
  for (const row of q.rows) {
    const display = el("div", { class: "eng-val", "aria-live": "polite" });
    const get = () => (row.token in values ? values[row.token] : row.start);
    const paint = () => { display.textContent = show(row, get()); };
    const stepButton = (step: number) => {
      const label = row.kind === "time" ? `${step > 0 ? "+" : "−"}${Math.abs(step) >= 60 ? `${Math.abs(step) / 60} h` : `${Math.abs(step)} min`}` : `${step > 0 ? "+" : "−"}${Math.abs(step)}`;
      return el("button", { type: "button", "aria-label": `${label}, ${step > 0 ? "increase" : "decrease"} by ${Math.abs(step)}${row.kind === "time" ? " minutes" : ""}`, onclick: () => {
        let next = get() + step;
        if (row.kind !== "time") {
          if (row.min !== null) next = Math.max(row.min, next);
          if (row.max !== null) next = Math.min(row.max, next);
        }
        values[row.token] = next;
        paint();
        push();
      } }, label);
    };
    paint();
    wrap.append(
      el("div", { class: "eng-dial" }, el("p", { class: "eng-label" }, row.label), el("div", { class: "eng-ctl" }, ...row.steps.filter((s) => s < 0).map(stepButton), display, ...row.steps.filter((s) => s > 0).map(stepButton))),
    );
  }
  clear(ctx.root);
  ctx.root.append(wrap, doneToggle(ctx, done, (value) => { done = value; push(); }));
}
