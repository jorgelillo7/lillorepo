import { describe, expect, test } from "vitest";
import { metadataMarkers, orientation, stripMetadata } from "../src/jpeg.ts";

const segment = (marker: number, payload: number[]) => [
  0xff,
  marker,
  (payload.length + 2) >> 8,
  (payload.length + 2) & 0xff,
  ...payload,
];
const ascii = (text: string) => [...text].map((c) => c.charCodeAt(0));

/** An EXIF block holding one tag, Orientation, in big-endian TIFF. */
function exif(value: number): number[] {
  const tiff = [0x4d, 0x4d, 0, 42, 0, 0, 0, 8, 0, 1, 0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, value, 0, 0, 0, 0, 0, 0];
  return [...ascii("Exif"), 0, 0, ...tiff, ...ascii("GPS")];
}

function photo(withExif: number | null): Uint8Array {
  return new Uint8Array([
    0xff, 0xd8,
    ...segment(0xe0, ascii("JFIF\0")),
    ...(withExif === null ? [] : segment(0xe1, exif(withExif))),
    ...segment(0xfe, ascii("a comment")),
    ...segment(0xdb, [1, 2, 3]),
    0xff, 0xda, 0, 4, 9, 9, 7, 7, 0xff, 0xd9,
  ]);
}

const text = (bytes: Uint8Array) => Buffer.from(bytes).toString("latin1");

describe("jpeg", () => {
  test("reads the EXIF orientation, and 1 when there is none", () => {
    expect(orientation(photo(6))).toBe(6);
    expect(orientation(photo(null))).toBe(1);
  });

  test("drops EXIF, GPS and comments and keeps the image segments", () => {
    const clean = stripMetadata(photo(6));
    expect(text(clean)).not.toMatch(/Exif|GPS|a comment/);
    expect(text(clean)).toContain("JFIF");
    expect(clean.subarray(-6)).toEqual(new Uint8Array([9, 9, 7, 7, 0xff, 0xd9]));
    expect(stripMetadata(clean)).toEqual(clean);
  });

  test("refuses what is not a JPEG", () => {
    expect(() => stripMetadata(new Uint8Array([0x89, 0x50, 0x4e, 0x47]))).toThrow(/not a JPEG/);
  });

  test("finds metadata by its segments, not by bytes that happen to spell a tag", () => {
    expect(metadataMarkers(photo(6))).toEqual([0xe1, 0xfe]);
    const clean = stripMetadata(photo(null));
    expect(metadataMarkers(clean)).toEqual([]);
    // Image data that contains the words EXIF and GPS by chance is still a clean photo.
    const unlucky = new Uint8Array([
      0xff, 0xd8,
      ...segment(0xe0, ascii("JFIF\0")),
      ...segment(0xdb, [1, 2, 3]),
      0xff, 0xda, 0, 4, 9, 9, ...ascii("Exif"), ...ascii("GPS"), 0xff, 0xd9,
    ]);
    expect(text(unlucky)).toMatch(/Exif.*GPS/);
    expect(metadataMarkers(stripMetadata(unlucky))).toEqual([]);
  });
});
