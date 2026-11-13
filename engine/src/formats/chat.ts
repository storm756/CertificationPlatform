/* chat: a short branching conversation. The next step is fetched from the server only after the
   learner's reply has been saved, so later steps (and their replies) are never in the browser. */

import { t } from "../i18n";
import { clear, el } from "../dom";
import type { Base, Ctx, Tokened } from "../types";
import { asList } from "./shared";

interface ChatQ extends Base {
  who: string;
  total_steps: number;
  steps: { say: string; chosen?: string; text?: string; replies?: Tokened[] }[];
}

export function renderChat(ctx: Ctx<ChatQ>): void {
  const stage = el("div", { class: "eng-chat" });
  ctx.root.append(stage);
  const replies = asList<string>(ctx.q.response.replies);
  const draw = () => {
    const q = ctx.q;
    clear(stage);
    const log = el("div", { class: "eng-log", "aria-live": "polite" });
    for (const step of q.steps) {
      log.append(el("div", { class: "eng-bub eng-bub--them" }, el("span", { class: "eng-who" }, q.who), step.say));
      if (step.chosen !== undefined) log.append(el("div", { class: "eng-bub eng-bub--me" }, el("span", { class: "eng-who" }, t("You")), step.text ?? ""));
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
            await ctx.saved(); // the reply is on the server; only now ask for the next step
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
