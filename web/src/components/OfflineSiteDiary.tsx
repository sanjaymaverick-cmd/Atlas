import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, request } from "../api/client";
import {
  listQueuedDiaries,
  queueSiteDiary,
  syncQueuedDiaries,
  type MaterialMovementDraft,
  type QueuedDiary,
  type SiteDiaryDraft,
} from "../offline/diaryQueue";

interface LabourRow {
  trade: string;
  count: string;
}

interface MaterialRow {
  materialId: string;
  quantity: string;
  unit: string;
}

const emptyLabour = (): LabourRow => ({ trade: "", count: "" });
const emptyMaterial = (): MaterialRow => ({ materialId: "", quantity: "", unit: "" });

function MaterialEditor({
  title,
  rows,
  setRows,
  disabled,
}: {
  title: string;
  rows: MaterialRow[];
  setRows: (rows: MaterialRow[]) => void;
  disabled: boolean;
}) {
  return (
    <div className="stack">
      <div className="page-head">
        <h4>{title}</h4>
        <button
          className="btn"
          type="button"
          onClick={() => setRows([...rows, emptyMaterial()])}
          disabled={disabled}
        >
          Add material
        </button>
      </div>
      {rows.map((row, index) => (
        <div className="material-editor-row" key={index}>
          <label className="field material-id-field">
            <span>Material ID</span>
            <input
              required
              spellCheck={false}
              value={row.materialId}
              onChange={(event) =>
                setRows(
                  rows.map((value, rowIndex) =>
                    rowIndex === index ? { ...value, materialId: event.target.value } : value,
                  ),
                )
              }
            />
          </label>
          <label className="field">
            <span>Quantity</span>
            <input
              required
              min="0.000001"
              step="any"
              type="number"
              value={row.quantity}
              onChange={(event) =>
                setRows(
                  rows.map((value, rowIndex) =>
                    rowIndex === index ? { ...value, quantity: event.target.value } : value,
                  ),
                )
              }
            />
          </label>
          <label className="field">
            <span>Unit</span>
            <input
              required
              maxLength={50}
              value={row.unit}
              onChange={(event) =>
                setRows(
                  rows.map((value, rowIndex) =>
                    rowIndex === index ? { ...value, unit: event.target.value } : value,
                  ),
                )
              }
            />
          </label>
          <button
            className="btn btn-danger"
            type="button"
            onClick={() => setRows(rows.filter((_, rowIndex) => rowIndex !== index))}
            disabled={disabled}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}

function message(caught: unknown): string {
  return caught instanceof ApiError
    ? `${caught.code}: ${caught.message}`
    : "The offline diary could not be accessed.";
}

export function OfflineSiteDiary({ projectId }: { projectId: string }) {
  const [entryDate, setEntryDate] = useState("");
  const [weather, setWeather] = useState("");
  const [labour, setLabour] = useState<LabourRow[]>([]);
  const [materialsReceived, setMaterialsReceived] = useState<MaterialRow[]>([]);
  const [materialsConsumed, setMaterialsConsumed] = useState<MaterialRow[]>([]);
  const [equipmentBreakdowns, setEquipmentBreakdowns] = useState("");
  const [visitorCount, setVisitorCount] = useState("0");
  const [siteInstructions, setSiteInstructions] = useState("");
  const [delays, setDelays] = useState("");
  const [queued, setQueued] = useState<QueuedDiary[]>([]);
  const [online, setOnline] = useState(navigator.onLine);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const syncing = useRef(false);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setQueued([]);
      return;
    }
    setQueued(await listQueuedDiaries(projectId));
  }, [projectId]);

  const sync = useCallback(async () => {
    if (!projectId || !navigator.onLine || syncing.current) return;
    syncing.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await syncQueuedDiaries(
        projectId,
        async (draft) => {
          await request(`/api/v1/projects/${encodeURIComponent(projectId)}/site-diary`, {
            method: "POST",
            body: draft,
          });
        },
        (caught) => ({
          needsReview: caught instanceof ApiError && caught.status >= 400 && caught.status < 500,
          ...(caught instanceof ApiError ? { code: caught.code } : {}),
        }),
      );
      if (result.submitted > 0) {
        setNotice(`${result.submitted} queued diary ${result.submitted === 1 ? "entry" : "entries"} synced.`);
      }
      await refresh();
    } catch (caught) {
      setError(message(caught));
    } finally {
      syncing.current = false;
      setBusy(false);
    }
  }, [projectId, refresh]);

  useEffect(() => {
    setError(null);
    setNotice(null);
    void refresh().catch((caught: unknown) => setError(message(caught)));
  }, [refresh]);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      void sync();
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    if (navigator.onLine) void sync();
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [sync]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const visitors = Number(visitorCount);
      if (!Number.isInteger(visitors) || visitors < 0) {
        setError("Visitor count must be a non-negative whole number.");
        return;
      }
      const labourStrength: Record<string, number> = {};
      for (const row of labour) {
        const trade = row.trade.trim();
        const count = Number(row.count);
        if (!trade || !Number.isInteger(count) || count < 0 || trade in labourStrength) {
          setError("Labour rows require a unique trade and non-negative whole-number count.");
          return;
        }
        labourStrength[trade] = count;
      }
      const materials = (rows: MaterialRow[]): MaterialMovementDraft[] | null => {
        const values = rows.map((row) => ({
          material_id: row.materialId.trim(),
          quantity: Number(row.quantity),
          unit: row.unit.trim(),
        }));
        return values.some(
          (value) => !value.material_id || !Number.isFinite(value.quantity) || value.quantity <= 0 || !value.unit,
        )
          ? null
          : values;
      };
      const received = materials(materialsReceived);
      const consumed = materials(materialsConsumed);
      if (received === null || consumed === null) {
        setError("Material rows require an ID, a positive quantity, and a unit.");
        return;
      }
      const draft: SiteDiaryDraft = {
        entry_date: entryDate,
        client_record_id: crypto.randomUUID(),
        device_recorded_at: new Date().toISOString(),
        ...(weather.trim() ? { weather: weather.trim() } : {}),
        labour_strength: labourStrength,
        materials_received: received,
        materials_consumed: consumed,
        ...(equipmentBreakdowns.trim()
          ? { equipment_breakdowns: equipmentBreakdowns.trim() }
          : {}),
        visitor_count: visitors,
        ...(siteInstructions.trim() ? { site_instructions: siteInstructions.trim() } : {}),
        ...(delays.trim() ? { delays_and_reasons: delays.trim() } : {}),
      };
      await queueSiteDiary(projectId, draft);
      setEntryDate("");
      setWeather("");
      setLabour([]);
      setMaterialsReceived([]);
      setMaterialsConsumed([]);
      setEquipmentBreakdowns("");
      setVisitorCount("0");
      setSiteInstructions("");
      setDelays("");
      setNotice(
        navigator.onLine
          ? "Diary encrypted locally and queued for submission."
          : "Offline: diary encrypted locally and retained until connectivity returns.",
      );
      await refresh();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
    if (navigator.onLine) await sync();
  }

  return (
    <section className="card stack" aria-labelledby="offline-diary-title">
      <div className="page-head">
        <div>
          <h3 id="offline-diary-title">Mobile Site Diary</h3>
          <p className="muted">
            Entries are encrypted in this browser before local storage. Sync runs only in the
            foreground while you are signed in; session tokens are never stored with drafts.
          </p>
        </div>
        <span className={online ? "pill pill-ok" : "pill pill-warn"}>
          {online ? "Online" : "Offline"}
        </span>
      </div>

      {!projectId && <p className="banner banner-info">Select a project to capture a diary.</p>}
      {error && <p className="banner banner-error">{error}</p>}
      {notice && <p className="banner banner-ok">{notice}</p>}

      <form className="stack" onSubmit={save}>
        <div className="grid-2">
          <label className="field">
            <span>Entry date</span>
            <input
              required
              type="date"
              value={entryDate}
              onChange={(event) => setEntryDate(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Weather</span>
            <input
              maxLength={500}
              value={weather}
              onChange={(event) => setWeather(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Visitor count</span>
            <input
              required
              min="0"
              step="1"
              type="number"
              value={visitorCount}
              onChange={(event) => setVisitorCount(event.target.value)}
            />
            <span className="field-help">Count only; do not enter visitor identities.</span>
          </label>
          <label className="field">
            <span>Equipment breakdowns</span>
            <textarea
              maxLength={4000}
              value={equipmentBreakdowns}
              onChange={(event) => setEquipmentBreakdowns(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Site instructions</span>
            <textarea
              maxLength={4000}
              value={siteInstructions}
              onChange={(event) => setSiteInstructions(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Delays and reasons</span>
            <textarea
              maxLength={4000}
              value={delays}
              onChange={(event) => setDelays(event.target.value)}
            />
          </label>
        </div>
        <div className="stack">
          <div className="page-head">
            <h4>Labour strength</h4>
            <button
              className="btn"
              type="button"
              onClick={() => setLabour([...labour, emptyLabour()])}
              disabled={busy}
            >
              Add trade
            </button>
          </div>
          {labour.map((row, index) => (
            <div className="labour-editor-row" key={index}>
              <label className="field">
                <span>Trade</span>
                <input
                  required
                  maxLength={100}
                  value={row.trade}
                  onChange={(event) =>
                    setLabour(
                      labour.map((value, rowIndex) =>
                        rowIndex === index ? { ...value, trade: event.target.value } : value,
                      ),
                    )
                  }
                />
              </label>
              <label className="field">
                <span>Count</span>
                <input
                  required
                  min="0"
                  step="1"
                  type="number"
                  value={row.count}
                  onChange={(event) =>
                    setLabour(
                      labour.map((value, rowIndex) =>
                        rowIndex === index ? { ...value, count: event.target.value } : value,
                      ),
                    )
                  }
                />
              </label>
              <button
                className="btn btn-danger"
                type="button"
                onClick={() => setLabour(labour.filter((_, rowIndex) => rowIndex !== index))}
                disabled={busy}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <MaterialEditor
          title="Materials received"
          rows={materialsReceived}
          setRows={setMaterialsReceived}
          disabled={busy}
        />
        <MaterialEditor
          title="Materials consumed"
          rows={materialsConsumed}
          setRows={setMaterialsConsumed}
          disabled={busy}
        />
        <div>
          <button className="btn btn-primary" disabled={busy || !projectId}>
            {busy ? "Securing…" : "Save securely and queue"}
          </button>
        </div>
      </form>

      {queued.length > 0 && (
        <div className="stack">
          <div className="page-head">
            <h4>Encrypted queue</h4>
            <button
              className="btn"
              type="button"
              onClick={() => void sync()}
              disabled={busy || !online}
            >
              Sync now
            </button>
          </div>
          {queued.map((entry) => (
            <div className="offline-queue-row" key={entry.id}>
              <div>
                <strong>{entry.draft.entry_date}</strong>
                <span className="muted">
                  queued {new Date(entry.queuedAt).toLocaleString()} · attempts {entry.attemptCount}
                </span>
              </div>
              <span className={entry.status === "pending" ? "pill" : "pill pill-warn"}>
                {entry.status === "pending" ? "Pending" : `Needs review: ${entry.errorCode ?? "conflict"}`}
              </span>
            </div>
          ))}
          <p className="muted">
            Entries needing review are retained and are never silently overwritten or discarded.
          </p>
        </div>
      )}
    </section>
  );
}
