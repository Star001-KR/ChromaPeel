// Filename sanitisation shared by chroma · grid · crop save paths.
// Strip path separators and characters illegal in Windows filenames,
// then strip trailing dots / whitespace.
export function sanitizeStem(s) {
  return s.replace(/[/\\:*?"<>|\x00-\x1f]/g, '').replace(/\.+$/, '').trim();
}
