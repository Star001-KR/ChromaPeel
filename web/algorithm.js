// ChromaPeel — algorithm core (Python parity).
// Pure functions, no DOM. Mirrors imageAlpha.py byte-for-byte; the
// js_parity_runner imports this module directly to verify every
// pixel matches the Python reference.

// Multi-color detection — mirrors detect_background_colors() in imageAlpha.py.
// Sort order: count desc, then packed RGB key asc (= R asc, G asc, B asc).
// This matches Python's np.lexsort with (B, G, R, -count) keys so JS and Python
// agree on tie-breaks byte-for-byte.
export function detectBackgroundColors(imageData, minRatio = 0.05, maxK = 8) {
  const { data, width, height } = imageData;
  const counts = new Map();
  const tally = (idx) => {
    const key = (data[idx] << 16) | (data[idx + 1] << 8) | data[idx + 2];
    counts.set(key, (counts.get(key) || 0) + 1);
  };
  for (let x = 0; x < width; x++) {
    tally((0 * width + x) * 4);
    tally(((height - 1) * width + x) * 4);
  }
  for (let y = 0; y < height; y++) {
    tally((y * width + 0) * 4);
    tally((y * width + (width - 1)) * 4);
  }
  const entries = [...counts.entries()];
  entries.sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    return a[0] - b[0];
  });
  let total = 0;
  for (const [, c] of entries) total += c;
  const accepted = [];
  for (const [key, cnt] of entries) {
    if (accepted.length > 0 && cnt / total < minRatio) break;
    accepted.push([(key >> 16) & 0xff, (key >> 8) & 0xff, key & 0xff]);
    if (accepted.length >= maxK) break;
  }
  return accepted;
}

export function detectBackgroundColor(imageData) {
  return detectBackgroundColors(imageData, 0.0, 1)[0];
}

export function clampToInt(v) {
  // Match Python's np.clip(...).astype(np.uint8) — clamp then truncate.
  // Uint8ClampedArray would otherwise round to nearest even, off by 1 from Python.
  if (v < 0) return 0;
  if (v > 255) return 255;
  return v | 0;
}

// Resolve which colors to remove. Mirrors the Python branch in remove_color().
function resolveTargetColors(srcImageData, params) {
  if (params.targetColor != null && params.targetColors != null) {
    throw new Error('targetColor 와 targetColors 는 동시에 지정할 수 없습니다.');
  }
  if (params.targetColors != null) {
    if (params.targetColors.length === 0) {
      throw new Error('targetColors 가 비어 있습니다.');
    }
    return params.targetColors;
  }
  if (params.targetColor != null) {
    return [params.targetColor];
  }
  return detectBackgroundColors(srcImageData);
}

