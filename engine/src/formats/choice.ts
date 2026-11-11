/* mc (with the four colour-triage buttons), cards, spot, hotspot, pick. */

import { TONES, clear, el, nodes, svg } from "../dom";
import type { Base, Ctx, Tokened } from "../types";
import { asList, asMap, counter, doneToggle, note } from "./shared";

interface MCQ extends Base {
  options: (Tokened & { tone: string | null })[];
  triage: boolean;
}

export function renderMC(ctx: Ctx<MCQ>): void {
  const { q } = ctx;
  let chosen = (q.response.choice as string) ?? "";
  const group = el("div", { class: q.triage ? "tri" : "opts", role: "radiogroup", "aria-label": "Choose one answer" });
  const buttons: [string, HTMLButtonElement][] = [];
  for (const option of q.options) {
    const tone = option.tone ? TONES[option.tone] : null;
    const button = el(
      "button",
      { type: "button", role: "radio", class: tone ? `tri__btn tri--${option.tone}` : "opt", "aria-checked": String(option.token === chosen) },
      tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : el("span", { class: "opt__mark", "aria-hidden": "true" }),
      tone ? el("span", { class: "tri__name" }, tone.name) : null,
      el("span", { class: "tri__text" }, option.text),
    );
    button.addEventListener("click", () => {
      chosen = option.token;
      buttons.forEach(([token, b]) => b.setAttribute("aria-checked", String(token === chosen)));
      ctx.save({ choice: chosen });
    });
    buttons.push([option.token, button]);
    group.append(button);
  }
  ctx.root.append(group);
}

interface CardsQ extends Base {
  labels: (Tokened & { tone: string | null })[];
  items: Tokened[];
}

export function renderCards(ctx: Ctx<CardsQ>): void {
  const { q } = ctx;
  const answers = asMap<string>(q.response.answers);
  let index = Math.max(0, q.items.findIndex((it) => !answers[it.token]));
  if (q.items.every((it) => answers[it.token])) index = q.items.length;
  const stage = el("div", { class: "eng-cards" });
  ctx.root.append(stage);
  const draw = () => {
    clear(stage);
    if (index >= q.items.length) {
      stage.append(
        note("All cards are answered. Use Previous to change one."),
        el("button", { type: "button", class: "btn btn-outline", onclick: () => { index = q.items.length - 1; draw(); } }, "Previous"),
      );
      return;
    }
    const item = q.items[index];
    stage.append(counter(`Card ${index + 1} of ${q.items.length}`), el("div", { class: "eng-card", "aria-live": "polite" }, item.text));
    const row = el("div", { class: "tri", role: "group", "aria-label": "Your verdict" });
    for (const label of q.labels) {
      const tone = label.tone ? TONES[label.tone] : null;
      const picked = answers[item.token] === label.token;
      const button = el(
        "button",
        { type: "button", class: `tri__btn${label.tone ? ` tri--${label.tone}` : ""}`, "aria-pressed": String(picked) },
        tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : null,
        el("span", { class: "tri__name" }, label.text),
      );
      button.addEventListener("click", () => {
        answers[item.token] = label.token;
        ctx.save({ answers });
        index += 1;
        draw();
      });
      row.append(button);
    }
    stage.append(row);
    if (index > 0) stage.append(el("button", { type: "button", class: "btn btn-ghost", onclick: () => { index -= 1; draw(); } }, "Previous"));
  };
  draw();
}

interface SpotQ extends Base {
  segments: { text: string; token: string | null }[];
  style: string;
  redact: boolean;
  look_for?: number;
}

export function renderSpot(ctx: Ctx<SpotQ>): void {
  const { q } = ctx;
  const picked = new Set(asList<string>(q.response.picked));
  let done = Boolean(q.response.done);
  const message = el("p", { class: `eng-msg ${q.style}${q.redact ? " is-redact" : ""}` });
  const status = counter("");
  const update = () => {
    status.textContent = `${picked.size} selected${q.look_for ? ` · look for ${q.look_for}` : ""}`;
  };
  const push = () => ctx.save({ picked: [...picked], done });
  for (const segment of q.segments) {
    if (!segment.token) {
      message.append(document.createTextNode(segment.text));
      continue;
    }
    const token = segment.token;
    const tap = el("span", { class: "eng-tap", role: "button", tabindex: "0", "aria-pressed": String(picked.has(token)) }, segment.text);
    const toggle = () => {
      if (picked.has(token)) picked.delete(token);
      else picked.add(token);
      tap.setAttribute("aria-pressed", String(picked.has(token)));
      update();
      push();
    };
    tap.addEventListener("click", toggle);
    tap.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
    message.append(tap);
  }
  update();
  ctx.root.append(message, status, doneToggle(ctx, done, (value) => { done = value; push(); }));
}

