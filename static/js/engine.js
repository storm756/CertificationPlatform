/* CCFR interactive engine. Built from engine/src with tools/build_engine.mjs; do not edit. */
"use strict";
(() => {
  // ../engine/src/i18n.ts
  var table = null;
  function load() {
    var _a2;
    if (table === null) {
      table = {};
      const node = document.getElementById("engine-labels");
      try {
        const parsed = node ? JSON.parse((_a2 = node.textContent) != null ? _a2 : "{}") : {};
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) table = parsed;
      } catch {
        table = {};
      }
    }
    return table;
  }
  function t(text, vars) {
    const found = load()[text];
    let out = typeof found === "string" && found ? found : text;
    if (vars) for (const [key, value] of Object.entries(vars)) out = out.split(`{${key}}`).join(String(value));
    return out;
  }

  // ../engine/src/dom.ts
  var SVG_NS = "http://www.w3.org/2000/svg";
  function apply(node, attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === void 0 || value === false) continue;
      if (typeof value === "function") node.addEventListener(key.replace(/^on/, ""), value);
      else node.setAttribute(key, value === true ? "" : String(value));
    }
  }
  function append(node, children) {
    for (const child of children) {
      if (child === null || child === false || child === void 0) continue;
      node.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
    }
  }
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    apply(node, attrs);
    append(node, children);
    return node;
  }
  function svg(tag, attrs = {}, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    apply(node, attrs);
    append(node, children);
    return node;
  }
  function nodes(...children) {
    return children.filter((c) => c !== null && c !== false && c !== void 0).map((c) => typeof c === "number" ? String(c) : c);
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  var TONES = {
    red: { name: t("Red"), shape: "■" },
    amber: { name: t("Amber"), shape: "▲" },
    yellow: { name: t("Yellow"), shape: "◆" },
    green: { name: t("Green"), shape: "●" }
  };

  // ../engine/src/formats/shared.ts
  var FINISHED = () => t("I have finished this question");
  var MARKED = () => t("✓ Marked as finished");
  function doneToggle(_ctx, done, onChange) {
    const button = el("button", { type: "button", class: "btn btn-outline eng-done", "aria-pressed": String(done) }, done ? MARKED() : FINISHED());
    button.addEventListener("click", () => {
      const next = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(next));
      button.textContent = next ? MARKED() : FINISHED();
      onChange(next);
    });
    return button;
  }
  function counter(text) {
    return el("p", { class: "eng-count", "aria-live": "polite" }, text);
  }
  function note(text) {
    return el("p", { class: "eng-note" }, text);
  }
  var asList = (value) => Array.isArray(value) ? value : [];
  var asMap = (value) => value && typeof value === "object" && !Array.isArray(value) ? { ...value } : {};

  // ../engine/src/formats/chat.ts
  function renderChat(ctx) {
    const stage = el("div", { class: "eng-chat" });
    ctx.root.append(stage);
    const replies = asList(ctx.q.response.replies);
    const draw = () => {
      var _a2;
      const q = ctx.q;
      clear(stage);
      const log = el("div", { class: "eng-log", "aria-live": "polite" });
      for (const step of q.steps) {
        log.append(el("div", { class: "eng-bub eng-bub--them" }, el("span", { class: "eng-who" }, q.who), step.say));
        if (step.chosen !== void 0) log.append(el("div", { class: "eng-bub eng-bub--me" }, el("span", { class: "eng-who" }, t("You")), (_a2 = step.text) != null ? _a2 : ""));
      }
      stage.append(log);
      const last = q.steps[q.steps.length - 1];
      if (last && last.replies) {
        const box = el("div", { class: "eng-replies", role: "group", "aria-label": t("What do you say or do?") });
        for (const reply of last.replies) {
          const button = el("button", { type: "button", class: "eng-reply" }, reply.text);
          button.addEventListener("click", async () => {
            box.querySelectorAll("button").forEach((b) => b.setAttribute("disabled", ""));
            replies.push(reply.token);
            ctx.save({ replies });
            try {
              await ctx.saved();
              await ctx.refetch();
              draw();
            } catch {
              box.querySelectorAll("button").forEach((b) => b.removeAttribute("disabled"));
            }
          });
          box.append(button);
        }
        stage.append(box);
      } else {
        stage.append(el("p", { class: "eng-note" }, t("That is the end of the conversation. Your replies are saved.")));
      }
      stage.append(el("p", { class: "eng-count" }, `Step ${Math.min(replies.length + 1, q.total_steps)} of ${q.total_steps}`));
    };
    draw();
  }

  // ../engine/src/formats/choice.ts
  function renderMC(ctx) {
    var _a2;
    const { q } = ctx;
    let chosen = (_a2 = q.response.choice) != null ? _a2 : "";
    const group = el("div", { class: q.triage ? "tri" : "opts", role: "radiogroup", "aria-label": t("Choose one answer") });
    const buttons = [];
    for (const option of q.options) {
      const tone = option.tone ? TONES[option.tone] : null;
      const button = el(
        "button",
        { type: "button", role: "radio", class: tone ? `tri__btn tri--${option.tone}` : "opt", "aria-checked": String(option.token === chosen) },
        tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : el("span", { class: "opt__mark", "aria-hidden": "true" }),
        tone ? el("span", { class: "tri__name" }, tone.name) : null,
        el("span", { class: "tri__text" }, option.text)
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
  function renderCards(ctx) {
    const { q } = ctx;
    const answers = asMap(q.response.answers);
    let index = Math.max(0, q.items.findIndex((it) => !answers[it.token]));
    if (q.items.every((it) => answers[it.token])) index = q.items.length;
    const stage = el("div", { class: "eng-cards" });
    ctx.root.append(stage);
    const draw = () => {
      clear(stage);
      if (index >= q.items.length) {
        stage.append(
          note(t("All cards are answered. Use Previous to change one.")),
          el("button", { type: "button", class: "btn btn-outline", onclick: () => {
            index = q.items.length - 1;
            draw();
          } }, t("Previous"))
        );
        return;
      }
      const item = q.items[index];
      stage.append(counter(`Card ${index + 1} of ${q.items.length}`), el("div", { class: "eng-card", "aria-live": "polite" }, item.text));
      const row = el("div", { class: "tri", role: "group", "aria-label": t("Your verdict") });
      for (const label of q.labels) {
        const tone = label.tone ? TONES[label.tone] : null;
        const picked = answers[item.token] === label.token;
        const button = el(
          "button",
          { type: "button", class: `tri__btn${label.tone ? ` tri--${label.tone}` : ""}`, "aria-pressed": String(picked) },
          tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : null,
          el("span", { class: "tri__name" }, label.text)
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
      if (index > 0) stage.append(el("button", { type: "button", class: "btn btn-ghost", onclick: () => {
        index -= 1;
        draw();
      } }, t("Previous")));
    };
    draw();
  }
  function renderSpot(ctx) {
    const { q } = ctx;
    const picked = new Set(asList(q.response.picked));
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
    ctx.root.append(message, status, doneToggle(ctx, done, (value) => {
      done = value;
      push();
    }));
  }
  function renderHotspot(ctx) {
    const { q } = ctx;
    const picked = new Set(asList(q.response.picked));
    let done = Boolean(q.response.done);
    const push = () => ctx.save({ picked: [...picked], done });
    const status = counter("");
    const update = () => {
      status.textContent = `${picked.size} selected`;
    };
    if (!q.image.available || !ctx.imageUrl) {
      ctx.root.append(note(t("The picture for this question is not available yet.")));
      return;
    }
    const image = el("img", { class: "eng-hot__img", src: ctx.imageUrl, alt: q.image.alt });
    const layer = svg("svg", { class: "eng-hot__layer", viewBox: "0 0 100 100", preserveAspectRatio: "none" });
    const aspect = () => image.naturalHeight ? image.naturalWidth / image.naturalHeight : 1;
    const shapes = [];
    for (const region of q.regions) {
      const c = region.coords;
      const shape = region.shape === "rect" ? svg("rect", { x: c[0], y: c[1], width: c[2], height: c[3] }) : region.shape === "circle" ? svg("ellipse", { cx: c[0], cy: c[1], rx: c[2], ry: c[2] * aspect() }) : svg("polygon", { points: c.reduce((acc, v, i) => acc + (i % 2 ? `,${v} ` : String(v)), "") });
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
        const key = e.key;
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
        doneToggle(ctx, done, (value) => {
          done = value;
          push();
        })
      )
    );
  }
  function renderPick(ctx) {
    const { q } = ctx;
    const picked = new Set(asList(q.response.picked));
    let done = Boolean(q.response.done);
    const status = counter("");
    const update = (message) => {
      status.textContent = message != null ? message : q.need ? `${picked.size} of ${q.need} picked` : `${picked.size} ticked`;
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
    ctx.root.append(...nodes(grid, status, q.need ? null : doneToggle(ctx, done, (value) => {
      done = value;
      push();
    })));
  }

  // ../engine/src/formats/crossword.ts
  var KEYS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
  function renderCrossword(ctx) {
    const { q } = ctx;
    const letters = asMap(q.response.letters);
    let word = 0;
    let cell = q.words[0].cells[0];
    const cellByToken = new Map(q.cells.map((c) => [c.token, c]));
    const startNumber = /* @__PURE__ */ new Map();
    for (const w of q.words) startNumber.set(w.cells[0], w.number);
    const stage = el("div", { class: "eng-xw" });
    ctx.root.append(stage);
    const buttons = /* @__PURE__ */ new Map();
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
          const containing = q.words.map((w, i) => w.cells.includes(found.token) ? i : -1).filter((i) => i >= 0);
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
      var _a2, _b, _c;
      const active = new Set(q.words[word].cells);
      for (const [token, button] of buttons) {
        button.className = `eng-xc${active.has(token) ? " is-word" : ""}${token === cell ? " is-current" : ""}`;
        const letter = (_a2 = letters[token]) != null ? _a2 : "";
        button.querySelector("b").textContent = letter;
        const pos = cellByToken.get(token);
        const number = startNumber.get(token);
        button.setAttribute("aria-label", `${number ? `Clue number ${number}, ` : ""}row ${((_b = pos == null ? void 0 : pos.row) != null ? _b : 0) + 1}, column ${((_c = pos == null ? void 0 : pos.col) != null ? _c : 0) + 1}: ${letter || "empty"}`);
      }
      const w = q.words[word];
      banner.textContent = `${w.number} ${w.dir === "A" ? "Across" : "Down"} · ${w.length} letters: ${w.clue}`;
    };
    const type = (letter) => {
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
    for (const dir of ["A", "D"]) {
      const column = el("div", {}, el("p", { class: "eng-label" }, dir === "A" ? "Across" : "Down"));
      q.words.forEach((w, i) => {
        if (w.dir !== dir) return;
        column.append(el("button", { type: "button", class: "eng-xclue", onclick: () => {
          var _a2;
          word = i;
          cell = (_a2 = w.cells.find((t2) => !letters[t2])) != null ? _a2 : w.cells[0];
          paint();
        } }, el("span", { class: "eng-xn" }, String(w.number)), el("span", {}, w.clue)));
      });
      clues.append(column);
    }
    clear(stage);
    stage.append(banner, grid, keys, clues);
    const onKey = (event) => {
      if (!document.body.contains(grid)) {
        document.removeEventListener("keydown", onKey);
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
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

  // ../engine/src/formats/arrange.ts
  function renderSort(ctx) {
    const { q } = ctx;
    const placed = asMap(q.response.placed);
    let selected = null;
    const stage = el("div", { class: "eng-sort" });
    ctx.root.append(stage);
    const draw = () => {
      clear(stage);
      const left = q.items.filter((it) => !placed[it.token]);
      stage.append(counter(left.length ? t("Tap a card, then tap where it belongs ({n} left)", { n: left.length }) : t("All placed. Tap a card to move it.")));
      const chip = (item) => el("button", { type: "button", class: "eng-chip", "aria-pressed": String(selected === item.token), onclick: () => {
        selected = selected === item.token ? null : item.token;
        draw();
      } }, item.text);
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
            }
          },
          tone ? el("span", { class: "tri__shape", "aria-hidden": "true" }, tone.shape) : null,
          el("span", { class: "tri__name" }, bin.text)
        );
        bins.append(el("div", { class: "eng-bin__col" }, target, el("div", { class: "eng-chips" }, ...q.items.filter((it) => placed[it.token] === bin.token).map(chip))));
      }
      stage.append(bins);
    };
    draw();
  }
  function renderMatch(ctx) {
    var _a2, _b;
    const { q } = ctx;
    const links = asMap(q.response.links);
    let selected = (_b = (_a2 = q.lefts.find((l) => !links[l.token])) == null ? void 0 : _a2.token) != null ? _b : null;
    const stage = el("div", { class: "eng-match" });
    ctx.root.append(stage);
    const owner = (right) => Object.keys(links).find((l) => links[l] === right);
    const draw = () => {
      clear(stage);
      stage.append(counter(t("Tap an item on the left, then its partner on the right. Tap again to change a pair.")));
      const left = el("div", { class: "eng-col" }, el("p", { class: "eng-label" }, q.left_label || t("Situation")));
      const right = el("div", { class: "eng-col" }, el("p", { class: "eng-label" }, q.right_label || t("Goes with")));
      q.lefts.forEach((l, i) => {
        left.append(
          el("button", { type: "button", class: "eng-pair", "aria-pressed": String(selected === l.token), onclick: () => {
            selected = l.token;
            draw();
          } }, el("span", { class: "eng-pin" }, links[l.token] ? String(i + 1) : ""), l.text)
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
                var _a3, _b2;
                if (!selected) return;
                for (const key of Object.keys(links)) if (links[key] === r.token) delete links[key];
                links[selected] = r.token;
                selected = (_b2 = (_a3 = q.lefts.find((l) => !links[l.token])) == null ? void 0 : _a3.token) != null ? _b2 : null;
                ctx.save({ links });
                draw();
              }
            },
            el("span", { class: "eng-pin" }, number ? String(number) : ""),
            r.text
          )
        );
      }
      stage.append(el("div", { class: "eng-cols" }, left, right));
    };
    draw();
  }
  function renderOrder(ctx) {
    const { q } = ctx;
    const sequence = asList(q.response.sequence);
    const text = (token) => {
      var _a2, _b;
      return (_b = (_a2 = q.items.find((i) => i.token === token)) == null ? void 0 : _a2.text) != null ? _b : "";
    };
    const stage = el("div", { class: "eng-order" });
    ctx.root.append(stage);
    const draw = () => {
      clear(stage);
      stage.append(el("p", { class: "eng-label" }, t("Your order")));
      const list = el("ol", { class: "eng-seq" });
      if (!sequence.length) list.append(el("li", { class: "eng-empty" }, t("Tap the steps below in the order you would do them.")));
      sequence.forEach((token, position) => {
        list.append(
          el("li", {}, el("button", { type: "button", title: t("Tap to remove"), onclick: () => {
            sequence.splice(position, 1);
            ctx.save({ sequence });
            draw();
          } }, el("span", { class: "eng-n" }, String(position + 1)), " ", el("span", {}, text(token))))
        );
      });
      stage.append(list);
      const rest = q.items.filter((i) => !sequence.includes(i.token));
      if (rest.length) {
        stage.append(el("p", { class: "eng-label" }, t("Steps to place")));
        stage.append(el("div", { class: "eng-chips" }, ...rest.map((i) => el("button", { type: "button", class: "eng-chip", onclick: () => {
          sequence.push(i.token);
          ctx.save({ sequence });
          draw();
        } }, i.text))));
      }
    };
    draw();
  }
  function renderBuild(ctx) {
    var _a2, _b, _c, _d;
    const { q } = ctx;
    const filled = asMap(q.response.filled);
    let current = (_d = (_c = (_a2 = q.slots.find((s) => !filled[s.token])) == null ? void 0 : _a2.token) != null ? _c : (_b = q.slots[0]) == null ? void 0 : _b.token) != null ? _d : null;
    const chipText = (token) => {
      var _a3, _b2;
      return (_b2 = (_a3 = q.chips.find((c) => c.token === token)) == null ? void 0 : _a3.text) != null ? _b2 : "";
    };
    const stage = el("div", { class: "eng-build" });
    ctx.root.append(stage);
    const draw = () => {
      clear(stage);
      const slots = el("div", { class: "eng-slots" });
      for (const slot2 of q.slots) {
        const value = filled[slot2.token];
        slots.append(
          el(
            "div",
            { class: "eng-slot" },
            el("p", { class: "eng-label" }, slot2.label),
            el(
              "button",
              {
                type: "button",
                class: `eng-slot__btn${current === slot2.token ? " is-target" : ""}${value ? " is-filled" : ""}`,
                "aria-label": `${slot2.label}: ${value ? chipText(value) : "Tap, then choose a card below"}`,
                onclick: () => {
                  if (value) {
                    delete filled[slot2.token];
                    ctx.save({ filled });
                  }
                  current = slot2.token;
                  draw();
                }
              },
              value ? chipText(value) : "Tap, then choose a card below"
            )
          )
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
            var _a3, _b2;
            if (!slot) return;
            filled[slot.token] = chip.token;
            current = (_b2 = (_a3 = q.slots.find((s) => !filled[s.token])) == null ? void 0 : _a3.token) != null ? _b2 : null;
            ctx.save({ filled });
            draw();
          } }, chip.text)
        );
      }
      stage.append(pool);
    };
    draw();
  }

  // ../engine/src/formats/numeric.ts
  function renderSettings(ctx) {
    const { q } = ctx;
    const values = asMap(q.response.values);
    let done = Boolean(q.response.done);
    const current = (row) => row.token in values ? values[row.token] : row.start;
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
        const buttons = [];
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
    ctx.root.append(device, doneToggle(ctx, done, (value) => {
      done = value;
      push();
    }));
  }
  var pad = (n) => String(n).padStart(2, "0");
  function show(row, value) {
    if (row.kind === "time") {
      const minutes = (value % 1440 + 1440) % 1440;
      return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)} ${row.unit || "IST"}`;
    }
    return `${value}${row.unit ? ` ${row.unit}` : ""}`;
  }
  function renderDial(ctx) {
    const { q } = ctx;
    const values = asMap(q.response.values);
    let done = Boolean(q.response.done);
    const push = () => ctx.save({ values, done });
    const wrap = el("div", { class: "eng-dials" });
    for (const row of q.rows) {
      const display = el("div", { class: "eng-val", "aria-live": "polite" });
      const get = () => row.token in values ? values[row.token] : row.start;
      const paint = () => {
        display.textContent = show(row, get());
      };
      const stepButton = (step) => {
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
        el("div", { class: "eng-dial" }, el("p", { class: "eng-label" }, row.label), el("div", { class: "eng-ctl" }, ...row.steps.filter((s) => s < 0).map(stepButton), display, ...row.steps.filter((s) => s > 0).map(stepButton)))
      );
    }
    clear(ctx.root);
    ctx.root.append(wrap, doneToggle(ctx, done, (value) => {
      done = value;
      push();
    }));
  }

  // ../engine/src/index.ts
  var RENDERERS = {
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
    crossword: renderCrossword
  };
  function waitForSave(form) {
    var _a2;
    const position = (_a2 = form.elements.namedItem("position")) == null ? void 0 : _a2.value;
    return new Promise((resolve) => {
      const handler = (event) => {
        const detail = event.detail;
        if (detail && String(detail.position) === position) {
          document.removeEventListener("ccfr:saved", handler);
          resolve();
        }
      };
      document.addEventListener("ccfr:saved", handler);
    });
  }
  function mount(root) {
    var _a2, _b;
    if (root.dataset.mounted) return;
    root.dataset.mounted = "1";
    const form = root.closest("form");
    const field = (_a2 = form == null ? void 0 : form.querySelector("[data-response]")) != null ? _a2 : null;
    const q = JSON.parse((_b = root.dataset.q) != null ? _b : "{}");
    const draw = RENDERERS[q.format];
    if (!draw || !form || !field) {
      root.textContent = t("This question can't be shown.");
      return;
    }
    const ctx = {
      root,
      q,
      imageUrl: root.dataset.imageUrl,
      save(response) {
        ctx.q.response = response;
        field.value = JSON.stringify(response);
        form.dispatchEvent(new Event("change", { bubbles: true }));
      },
      saved: () => waitForSave(form),
      async refetch() {
        var _a3;
        const reply = await fetch((_a3 = root.dataset.dataUrl) != null ? _a3 : "", { credentials: "same-origin", headers: { Accept: "application/json" } });
        if (!reply.ok) throw new Error("could not load");
        ctx.q = await reply.json();
        return ctx.q;
      }
    };
    clear(root);
    draw(ctx);
  }
  function boot() {
    document.querySelectorAll("[data-engine]").forEach(mount);
  }
  document.addEventListener("DOMContentLoaded", boot);
  var _a;
  (_a = document.body) == null ? void 0 : _a.addEventListener("htmx:afterSwap", boot);
  boot();
})();
