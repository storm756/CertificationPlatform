// Mailpit's HTTP API (the dev stack and CI run Mailpit). MAILPIT_URL is empty on staging, where real
// mail goes out; the journeys that need an e-mailed link skip there (e2e/README.md).
export const mailpit = process.env.MAILPIT_URL || "";

type Message = { ID: string; To: { Address: string }[]; Subject: string };

async function api(path: string, init?: RequestInit) {
  const res = await fetch(mailpit.replace(/\/$/, "") + path, init);
  if (!res.ok) throw new Error(`Mailpit ${path}: ${res.status}`);
  return res;
}

/** The first link (path and query) in the newest message to `address` whose text matches `pattern`. */
export async function linkFor(address: string, pattern: RegExp, tries = 20): Promise<string> {
  for (let i = 0; i < tries; i++) {
    const list = (await (await api("/api/v1/messages?limit=50")).json()) as { messages: Message[] };
    for (const m of list.messages) {
      if (!m.To.some((t) => t.Address.toLowerCase() === address.toLowerCase())) continue;
      const body = (await (await api(`/api/v1/message/${m.ID}`)).json()) as { Text: string };
      const found = body.Text.match(pattern);
      if (found) {
        const url = new URL(found[0]);
        return url.pathname + url.search;
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No e-mail link for ${address} matching ${pattern}`);
}