interface HotspotQ extends Base {
  image: { alt: string; available: boolean };
  legend: string;
  regions: { token: string; label: string; shape: "rect" | "circle" | "poly"; coords: number[] }[];
}

export function renderHotspot(ctx: Ctx<HotspotQ>): void {
  const { q } = ctx;
  const picked = new Set(asList<string>(q.response.picked));
  let done = Boolean(q.response.done);
  const push = () => ctx.save({ picked: [...picked], done });
  const status = counter("");
  const update = () => {
    status.textContent = `${picked.size} selected`;
  };
  if (!q.image.available || !ctx.imageUrl) {
    ctx.root.append(note("The picture for this question is not available yet."));
    return;
  }
  // The picture is an uploaded, re-encoded raster image. The tappable regions are drawn here as SVG
  // shapes from numbers (percent of the picture): no content markup is ever inserted.
  const image = el("img", { class: "eng-hot__img", src: ctx.imageUrl, alt: q.image.alt });
  const layer = svg("svg", { class: "eng-hot__layer", viewBox: "0 0 100 100", preserveAspectRatio: "none" });
  const aspect = () => (image.naturalHeight ? image.naturalWidth / image.naturalHeight : 1);
  const shapes: SVGElement[] = [];
  for (const region of q.regions) {
    const c = region.coords;
    const shape =
      region.shape === "rect"
        ? svg("rect", { x: c[0], y: c[1], width: c[2], height: c[3] })
        : region.shape === "circle"
          ? svg("ellipse", { cx: c[0], cy: c[1], rx: c[2], ry: c[2] * aspect() })
          : svg("polygon", { points: c.reduce((acc, v, i) => acc + (i % 2 ? `,${v} ` : String(v)), "") });
    shape.setAttribute("class", "eng-hot__region");
    shape.setAttribute("tabindex", "0");
    shape.setAttribute("role", "button");
    shape.setAttribute("aria-label", region.label);
    shape.setAttribute("aria-pressed", String(picked.has(region.token)));
    const toggle = () => {
      if (picked.has(region.token)) picked.delete(region.token);
      else picked.add(region.token);
      shape.setAttribute("aria-pressed", String(picked.has(region.token)));
      update();
      push();
    };
    shape.addEventListener("click", toggle);
    shape.addEventListener("keydown", (e) => {
      const key = (e as KeyboardEvent).key;
      if (key === "Enter" || key === " ") {
        e.preventDefault();
        toggle();
      }
    });
    shapes.push(shape);
    layer.append(shape);
  }
  image.addEventListener("load", () => {
    q.regions.forEach((region, i) => {
      if (region.shape === "circle") shapes[i].setAttribute("ry", String(region.coords[2] * aspect()));
    });
  });
  update();
  ctx.root.append(
    ...nodes(
      el("div", { class: "eng-hot" }, image, layer),
      q.legend ? note(q.legend) : null,
      status,
      doneToggle(ctx, done, (value) => { done = value; push(); }),
    ),
  );
}

interface PickQ extends Base {
  items: Tokened[];
  need: number;
  check_label: string;
}

export function renderPick(ctx: Ctx<PickQ>): void {
  const { q } = ctx;
  const picked = new Set(asList<string>(q.response.picked));
  let done = Boolean(q.response.done);
  const status = counter("");
  const update = (message?: string) => {
    status.textContent = message ?? (q.need ? `${picked.size} of ${q.need} picked` : `${picked.size} ticked`);
  };
  const push = () => ctx.save({ picked: [...picked], done });
  const grid = el("div", { class: "eng-tiles" });
  for (const item of q.items) {
    const tile = el("button", { type: "button", class: "eng-tile", "aria-pressed": String(picked.has(item.token)) }, el("span", { class: "eng-tile__box", "aria-hidden": "true" }), el("span", {}, item.text));
    tile.addEventListener("click", () => {
      if (!picked.has(item.token) && q.need && picked.size >= q.need) {
        update(`You can pick only ${q.need}. Untick one first.`);
        return;
      }
      if (picked.has(item.token)) picked.delete(item.token);
      else picked.add(item.token);
      tile.setAttribute("aria-pressed", String(picked.has(item.token)));
      update();
      push();
    });
    grid.append(tile);
  }
  update();
  ctx.root.append(...nodes(grid, status, q.need ? null : doneToggle(ctx, done, (value) => { done = value; push(); })));
}
