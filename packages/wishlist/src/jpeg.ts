// Just enough JPEG to publish a phone photo safely, for the Worker and for
// scripts/photo.ts: read the EXIF orientation, drop every metadata segment (EXIF with
// GPS, XMP, IPTC, comments), and rebuild an uploaded file as a baseline JPEG that
// carries nothing but the image.

const SOI = 0xd8;
const EOI = 0xd9;
const SOS = 0xda;
const APP0 = 0xe0;
const APP1 = 0xe1; // EXIF and XMP
const APP2 = 0xe2; // ICC colour profile, but also the multi-picture block of phones
const APP13 = 0xed; // IPTC
const APP14 = 0xee; // Adobe colour transform
const COM = 0xfe;
const DHT = 0xc4;
const DQT = 0xdb;
const DRI = 0xdd;
const SOF_BASELINE = 0xc0;
const DROPPED = new Set([APP1, APP13, COM]);

interface Segment {
  marker: number;
  start: number;
  end: number;
}

function segments(jpeg: Uint8Array): { list: Segment[]; scan: number } {
  if (jpeg[0] !== 0xff || jpeg[1] !== SOI) throw new Error("not a JPEG");
  const list: Segment[] = [];
  let at = 2;
  while (at + 4 <= jpeg.length) {
    if (jpeg[at] !== 0xff) throw new Error(`broken JPEG at byte ${at}`);
    const marker = jpeg[at + 1];
    if (marker === SOS) return { list, scan: at };
    const length = (jpeg[at + 2] << 8) | jpeg[at + 3];
    if (length < 2 || at + 2 + length > jpeg.length) throw new Error(`broken JPEG at byte ${at}`);
    list.push({ marker, start: at, end: at + 2 + length });
    at += 2 + length;
  }
  throw new Error("JPEG without image data");
}

/** The EXIF orientation (1 to 8), or 1 when the photo has none. */
export function orientation(jpeg: Uint8Array): number {
  for (const { marker, start, end } of segments(jpeg).list) {
    if (marker !== APP1) continue;
    const exif = jpeg.subarray(start + 4, end);
    if (String.fromCharCode(...exif.subarray(0, 4)) !== "Exif") continue;
    const tiff = exif.subarray(6);
    const view = new DataView(tiff.buffer, tiff.byteOffset, tiff.byteLength);
    const little = tiff[0] === 0x49;
    const ifd = view.getUint32(4, little);
    const count = view.getUint16(ifd, little);
    for (let i = 0; i < count; i++) {
      const entry = ifd + 2 + i * 12;
      if (view.getUint16(entry, little) === 0x0112) return view.getUint16(entry + 8, little);
    }
  }
  return 1;
}

function join(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

/** The same JPEG without its metadata segments. */
export function stripMetadata(jpeg: Uint8Array): Uint8Array {
  const { list, scan } = segments(jpeg);
  const kept = [jpeg.subarray(0, 2)];
  for (const { marker, start, end } of list) {
    if (!DROPPED.has(marker)) kept.push(jpeg.subarray(start, end));
  }
  kept.push(jpeg.subarray(scan));
  return join(kept);
}

/** Markers of the metadata segments a JPEG still carries: EXIF, XMP, IPTC, comments and other application blocks. */
export function metadataMarkers(jpeg: Uint8Array): number[] {
  return segments(jpeg)
    .list.filter((segment) => DISCARDED.has(segment.marker) && !keeps(jpeg, segment))
    .map((segment) => segment.marker);
}

export type CleanJpeg = { ok: true; bytes: Uint8Array; width: number; height: number } | { ok: false; reason: string };

const startsWith = (jpeg: Uint8Array, segment: Segment, text: string): boolean =>
  String.fromCharCode(...jpeg.subarray(segment.start + 4, segment.start + 4 + text.length)) === text;

/** Whether a segment before the scan carries image data or colour, as opposed to metadata. */
function keeps(jpeg: Uint8Array, segment: Segment): boolean {
  switch (segment.marker) {
    case DHT:
    case DQT:
    case DRI:
    case SOF_BASELINE:
      return true;
    case APP0:
      return startsWith(jpeg, segment, "JFIF\0");
    case APP2:
      return startsWith(jpeg, segment, "ICC_PROFILE\0");
    case APP14:
      return startsWith(jpeg, segment, "Adobe");
    default:
      return false;
  }
}

// Every application segment and comment: dropped unless keeps() recognises it.
const DISCARDED = new Set([...Array.from({ length: 16 }, (_, i) => APP0 + i), COM]);

/**
 * Rebuild an uploaded file as a single-scan baseline JPEG no larger than `maxSide` on
 * either side: only the tables, the frame, the optional colour profile and the scan
 * survive, and whatever follows the end-of-image marker (a second picture some phones
 * append, thumbnails, trailing data) is cut. A file that is not that, or that would
 * display turned by an EXIF orientation this drops, is refused.
 */
export function cleanBaseline(jpeg: Uint8Array, maxSide: number): CleanJpeg {
  try {
    const { list, scan } = segments(jpeg);
    if (orientation(jpeg) !== 1) return { ok: false, reason: "orientation" };
    let frame: Segment | undefined;
    for (const segment of list) {
      if (segment.marker === SOF_BASELINE) {
        if (frame) return { ok: false, reason: "not baseline" };
        frame = segment;
      } else if (!keeps(jpeg, segment) && !DISCARDED.has(segment.marker)) {
        return { ok: false, reason: "not baseline" };
      }
    }
    if (!frame) return { ok: false, reason: "not baseline" };
    if (!list.some((s) => s.marker === DQT) || !list.some((s) => s.marker === DHT)) {
      return { ok: false, reason: "not baseline" };
    }
    const header = jpeg.subarray(frame.start + 4, frame.end);
    const height = (header[1] << 8) | header[2];
    const width = (header[3] << 8) | header[4];
    if (header[0] !== 8 || (header[5] !== 1 && header[5] !== 3) || !width || !height) {
      return { ok: false, reason: "not baseline" };
    }
    if (width > maxSide || height > maxSide) return { ok: false, reason: "too large" };

    const first = scan + 2 + ((jpeg[scan + 2] << 8) | jpeg[scan + 3]);
    let end = -1;
    for (let at = first; at + 1 < jpeg.length; ) {
      if (jpeg[at] !== 0xff) {
        at++;
        continue;
      }
      const next = jpeg[at + 1];
      if (next === 0x00 || (next >= 0xd0 && next <= 0xd7)) at += 2;
      else if (next === EOI) {
        end = at + 2;
        break;
      } else return { ok: false, reason: "not baseline" };
    }
    if (end < 0) return { ok: false, reason: "truncated" };

    const parts = [jpeg.subarray(0, 2)];
    for (const segment of list) if (keeps(jpeg, segment)) parts.push(jpeg.subarray(segment.start, segment.end));
    parts.push(jpeg.subarray(scan, end));
    return { ok: true, bytes: join(parts), width, height };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : "invalid" };
  }
}
