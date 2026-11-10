/* crossword (practice only): tap a cell or a clue, then type on the keyboard or the screen keys. */

import { clear, el } from "../dom";
import type { Base, Ctx } from "../types";
import { asMap } from "./shared";

interface CrosswordQ extends Base {
  rows: number;
  cols: number;
  cells: { token: string; row: number; col: number }[];
  words: { number: number; dir: "A" | "D"; clue: string; length: number; cells: string[] }[];
}

const KEYS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];

export function renderCrossword(ctx: Ctx<CrosswordQ>): void {
  const { q } = ctx;
  const letters = asMap<string>(q.response.letters);
  let word = 0;
  let cell: string = q.words[0].cells[0];
  const cellByToken = new Map(q.cells.map((c) => [c.token, c]));
  const startNumber = new Map<string, number>();
  for (const w of q.words) startNumber.set(w.cells[0], w.number);
  const stage = el("div", { class: "eng-xw" });
  ctx.root.append(stage);
  const buttons = new Map<string, HTMLButtonElement>();

  const grid = el("div", { class: "eng-xgrid" });
  grid.style.setProperty("--cols", String(q.cols));
  for (let r = 0; r < q.rows; r++) {
    for (let c = 0; c < q.cols; c++) {
      const found = q.cells.find((x) => x.row === r && x.col === c);
      if (!found) {
        grid.append(el("span", { class: "eng-xblock", "aria-hidden": "true" }));
        continue;
      }
      const button = el("button", { type: "button", class: "eng-xc", "aria-label": `${startNumber.has(found.token) ? `Clue number ${startNumber.get(found.token)}, ` : ""}row ${r + 1}, column ${c + 1}: empty` }, startNumber.has(found.token) ? el("i", {}, String(startNumber.get(found.token))) : null, el("b", {}));
      button.addEventListener("click", () => {
        const containing = q.words.map((w, i) => (w.cells.includes(found.token) ? i : -1)).filter((i) => i >= 0);
        if (cell === found.token && containing.length > 1 && containing.includes(word)) word = containing[(containing.indexOf(word) + 1) % containing.length];
        else if (!containing.includes(word)) word = containing[0];
        cell = found.token;
        paint();
      });
      buttons.set(found.token, button);
      grid.append(button);
    }
  }

  const banner = el("p", { class: "eng-xnow", "aria-live": "polite" });
  const paint = () => {
    const active = new Set(q.words[word].cells);
    for (const [token, button] of buttons) {
      button.className = `eng-xc${active.has(token) ? " is-word" : ""}${token === cell ? " is-current" : ""}`;
      const letter = letters[token] ?? "";
      (button.querySelector("b") as HTMLElement).textContent = letter;
      const pos = cellByToken.get(token);
      const number = startNumber.get(token);
      button.setAttribute("aria-label", `${number ? `Clue number ${number}, ` : ""}row ${(pos?.row ?? 0) + 1}, column ${(pos?.col ?? 0) + 1}: ${letter || "empty"}`);
    }
    const w = q.words[word];
    banner.textContent = `${w.number} ${w.dir === "A" ? "Across" : "Down"} · ${w.length} letters: ${w.clue}`;
  };
  const type = (letter: string) => {
    letters[cell] = letter;
    const cells = q.words[word].cells;
    const i = cells.indexOf(cell);
    if (i >= 0 && i < cells.length - 1) cell = cells[i + 1];
    ctx.save({ letters });
    paint();
  };
  const back = () => {
    const cells = q.words[word].cells;
    const i = cells.indexOf(cell);
    if (letters[cell]) delete letters[cell];
    else if (i > 0) {
      cell = cells[i - 1];
      delete letters[cell];
    }
    ctx.save({ letters });
    paint();
  };

  const keys = el("div", { class: "eng-xkeys", role: "group", "aria-label": "Letter keyboard" });
  KEYS.forEach((row, index) => {
    const line = el("div", { class: "eng-xkrow" });
    for (const ch of row) line.append(el("button", { type: "button", "aria-label": ch, onclick: () => type(ch) }, ch));
    if (index === 2) line.append(el("button", { type: "button", class: "eng-xbs", "aria-label": "Delete", onclick: back }, "⌫"));
    keys.append(line);
  });

  const clues = el("div", { class: "eng-xclues" });
  for (const dir of ["A", "D"] as const) {
    const column = el("div", {}, el("p", { class: "eng-label" }, dir === "A" ? "Across" : "Down"));
    q.words.forEach((w, i) => {
      if (w.dir !== dir) return;
      column.append(el("button", { type: "button", class: "eng-xclue", onclick: () => { word = i; cell = w.cells.find((t) => !letters[t]) ?? w.cells[0]; paint(); } }, el("span", { class: "eng-xn" }, String(w.number)), el("span", {}, w.clue)));
    });
    clues.append(column);
  }

  clear(stage);
  stage.append(banner, grid, keys, clues);
  const onKey = (event: KeyboardEvent) => {
    if (!document.body.contains(grid)) {
      document.removeEventListener("keydown", onKey);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target as HTMLElement | null;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
    if (/^[a-zA-Z]$/.test(event.key)) {
      event.preventDefault();
      type(event.key.toUpperCase());
    } else if (event.key === "Backspace") {
      event.preventDefault();
      back();
    }
  };
  document.addEventListener("keydown", onKey);
  paint();
}
