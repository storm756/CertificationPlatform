import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// The seed prints this file: `manage.py e2e_seed > e2e/manifest.json` (see e2e/README.md).
const here = dirname(fileURLToPath(import.meta.url));
const path = process.env.E2E_MANIFEST || join(here, "..", "manifest.json");

export type Manifest = {
  password: string;
  totp_secret: string;
  domain: string;
  batches: Record<string, number>;
  users: Record<string, string>;
  learner_ids: Record<string, number>;
  parts: { mcq: number; gate: number; extra: number };
  final_question_id: number | null;
  exam_set: string;
};

export const manifest: Manifest = JSON.parse(readFileSync(path, "utf8"));
export const user = (key: string): string => {
  const email = manifest.users[key];
  if (!email) throw new Error(`No seeded user '${key}'`);
  return email;
};
