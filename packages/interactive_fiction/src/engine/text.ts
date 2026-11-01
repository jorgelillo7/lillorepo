/** Text as compared against quotes: Harlowe's italic and bold marks dropped, whitespace collapsed. */
export function normalizeText(s: string): string {
  return s
    .replace(/\/\/|''/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Whether `quote` is still, word for word, in `text`. */
export function quotes(text: string, quote: string): boolean {
  return normalizeText(text).includes(normalizeText(quote));
}
