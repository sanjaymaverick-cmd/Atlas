const DATABASE = "atlas-offline-v1";
const VERSION = 1;
const KEY_STORE = "keys";
const DIARY_STORE = "site-diaries";
const DIARY_KEY = "site-diary-aes-gcm";

export interface SiteDiaryDraft {
  entry_date: string;
  client_record_id: string;
  device_recorded_at: string;
  weather?: string;
  labour_strength: Record<string, number>;
  materials_received: MaterialMovementDraft[];
  materials_consumed: MaterialMovementDraft[];
  equipment_breakdowns?: string;
  visitor_count: number;
  site_instructions?: string;
  delays_and_reasons?: string;
}

export interface MaterialMovementDraft {
  material_id: string;
  quantity: number;
  unit: string;
}

type QueueStatus = "pending" | "needs_review";

interface EncryptedDiaryRecord {
  id: string;
  projectId: string;
  queuedAt: string;
  attemptCount: number;
  status: QueueStatus;
  errorCode?: string;
  iv: ArrayBuffer;
  ciphertext: ArrayBuffer;
}

export interface QueuedDiary {
  id: string;
  projectId: string;
  queuedAt: string;
  attemptCount: number;
  status: QueueStatus;
  errorCode?: string;
  draft: SiteDiaryDraft;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB aborted"));
    transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB failed"));
  });
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(KEY_STORE)) database.createObjectStore(KEY_STORE);
      if (!database.objectStoreNames.contains(DIARY_STORE)) {
        database.createObjectStore(DIARY_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline database could not open"));
  });
}

let keyPromise: Promise<CryptoKey> | null = null;

async function encryptionKey(): Promise<CryptoKey> {
  if (keyPromise) return keyPromise;
  keyPromise = (async () => {
    const database = await openDatabase();
    try {
      const read = database.transaction(KEY_STORE, "readonly");
      const existing = await requestResult<CryptoKey | undefined>(
        read.objectStore(KEY_STORE).get(DIARY_KEY),
      );
      await transactionDone(read);
      if (existing) return existing;

      const created = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, [
        "encrypt",
        "decrypt",
      ]);
      const write = database.transaction(KEY_STORE, "readwrite");
      write.objectStore(KEY_STORE).put(created, DIARY_KEY);
      await transactionDone(write);
      return created;
    } finally {
      database.close();
    }
  })();
  return keyPromise;
}

async function encrypt(draft: SiteDiaryDraft): Promise<Pick<EncryptedDiaryRecord, "iv" | "ciphertext">> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(draft));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    await encryptionKey(),
    plaintext,
  );
  return { iv: iv.buffer, ciphertext };
}

async function decrypt(record: EncryptedDiaryRecord): Promise<SiteDiaryDraft> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(record.iv) },
    await encryptionKey(),
    record.ciphertext,
  );
  return JSON.parse(new TextDecoder().decode(plaintext)) as SiteDiaryDraft;
}

export async function queueSiteDiary(
  projectId: string,
  draft: SiteDiaryDraft,
): Promise<string> {
  const id = crypto.randomUUID();
  const encrypted = await encrypt(draft);
  const record: EncryptedDiaryRecord = {
    id,
    projectId,
    queuedAt: new Date().toISOString(),
    attemptCount: 0,
    status: "pending",
    ...encrypted,
  };
  const database = await openDatabase();
  try {
    const transaction = database.transaction(DIARY_STORE, "readwrite");
    transaction.objectStore(DIARY_STORE).add(record);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
  return id;
}

export async function listQueuedDiaries(projectId: string): Promise<QueuedDiary[]> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(DIARY_STORE, "readonly");
    const records = await requestResult<EncryptedDiaryRecord[]>(
      transaction.objectStore(DIARY_STORE).getAll(),
    );
    await transactionDone(transaction);
    const selected = records
      .filter((record) => record.projectId === projectId)
      .sort((left, right) => left.queuedAt.localeCompare(right.queuedAt));
    return Promise.all(
      selected.map(async (record) => ({
        id: record.id,
        projectId: record.projectId,
        queuedAt: record.queuedAt,
        attemptCount: record.attemptCount,
        status: record.status,
        ...(record.errorCode ? { errorCode: record.errorCode } : {}),
        draft: await decrypt(record),
      })),
    );
  } finally {
    database.close();
  }
}

async function updateRecord(record: EncryptedDiaryRecord): Promise<void> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(DIARY_STORE, "readwrite");
    transaction.objectStore(DIARY_STORE).put(record);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

async function removeRecord(id: string): Promise<void> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(DIARY_STORE, "readwrite");
    transaction.objectStore(DIARY_STORE).delete(id);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

export interface SyncFailure {
  code?: string;
  needsReview: boolean;
}

export interface SyncResult {
  submitted: number;
  retained: number;
}

export async function syncQueuedDiaries(
  projectId: string,
  send: (draft: SiteDiaryDraft) => Promise<void>,
  classifyFailure: (error: unknown) => SyncFailure,
): Promise<SyncResult> {
  const database = await openDatabase();
  let records: EncryptedDiaryRecord[];
  try {
    const transaction = database.transaction(DIARY_STORE, "readonly");
    records = await requestResult<EncryptedDiaryRecord[]>(
      transaction.objectStore(DIARY_STORE).getAll(),
    );
    await transactionDone(transaction);
  } finally {
    database.close();
  }

  let submitted = 0;
  let retained = 0;
  for (const record of records) {
    if (record.projectId !== projectId || record.status !== "pending") continue;
    try {
      await send(await decrypt(record));
      await removeRecord(record.id);
      submitted += 1;
    } catch (error) {
      const failure = classifyFailure(error);
      record.attemptCount += 1;
      if (failure.needsReview) record.status = "needs_review";
      if (failure.code) record.errorCode = failure.code;
      await updateRecord(record);
      retained += 1;
    }
  }
  return { submitted, retained };
}

export async function resetOfflineDiaryStoreForTests(): Promise<void> {
  keyPromise = null;
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DATABASE);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error ?? new Error("Offline database reset failed"));
    request.onblocked = () => reject(new Error("Offline database reset was blocked"));
  });
}
