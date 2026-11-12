import { readFileSync, readdirSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import type { Database, Env, Statement } from "../src/types.ts";

export const ORIGIN = "https://wishlist.test";
export const ADMIN = "Basic " + Buffer.from("me:long secret").toString("base64");

const MIGRATIONS = new URL("../migrations/", import.meta.url);

/** D1's surface over Node's SQLite, running every real migration in order. */
export function database(): { db: Database; sqlite: DatabaseSync } {
  const sqlite = new DatabaseSync(":memory:");
  for (const file of readdirSync(MIGRATIONS).sort()) {
    sqlite.exec(readFileSync(new URL(file, MIGRATIONS), "utf8"));
  }
  const statementOf = (sql: string): Statement => {
    let values: unknown[] = [];
    const statement: Statement = {
      bind(...given: unknown[]) {
        values = given;
        return statement;
      },
      async run() {
        const result = sqlite.prepare(sql).run(...(values as never[]));
        return { meta: { changes: Number(result.changes) } };
      },
      async all<T>() {
        return { results: sqlite.prepare(sql).all(...(values as never[])) as T[] };
      },
    };
    return statement;
  };
  return {
    sqlite,
    db: {
      prepare: statementOf,
      async batch(statements: Statement[]) {
        sqlite.exec("BEGIN");
        try {
          const results = [];
          for (const statement of statements) results.push(await statement.run());
          sqlite.exec("COMMIT");
          return results;
        } catch (error) {
          sqlite.exec("ROLLBACK");
          throw error;
        }
      },
    },
  };
}

export function environment(db: Database, served: string[] = []): Env {
  return {
    DB: db,
    ASSETS: {
      fetch: async (request: Request) => {
        served.push(new URL(request.url).pathname);
        return new Response("ASSET");
      },
    },
    ADMIN_USER: "me",
    ADMIN_PASSWORD: "long secret",
  };
}

const segment = (marker: number, payload: number[]) => [
  0xff,
  marker,
  (payload.length + 2) >> 8,
  (payload.length + 2) & 0xff,
  ...payload,
];
const ascii = (text: string) => [...text].map((c) => c.charCodeAt(0));

/** Latitude/longitude as the GPS IFD of a big-endian EXIF block, plus an orientation tag. */
function exifWithGps(orientation: number): number[] {
  const tiff = [
    0x4d, 0x4d, 0, 42, 0, 0, 0, 8,
    // IFD0: Orientation and a pointer to the GPS IFD at offset 38.
    0, 2,
    0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, orientation, 0, 0,
    0x88, 0x25, 0, 4, 0, 0, 0, 1, 0, 0, 0, 38,
    0, 0, 0, 0,
    // GPS IFD: latitude reference and a degrees value.
    0, 2,
    0, 1, 0, 2, 0, 0, 0, 2, 0x4e, 0, 0, 0,
    0, 2, 0, 5, 0, 0, 0, 3, 0, 0, 0, 80,
    0, 0, 0, 0,
    0, 0, 0, 40, 0, 0, 0, 1, 0, 0, 0, 25, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1,
  ];
  return [...ascii("Exif"), 0, 0, ...tiff, ...ascii("GPSLatitude 40.4168 N")];
}

export interface PhotoOptions {
  orientation?: number;
  /** SOF marker: 0xc0 is baseline, 0xc2 progressive. */
  frame?: number;
  width?: number;
  height?: number;
  /** Bytes of entropy data, to make the file as large as a test needs. */
  padding?: number;
}

/**
 * A structurally valid baseline JPEG the way a phone writes it: EXIF with GPS, a
 * multi-picture block, IPTC and a comment before the image, and a second picture with
 * its own EXIF appended after the end-of-image marker.
 */
export function phonePhoto(options: PhotoOptions = {}): Uint8Array {
  const { orientation = 1, frame = 0xc0, width = 64, height = 48, padding = 0 } = options;
  const entropy = [0x12, 0xff, 0x00, 0x34, ...new Array<number>(padding).fill(0x56)];
  return new Uint8Array([
    0xff, 0xd8,
    ...segment(0xe0, ascii("JFIF\0")),
    ...segment(0xe1, exifWithGps(orientation)),
    ...segment(0xe2, ascii("MPF\0second image")),
    ...segment(0xed, ascii("Photoshop 3.0 IPTC")),
    ...segment(0xfe, ascii("shot at home")),
    ...segment(0xdb, [0, ...new Array<number>(64).fill(3)]),
    ...segment(frame, [8, height >> 8, height & 0xff, width >> 8, width & 0xff, 1, 1, 0x11, 0]),
    ...segment(0xc4, [0, ...new Array<number>(16).fill(0), 7]),
    0xff, 0xda, 0, 8, 1, 1, 0, 0, 63, 0,
    ...entropy,
    0xff, 0xd9,
    // The appended second picture.
    0xff, 0xd8, ...segment(0xe1, exifWithGps(1)), 0xff, 0xd9,
  ]);
}

export const asText = (bytes: Uint8Array) => Buffer.from(bytes).toString("latin1");
