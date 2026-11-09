// Build dist/ for the Worker: the pages from web/, the photos the list uses and the
// list itself. Stops on a list the page could not show.
//
// Usage: npm run build

import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export interface Gift {
  id: string;
  /** The recipient's id, from `recipients`; never a name, the site is public. */
  for?: string;
  title: string;
  detail?: string;
  note?: string;
  photo: string;
}

export interface Recipient {
  id: string;
  label: string;
}

export interface GiftList {
  title: string;
  subtitle?: string;
  recipients?: Recipient[];
  gifts: Gift[];
}

const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Every problem with the list, so one run reports them all. */
export function problems(list: GiftList, photos: string[]): string[] {
  const found: string[] = [];
  if (!list.title) found.push("the list has no title");
  if (!Array.isArray(list.gifts) || list.gifts.length === 0) return [...found, "the list has no gifts"];
  const recipients = new Set((list.recipients ?? []).map((recipient) => recipient.id));
  const seen = new Set<string>();
  for (const [index, gift] of list.gifts.entries()) {
    const where = `gift ${index + 1} (${gift.id ?? "no id"})`;
    if (!ID.test(gift.id ?? "")) found.push(`${where}: the id must be lowercase words joined by dashes`);
    if (seen.has(gift.id)) found.push(`${where}: the id is repeated`);
    seen.add(gift.id);
    if (!gift.title) found.push(`${where}: no title`);
    if (gift.for !== undefined && !recipients.has(gift.for)) {
      found.push(`${where}: "${gift.for}" is not one of the recipients`);
    }
    if (!photos.includes(gift.photo)) found.push(`${where}: photos/${gift.photo} does not exist`);
  }
  return found;
}

function main(): void {
  const root = join(dirname(fileURLToPath(import.meta.url)), "..");
  const list = JSON.parse(readFileSync(join(root, "gifts.json"), "utf8")) as GiftList;
  const photos = readdirSync(join(root, "photos"));
  const found = problems(list, photos);
  if (found.length) {
    console.error(found.map((problem) => `gifts.json: ${problem}`).join("\n"));
    process.exit(1);
  }

  const dist = join(root, "dist");
  if (existsSync(dist)) rmSync(dist, { recursive: true });
  cpSync(join(root, "web"), dist, { recursive: true });
  mkdirSync(join(dist, "photos"));
  for (const gift of list.gifts) cpSync(join(root, "photos", gift.photo), join(dist, "photos", gift.photo));
  writeFileSync(join(dist, "gifts.json"), JSON.stringify(list));
  console.log(`dist/: ${list.gifts.length} gifts`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
