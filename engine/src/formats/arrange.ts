/* sort, match, order, build: tap an item, then tap where it goes. */

import { t } from "../i18n";
import { TONES, clear, el } from "../dom";
import type { Base, Ctx, Tokened } from "../types";
import { asList, asMap, counter } from "./shared";

interface SortQ extends Base {
  bins: (Tokened & { tone: string | null })[];
  items: Tokened[];
}

export function renderSort(ctx: Ctx<SortQ>): void {
  const { q } = ctx;
  const placed = asMap<string>(q.response.placed);
  let selected: string | null = null;
  const stage = el("div", { class: "eng-sort" });
  ctx.root.append(stage);
  const draw = () => {
    clear(stage);
    const left = q.items.filter((it) => !placed[it.token]);
    stage.append(counter(left.length ? t("Tap a card, then tap where it belongs ({n} left)", { n: left.length }) : t("All placed. Tap a card to move it.")));
    const chip = (item: Tokened) =>
      el("button", { type: "button", class: "eng-chip", "aria-pressed": String(selected === item.token), onclick: () => { selected = selected === item.token ? null : item.token; draw(); } }, item.text);
    stage.append(el("div", { class: "eng-chips" }, ...left.map(chip)));
    const bins = el("div", { class: "eng-bins" });
    for (const bin of q.bins) {
      const tone = bin.tone ? TONES[bin.tone] : null;
      const target = el(
        "button",
        {
          type: "button",
          class: `eng-bin${bin.tone ? ` tri--${bin.tone}` : ""}`,
          onclick: () => {
            if (!selected) return;
            placed[selected] = bin.token;
            selected = null;
            ctx.save({ placed });
            draw();
          },
        },
        tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : null,
        el("span", { class: "tri__name" }, bin.text),
      );
      bins.append(el("div", { class: "eng-bin__col" }, target, el("div", { class: "eng-chips" }, ...q.items.filter((it) => placed[it.token] === bin.token).map(chip))));
    }
    stage.append(bins);
  };
  draw();
}

interface MatchQ extends Base {
  lefts: Tokened[];
  rights: Tokened[];
  left_label: string;
  right_label: string;
}

export function renderMatch(ctx: Ctx<MatchQ>): void {
  const { q } = ctx;
  const links = asMap<string>(q.response.links);
  let selected: string | null = q.lefts.find((l) => !links[l.token])?.token ?? null;
  const stage = el("div", { class: "eng-match" });
  ctx.root.append(stage);
  const owner = (right: string) => Object.keys(links).find((l) => links[l] === right);
  const draw = () => {
    clear(stage);
    stage.append(counter(t("Tap an item on the left, then its partner on the right. Tap again to change a pair.")));
    const left = el("div", { class: "eng-col" }, el("p", { class: "eng-label" }, q.left_label || t("Situation")));
    const right = el("div", { class: "eng-col" }, el("p", { class: "eng-label" }, q.right_label || t("Goes with")));
    q.lefts.forEach((l, i) => {
      left.append(
        el("button", { type: "button", class: "eng-pair", "aria-pressed": String(selected === l.token), onclick: () => { selected = l.token; draw(); } }, el("span", { class: "eng-pin" }, links[l.token] ? String(i + 1) : ""), l.text),
      );
    });
    for (const r of q.rights) {
      const who = owner(r.token);
      const number = who ? q.lefts.findIndex((l) => l.token === who) + 1 : 0;
      right.append(
        el(
          "button",
          {
            type: "button",
            class: "eng-pair",
            "aria-pressed": String(Boolean(who)),
            onclick: () => {
              if (!selected) return;
              for (const key of Object.keys(links)) if (links[key] === r.token) delete links[key];
              links[selected] = r.token;
              selected = q.lefts.find((l) => !links[l.token])?.token ?? null;
              ctx.save({ links });
              draw();
            },
          },
          el("span", { class: "eng-pin" }, number ? String(number) : ""),
          r.text,
        ),
      );
    }
    stage.append(el("div", { class: "eng-cols" }, left, right));
  };
  draw();
}

