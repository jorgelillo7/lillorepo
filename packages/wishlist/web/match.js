/** Lowercased, without accents, so "camion" finds "Camión". */
export function fold(text) {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

/** True when every word of the search appears in the gift's name, in any order. */
export function nameMatches(name, search) {
  const words = fold(search).split(/\s+/).filter(Boolean);
  const folded = fold(name);
  return words.every((word) => folded.includes(word));
}
