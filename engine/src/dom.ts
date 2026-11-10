/* Tiny DOM helpers. Everything the renderers draw goes through here, and text is only ever set
   with textContent / text nodes: question content is never inserted as HTML. */

export type Child = Node | string | number | null | false | undefined;
type Attr = string | number | boolean | undefined | ((e: Event) => void);

const SVG_NS = "http://www.w3.org/2000/svg";

function apply(node: Element, attrs: Record<string, Attr>): void {
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    if (typeof value === "function") node.addEventListener(key.replace(/^on/, ""), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
}

function append(node: Element, children: Child[]): void {
  for (const child of children) {
    if (child === null || child === false || child === undefined) continue;
    node.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, Attr> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  apply(node, attrs);
  append(node, children);
  return node;
}

export function svg(tag: string, attrs: Record<string, Attr> = {}, ...children: Child[]): SVGElement {
  const node = document.createElementNS(SVG_NS, tag);
  apply(node, attrs);
  append(node, children);
  return node;
}

/** Children for Element.append(): drops null / false / undefined and turns numbers into text. */
export function nodes(...children: Child[]): (Node | string)[] {
  return children.filter((c): c is Node | string | number => c !== null && c !== false && c !== undefined).map((c) => (typeof c === "number" ? String(c) : c));
}

export function clear(node: Element): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

/** The shape cue (not just colour) that goes with each triage colour. */
export const TONES: Record<string, { name: string; shape: string }> = {
  red: { name: "Red", shape: "■" },
  amber: { name: "Amber", shape: "▲" },
  yellow: { name: "Yellow", shape: "◆" },
  green: { name: "Green", shape: "●" },
};
