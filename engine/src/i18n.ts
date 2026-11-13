/* The engine's own labels in the learner's language (Stage 8).

   The page carries a table {English: translation} made by the server with gettext and inserted
   with Django's json_script (apps/questions/engine_labels.py). It holds interface labels only: no
   question text, no answers. A label that is missing from the table stays in English.
   Crosswords keep their labels in English (D33). */

let table: Record<string, string> | null = null;

function load(): Record<string, string> {
  if (table === null) {
    table = {};
    const node = document.getElementById("engine-labels");
    try {
      const parsed = node ? (JSON.parse(node.textContent ?? "{}") as unknown) : {};
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) table = parsed as Record<string, string>;
    } catch {
      table = {};
    }
  }
  return table;
}

/** `text` in the page's language. `{name}` placeholders are filled from `vars` after lookup. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const found = load()[text];
  let out = typeof found === "string" && found ? found : text;
  if (vars) for (const [key, value] of Object.entries(vars)) out = out.split(`{${key}}`).join(String(value));
  return out;
}
