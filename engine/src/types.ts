/* What the server sends for each question (apps/questions/formats.py `project`): text and random
   one-off tokens. There is no key, no risky flag and no canonical order in any of these. */

export interface Base {
  format: string;
  title: string;
  ask: string;
  scene: string;
  response: Record<string, unknown>;
}

export interface Tokened {
  token: string;
  text: string;
}

export interface Ctx<Q extends Base = Base> {
  root: HTMLElement;
  q: Q;
  /** Save the learner's whole answer for this question (tokens only). */
  save(response: Record<string, unknown>): void;
  /** The pending save has reached the server (resolves after the next successful save). */
  saved(): Promise<void>;
  /** Fetch the question again from the server (chat uses this for its next step). */
  refetch(): Promise<Base>;
  imageUrl?: string;
}

export type Renderer = (ctx: Ctx<any>) => void;
