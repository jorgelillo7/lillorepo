// Just enough JPEG to publish a phone photo safely: read its EXIF orientation, and drop
// every metadata segment (EXIF with GPS, XMP, IPTC, comments) while keeping the image
// and its colour profile.

const SOI = 0xd8;
const SOS = 0xda;
const APP1 = 0xe1; // EXIF and XMP
const APP13 = 0xed; // IPTC
const COM = 0xfe;
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

/** The same JPEG without its metadata segments. */
export function stripMetadata(jpeg: Uint8Array): Uint8Array {
  const { list, scan } = segments(jpeg);
  const kept = [jpeg.subarray(0, 2)];
  for (const { marker, start, end } of list) {
    if (!DROPPED.has(marker)) kept.push(jpeg.subarray(start, end));
  }
  kept.push(jpeg.subarray(scan));
  const out = new Uint8Array(kept.reduce((total, part) => total + part.length, 0));
  let at = 0;
  for (const part of kept) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}
