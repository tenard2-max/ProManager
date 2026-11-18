/** File System Access API + IndexedDB 핸들 저장 */

const DB_NAME = "monitor_fs_ui";
const STORE = "handles";
const KEY = "dataDir";

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveDirHandle(handle) {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(handle, KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function loadDirHandle() {
  const db = await openDb();
  const handle = await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(KEY);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return handle;
}

export async function clearDirHandle() {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export function supportsFsAccess() {
  return typeof window.showDirectoryPicker === "function";
}

export async function pickDataDirectory() {
  const handle = await window.showDirectoryPicker({
    id: "monitor-data",
    mode: "read",
    startIn: "documents",
  });
  await saveDirHandle(handle);
  return handle;
}

export async function ensurePermission(handle) {
  if (!handle) return false;
  const opts = { mode: "read" };
  if ((await handle.queryPermission(opts)) === "granted") return true;
  if ((await handle.requestPermission(opts)) === "granted") return true;
  return false;
}

export async function readTextFile(dirHandle, name) {
  try {
    const fh = await dirHandle.getFileHandle(name);
    const file = await fh.getFile();
    return await file.text();
  } catch {
    return null;
  }
}
