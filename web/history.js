// Result history — IndexedDB-backed FIFO of up to 10 chroma results.
//
// Storage: DB 'chromapeel' (v1), store 'history' { id pk autoIncrement,
// filename, timestamp, blob, size_bytes }. timestamp index for DESC sort.
//
// Lifecycle: addHistoryItem() is called from chroma.js right after a
// successful processedBlob is produced. We store the blob, then evict the
// oldest rows down to MAX_ITEMS, then re-render the UI. URLs for the
// rendered thumbnails are tracked in `live` and revoked on remove / reload.
//
// Quota: addHistoryItem retries on QuotaExceededError by evicting the
// oldest item one at a time. If the store empties and the write still
// fails, we surface a toast and give up.
//
// Dedup: addHistoryItem skips a blob it already stored as the latest card, so
// repeated saves of one result don't pile up; deleting that card clears the
// marker so the same result can be saved again.
import { $ } from './dom.js';

const DB_NAME = 'chromapeel';
const DB_VERSION = 1;
const STORE = 'history';
const MAX_ITEMS = 10;

let dbPromise = null;
// id → object URL for currently rendered cards (revoked on remove/reload).
const live = new Map();

// Dedup marker — chroma.js's saveOrShare may call addHistoryItem repeatedly for
// the same result (re-download, cancelled share, double-click). We remember the
// { blob, id } of the last stored card and skip an identical blob; the marker
// is cleared when that card is deleted so re-saving restores it.
let lastSaved = null;

function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, {
          keyPath: 'id',
          autoIncrement: true,
        });
        store.createIndex('timestamp', 'timestamp');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function tx(mode) {
  return openDB().then((db) => db.transaction(STORE, mode).objectStore(STORE));
}

function getAllDesc() {
  return tx('readonly').then(
    (store) =>
      new Promise((resolve, reject) => {
        const items = [];
        const req = store.index('timestamp').openCursor(null, 'prev');
        req.onsuccess = () => {
          const cur = req.result;
          if (cur) {
            items.push(cur.value);
            cur.continue();
          } else {
            resolve(items);
          }
        };
        req.onerror = () => reject(req.error);
      })
  );
}

function deleteOne(id) {
  return tx('readwrite').then(
    (store) =>
      new Promise((resolve, reject) => {
        const req = store.delete(id);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      })
  );
}

function getOldestId() {
  return tx('readonly').then(
    (store) =>
      new Promise((resolve, reject) => {
        const req = store.index('timestamp').openCursor(null, 'next');
        req.onsuccess = () => {
          const cur = req.result;
          resolve(cur ? cur.value.id : null);
        };
        req.onerror = () => reject(req.error);
      })
  );
}

function putRecord(record) {
  return tx('readwrite').then(
    (store) =>
      new Promise((resolve, reject) => {
        const req = store.add(record);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      })
  );
}

function isQuotaError(err) {
  if (!err) return false;
  if (err.name === 'QuotaExceededError') return true;
  // Some browsers nest the DOMException
  if (err.target && err.target.error && err.target.error.name === 'QuotaExceededError') return true;
  return false;
}