export function processImage(srcImageData, params) {
  const { width, height } = srcImageData;
  const src = srcImageData.data;
  const out = new Uint8ClampedArray(src);
  const colors = resolveTargetColors(srcImageData, params);
  const K = colors.length;
  const singleColor = K === 1;
  const tol = params.tolerance;
  const feather = params.feather;
  const decon = params.decontaminate;
  const erosion = params.edgeErosion;
  const n = width * height;

  const alphaMul = new Float32Array(n);

  // K=1 fast path = original byte-for-byte single-color behavior.
  // K>1 branch tracks per-pixel nearest target color for decontamination.
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const r = src[o], g = src[o + 1], b = src[o + 2];
    let dist, nearestK;
    if (singleColor) {
      const tr = colors[0][0], tg = colors[0][1], tb = colors[0][2];
      const dr = r > tr ? r - tr : tr - r;
      const dg = g > tg ? g - tg : tg - g;
      const db = b > tb ? b - tb : tb - b;
      dist = dr > dg ? (dr > db ? dr : db) : (dg > db ? dg : db);
      nearestK = 0;
    } else {
      let minDist = 256;
      let mk = 0;
      for (let k = 0; k < K; k++) {
        const tr = colors[k][0], tg = colors[k][1], tb = colors[k][2];
        const dr = r > tr ? r - tr : tr - r;
        const dg = g > tg ? g - tg : tg - g;
        const db = b > tb ? b - tb : tb - b;
        const d = dr > dg ? (dr > db ? dr : db) : (dg > db ? dg : db);
        if (d < minDist) { minDist = d; mk = k; }
      }
      dist = minDist;
      nearestK = mk;
    }

    let m = 1.0;
    if (dist <= tol) {
      m = 0.0;
    } else if (feather > 0 && dist <= tol + feather) {
      m = (dist - tol) / feather;
      if (decon) {
        const tr = colors[nearestK][0];
        const tg = colors[nearestK][1];
        const tb = colors[nearestK][2];
        const t = 1.0 - m;
        const denom = 1.0 - t < 1e-6 ? 1e-6 : 1.0 - t;
        out[o]     = clampToInt((r - t * tr) / denom);
        out[o + 1] = clampToInt((g - t * tg) / denom);
        out[o + 2] = clampToInt((b - t * tb) / denom);
      }
    }
    alphaMul[i] = m;
  }

  for (let i = 0; i < n; i++) {
    out[i * 4 + 3] = (src[i * 4 + 3] * alphaMul[i]) | 0;
  }

  if (erosion > 0) {
    let cur = new Uint8ClampedArray(n);
    let nxt = new Uint8ClampedArray(n);
    for (let i = 0; i < n; i++) cur[i] = out[i * 4 + 3];
    const w = width, h = height;
    for (let pass = 0; pass < erosion; pass++) {
      for (let y = 0; y < h; y++) {
        const yUp = y === 0 ? 0 : y - 1;
        const yDn = y === h - 1 ? h - 1 : y + 1;
        for (let x = 0; x < w; x++) {
          const xL = x === 0 ? 0 : x - 1;
          const xR = x === w - 1 ? w - 1 : x + 1;
          let mn = cur[yUp * w + xL];
          let v;
          v = cur[yUp * w + x];  if (v < mn) mn = v;
          v = cur[yUp * w + xR]; if (v < mn) mn = v;
          v = cur[y   * w + xL]; if (v < mn) mn = v;
          v = cur[y   * w + x];  if (v < mn) mn = v;
          v = cur[y   * w + xR]; if (v < mn) mn = v;
          v = cur[yDn * w + xL]; if (v < mn) mn = v;
          v = cur[yDn * w + x];  if (v < mn) mn = v;
          v = cur[yDn * w + xR]; if (v < mn) mn = v;
          nxt[y * w + x] = mn;
        }
      }
      const tmp = cur; cur = nxt; nxt = tmp;
    }
    for (let i = 0; i < n; i++) out[i * 4 + 3] = cur[i];
  }

  let result = new ImageData(out, width, height);

  if (params.autoTrim) {
    const trimmed = trimTransparentEdges(
      result,
      params.trimAlphaThreshold || 0,
      params.trimPadding || 0,
    );
    if (trimmed === null) {
      // Match Python: skip with warning, keep original
      console.warn('자동 트림 스킵: 모든 픽셀이 투명입니다');
    } else {
      result = trimmed;
    }
  }

  return result;
}

export function trimTransparentEdges(imageData, alphaThreshold, padding) {
  const { data, width, height } = imageData;
  let top = -1, bottom = -1, left = width, right = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const a = data[(y * width + x) * 4 + 3];
      if (a > alphaThreshold) {
        if (top === -1) top = y;
        bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
  }
  if (top === -1) return null;

  // Match PIL.Image.crop: right/bottom are exclusive.
  let l = left, t = top, r = right + 1, b = bottom + 1;
  if (padding > 0) {
    l = Math.max(0, l - padding);
    t = Math.max(0, t - padding);
    r = Math.min(width, r + padding);
    b = Math.min(height, b + padding);
  }
  const newW = r - l, newH = b - t;
  const out = new Uint8ClampedArray(newW * newH * 4);
  for (let y = 0; y < newH; y++) {
    const srcRow = ((t + y) * width + l) * 4;
    const dstRow = y * newW * 4;
    out.set(data.subarray(srcRow, srcRow + newW * 4), dstRow);
  }
  return new ImageData(out, newW, newH);
}
