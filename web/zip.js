// Store-mode ZIP builder (no compression — PNGs are already compressed).
// PKZIP APPNOTE: local file header + central directory + EOCD.
// UTF-8 filenames via GPB flag bit 11. Pure functions, no DOM.

const CRC32_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    t[i] = c >>> 0;
  }
  return t;
})();

export function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = CRC32_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

export async function buildZip(files) {
  const encoder = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;

  for (const f of files) {
    const data = new Uint8Array(await f.blob.arrayBuffer());
    const nameBytes = encoder.encode(f.name);
    const crc = crc32(data);
    const size = data.length;

    const lh = new ArrayBuffer(30 + nameBytes.length);
    const lhV = new DataView(lh);
    lhV.setUint32(0, 0x04034b50, true);
    lhV.setUint16(4, 20, true);          // version needed
    lhV.setUint16(6, 0x0800, true);      // GPB flag: UTF-8 filename
    lhV.setUint16(8, 0, true);           // method: store
    lhV.setUint16(10, 0, true);          // mod time
    lhV.setUint16(12, 0x0021, true);     // mod date (1996-01-01)
    lhV.setUint32(14, crc, true);
    lhV.setUint32(18, size, true);       // compressed size
    lhV.setUint32(22, size, true);       // uncompressed size
    lhV.setUint16(26, nameBytes.length, true);
    lhV.setUint16(28, 0, true);          // extra len
    new Uint8Array(lh, 30).set(nameBytes);

    parts.push(new Uint8Array(lh));
    parts.push(data);

    const ch = new ArrayBuffer(46 + nameBytes.length);
    const chV = new DataView(ch);
    chV.setUint32(0, 0x02014b50, true);
    chV.setUint16(4, 20, true);          // version made by
    chV.setUint16(6, 20, true);          // version needed
    chV.setUint16(8, 0x0800, true);
    chV.setUint16(10, 0, true);
    chV.setUint16(12, 0, true);
    chV.setUint16(14, 0x0021, true);
    chV.setUint32(16, crc, true);
    chV.setUint32(20, size, true);
    chV.setUint32(24, size, true);
    chV.setUint16(28, nameBytes.length, true);
    chV.setUint16(30, 0, true);          // extra
    chV.setUint16(32, 0, true);          // comment
    chV.setUint16(34, 0, true);          // disk number
    chV.setUint16(36, 0, true);          // internal attrs
    chV.setUint32(38, 0, true);          // external attrs
    chV.setUint32(42, offset, true);     // local header offset
    new Uint8Array(ch, 46).set(nameBytes);
    central.push(new Uint8Array(ch));

    offset += 30 + nameBytes.length + size;
  }

  let centralSize = 0;
  for (const c of central) centralSize += c.length;

  const eocd = new ArrayBuffer(22);
  const eV = new DataView(eocd);
  eV.setUint32(0, 0x06054b50, true);
  eV.setUint16(4, 0, true);
  eV.setUint16(6, 0, true);
  eV.setUint16(8, files.length, true);
  eV.setUint16(10, files.length, true);
  eV.setUint32(12, centralSize, true);
  eV.setUint32(16, offset, true);
  eV.setUint16(20, 0, true);

  return new Blob([...parts, ...central, new Uint8Array(eocd)], {
    type: 'application/zip',
  });
}