let toastTimer = null;
function showToast(msg) {
  let el = $('historyToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'historyToast';
    el.className = 'history-toast';
    el.setAttribute('role', 'alert');
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('is-visible');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove('is-visible');
  }, 4000);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(ts) {
  const d = new Date(ts);
  const pad = (v) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function revokeLive(id) {
  const url = live.get(id);
  if (url) {
    URL.revokeObjectURL(url);
    live.delete(id);
  }
}

function revokeAllLive() {
  for (const url of live.values()) URL.revokeObjectURL(url);
  live.clear();
}

async function renderHistory() {
  const list = $('historyList');
  const summary = $('historySummary');
  const empty = $('historyEmpty');
  if (!list) return;

  let items;
  try {
    items = await getAllDesc();
  } catch (e) {
    list.innerHTML = '';
    summary.textContent = '저장소 로드 실패';
    return;
  }

  revokeAllLive();
  list.innerHTML = '';
  const frag = document.createDocumentFragment();
  let totalBytes = 0;

  for (const it of items) {
    totalBytes += it.size_bytes || 0;
    const url = URL.createObjectURL(it.blob);
    live.set(it.id, url);

    const card = document.createElement('div');
    card.className = 'history-card';

    const thumb = document.createElement('img');
    thumb.className = 'history-thumb';
    thumb.src = url;
    thumb.alt = it.filename;
    thumb.loading = 'lazy';
    card.appendChild(thumb);

    const meta = document.createElement('div');
    meta.className = 'history-meta';
    const name = document.createElement('div');
    name.className = 'history-name';
    name.textContent = it.filename;
    name.title = it.filename;
    meta.appendChild(name);
    const sub = document.createElement('div');
    sub.className = 'history-sub muted';
    sub.textContent = `${formatTime(it.timestamp)} · ${formatBytes(it.size_bytes || 0)}`;
    meta.appendChild(sub);
    card.appendChild(meta);

    const actions = document.createElement('div');
    actions.className = 'history-actions';
    const dl = document.createElement('button');
    dl.type = 'button';
    dl.className = 'history-btn';
    dl.textContent = '다운로드';
    dl.addEventListener('click', () => downloadBlob(it.blob, it.filename));
    actions.appendChild(dl);
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'history-btn ghost';
    del.textContent = '삭제';
    del.addEventListener('click', async () => {
      try {
        await deleteOne(it.id);
        revokeLive(it.id);
        // If this was the just-saved card, clear the dedup marker so the same
        // result can be saved again (addHistoryItem would otherwise skip it).
        if (lastSaved && lastSaved.id === it.id) lastSaved = null;
        await renderHistory();
      } catch (_) {
        showToast('삭제 실패');
      }
    });
    actions.appendChild(del);
    card.appendChild(actions);

    frag.appendChild(card);
  }
  list.appendChild(frag);

  if (items.length === 0) {
    empty.style.display = '';
    summary.textContent = '사용 중: 0 B / 0개';
  } else {
    empty.style.display = 'none';
    summary.textContent = `사용 중: ${formatBytes(totalBytes)} / ${items.length}개`;
  }
}

export async function addHistoryItem({ filename, blob }) {
  if (!blob) return;
  // Dedup — skip a blob already stored as the latest card. This check and flip
  // run synchronously before the first await, so a double-clicked saveOrShare
  // is blocked on its second call.
  if (lastSaved && lastSaved.blob === blob) return;
  lastSaved = { blob, id: null };  // id filled in after putRecord succeeds

  const record = {
    filename,
    timestamp: Date.now(),
    blob,
    size_bytes: blob.size,
  };

  // First, FIFO trim — keep at most MAX_ITEMS-1 BEFORE inserting the new one.
  try {
    let items = await getAllDesc();
    while (items.length >= MAX_ITEMS) {
      const oldestId = items[items.length - 1].id;
      await deleteOne(oldestId);
      revokeLive(oldestId);
      items.pop();
    }
  } catch (_) {
    // proceed; the put attempt will surface a real error if any
  }

  // Try to insert; on quota error, evict oldest 1-by-1 and retry.
  // Stop when empty or success.
  let newId;
  while (true) {
    try {
      newId = await putRecord(record);
      break;
    } catch (err) {
      if (!isQuotaError(err)) {
        showToast('히스토리 저장 실패');
        // Store failed — clear the marker so the save can be retried this
        // session. Leave it if a newer result claimed it in the meantime.
        if (lastSaved && lastSaved.blob === blob) lastSaved = null;
        return;
      }
      const oldestId = await getOldestId();
      if (oldestId == null) {
        showToast('브라우저 저장 공간이 부족합니다. 결과를 다운로드 후 카드를 삭제해주세요.');
        if (lastSaved && lastSaved.blob === blob) lastSaved = null;
        return;
      }
      await deleteOne(oldestId);
      revokeLive(oldestId);
    }
  }

  // Stored — remember the new card's id so deleting it clears the dedup marker.
  if (lastSaved && lastSaved.blob === blob) lastSaved.id = newId;

  await renderHistory();
}

export async function initHistory() {
  // Only proceed if the chroma section exists (we're on the main page).
  if (!$('historyList')) return;
  if (!('indexedDB' in window)) {
    $('historySummary').textContent = '이 브라우저는 결과 저장을 지원하지 않습니다.';
    return;
  }
  try {
    await renderHistory();
  } catch (_) {
    $('historySummary').textContent = '저장소를 열 수 없습니다.';
  }
}
