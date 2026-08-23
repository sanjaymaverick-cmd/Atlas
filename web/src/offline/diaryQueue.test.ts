import { afterEach, describe, expect, it, vi } from "vitest";

import {
  listQueuedDiaries,
  queueSiteDiary,
  resetOfflineDiaryStoreForTests,
  syncQueuedDiaries,
  type SiteDiaryDraft,
} from "./diaryQueue";

const draft = (): SiteDiaryDraft => ({
  entry_date: "2026-08-24",
  client_record_id: crypto.randomUUID(),
  device_recorded_at: "2026-08-24T10:00:00.000Z",
  weather: "SYNTHETIC PRIVATE WEATHER",
  labour_strength: { synthetic_trade: 4 },
  materials_received: [],
  materials_consumed: [],
  visitor_count: 2,
  site_instructions: "SYNTHETIC PRIVATE INSTRUCTION",
});

function rawStore(storeName: string): Promise<unknown[]> {
  return new Promise((resolve, reject) => {
    const opened = indexedDB.open("atlas-offline-v1");
    opened.onerror = () => reject(opened.error);
    opened.onsuccess = () => {
      const database = opened.result;
      const request = database.transaction(storeName, "readonly").objectStore(storeName).getAll();
      request.onsuccess = () => {
        database.close();
        resolve(request.result as unknown[]);
      };
      request.onerror = () => {
        database.close();
        reject(request.error);
      };
    };
  });
}

afterEach(async () => {
  await resetOfflineDiaryStoreForTests();
});

describe("offline diary queue", () => {
  it("stores only encrypted payload and a non-extractable key", async () => {
    const payload = draft();
    await queueSiteDiary("project-a", payload);

    const listed = await listQueuedDiaries("project-a");
    expect(listed[0]?.draft).toEqual(payload);
    const rawDiaries = await rawStore("site-diaries");
    expect(JSON.stringify(rawDiaries)).not.toContain("SYNTHETIC PRIVATE");
    expect(rawDiaries[0]).not.toHaveProperty("draft");
    const keys = (await rawStore("keys")) as CryptoKey[];
    expect(keys[0]?.extractable).toBe(false);
  });

  it("removes a draft only after successful foreground submission", async () => {
    const payload = draft();
    await queueSiteDiary("project-a", payload);
    const send = vi.fn(async () => undefined);

    const result = await syncQueuedDiaries("project-a", send, () => ({
      needsReview: false,
    }));

    expect(result).toEqual({ submitted: 1, retained: 0 });
    expect(send).toHaveBeenCalledWith(payload);
    expect(await listQueuedDiaries("project-a")).toEqual([]);
  });

  it("retains a conflicting draft for explicit review without silent retry", async () => {
    await queueSiteDiary("project-a", draft());
    const send = vi.fn(async () => {
      throw new Error("synthetic conflict");
    });

    const first = await syncQueuedDiaries("project-a", send, () => ({
      needsReview: true,
      code: "conflict",
    }));
    const second = await syncQueuedDiaries("project-a", send, () => ({
      needsReview: true,
      code: "conflict",
    }));
    const retained = await listQueuedDiaries("project-a");

    expect(first).toEqual({ submitted: 0, retained: 1 });
    expect(second).toEqual({ submitted: 0, retained: 0 });
    expect(send).toHaveBeenCalledTimes(1);
    expect(retained[0]).toMatchObject({
      attemptCount: 1,
      status: "needs_review",
      errorCode: "conflict",
    });
  });
});