interface OrderQ extends Base {
  items: Tokened[];
}

export function renderOrder(ctx: Ctx<OrderQ>): void {
  const { q } = ctx;
  const sequence = asList<string>(q.response.sequence);
  const text = (token: string) => q.items.find((i) => i.token === token)?.text ?? "";
  const stage = el("div", { class: "eng-order" });
  ctx.root.append(stage);
  const draw = () => {
    clear(stage);
    stage.append(el("p", { class: "eng-label" }, t("Your order")));
    const list = el("ol", { class: "eng-seq" });
    if (!sequence.length) list.append(el("li", { class: "eng-empty" }, t("Tap the steps below in the order you would do them.")));
    sequence.forEach((token, position) => {
      list.append(
        el("li", {}, el("button", { type: "button", title: t("Tap to remove"), onclick: () => { sequence.splice(position, 1); ctx.save({ sequence }); draw(); } }, el("span", { class: "eng-n" }, String(position + 1)), " ", el("span", {}, text(token)))),
      );
    });
    stage.append(list);
    const rest = q.items.filter((i) => !sequence.includes(i.token));
    if (rest.length) {
      stage.append(el("p", { class: "eng-label" }, t("Steps to place")));
      stage.append(el("div", { class: "eng-chips" }, ...rest.map((i) => el("button", { type: "button", class: "eng-chip", onclick: () => { sequence.push(i.token); ctx.save({ sequence }); draw(); } }, i.text))));
    }
  };
  draw();
}

interface BuildQ extends Base {
  slots: { token: string; label: string; chips: string[] | null }[];
  chips: Tokened[];
  scene_label: string;
}

export function renderBuild(ctx: Ctx<BuildQ>): void {
  const { q } = ctx;
  const filled = asMap<string>(q.response.filled);
  let current: string | null = q.slots.find((s) => !filled[s.token])?.token ?? q.slots[0]?.token ?? null;
  const chipText = (token: string) => q.chips.find((c) => c.token === token)?.text ?? "";
  const stage = el("div", { class: "eng-build" });
  ctx.root.append(stage);
  const draw = () => {
    clear(stage);
    const slots = el("div", { class: "eng-slots" });
    for (const slot of q.slots) {
      const value = filled[slot.token];
      slots.append(
        el(
          "div",
          { class: "eng-slot" },
          el("p", { class: "eng-label" }, slot.label),
          el(
            "button",
            {
              type: "button",
              class: `eng-slot__btn${current === slot.token ? " is-target" : ""}${value ? " is-filled" : ""}`,
              "aria-label": `${slot.label}: ${value ? chipText(value) : "Tap, then choose a card below"}`,
              onclick: () => {
                if (value) {
                  delete filled[slot.token];
                  ctx.save({ filled });
                }
                current = slot.token;
                draw();
              },
            },
            value ? chipText(value) : "Tap, then choose a card below",
          ),
        ),
      );
    }
    stage.append(slots);
    const slot = q.slots.find((s) => s.token === current);
    stage.append(el("p", { class: "eng-label" }, slot ? t("Cards for: {label}", { label: slot.label }) : t("Tap a slot to change it")));
    const used = new Set(Object.values(filled));
    const pool = el("div", { class: "eng-chips" });
    for (const chip of q.chips) {
      if (used.has(chip.token)) continue;
      if (slot && slot.chips && !slot.chips.includes(chip.token)) continue;
      pool.append(
        el("button", { type: "button", class: "eng-chip", onclick: () => {
          if (!slot) return;
          filled[slot.token] = chip.token;
          current = q.slots.find((s) => !filled[s.token])?.token ?? null;
          ctx.save({ filled });
          draw();
        } }, chip.text),
      );
    }
    stage.append(pool);
  };
  draw();
}
