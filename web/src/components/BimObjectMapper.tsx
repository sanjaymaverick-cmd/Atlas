import { useState, type FormEvent } from "react";

import { ApiError, request } from "../api/client";

interface MappingRow {
  ifcGuid: string;
  objectType: string;
  workPackage: string;
  materialId: string;
  buildingId: string;
  floorId: string;
  unitId: string;
  roomReference: string;
}

const emptyRow = (): MappingRow => ({
  ifcGuid: "",
  objectType: "work_package",
  workPackage: "",
  materialId: "",
  buildingId: "",
  floorId: "",
  unitId: "",
  roomReference: "",
});

const TYPES = [
  "building",
  "floor",
  "unit",
  "room",
  "work_package",
  "material",
  "boq_line",
  "asset",
  "quantity",
];

export function BimObjectMapper({ projectId }: { projectId: string }) {
  const [importId, setImportId] = useState("");
  const [rows, setRows] = useState<MappingRow[]>([emptyRow()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function update(index: number, field: keyof MappingRow, value: string) {
    setRows(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const objects = rows.map((row) => ({
        ifc_guid: row.ifcGuid.trim(),
        object_type: row.objectType,
        ...(row.workPackage.trim() ? { work_package: row.workPackage.trim() } : {}),
        ...(row.materialId.trim() ? { material_id: row.materialId.trim() } : {}),
        ...(row.buildingId.trim() ? { building_id: row.buildingId.trim() } : {}),
        ...(row.floorId.trim() ? { floor_id: row.floorId.trim() } : {}),
        ...(row.unitId.trim() ? { unit_id: row.unitId.trim() } : {}),
        ...(row.roomReference.trim() ? { room_reference: row.roomReference.trim() } : {}),
      }));
      await request(`/api/v1/bim-imports/${encodeURIComponent(importId.trim())}/objects`, {
        method: "POST",
        body: { objects },
      });
      setRows([emptyRow()]);
      setNotice(
        `${objects.length} structured BIM ${objects.length === 1 ? "object" : "objects"} imported.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? `${caught.code}: ${caught.message}`
          : "The BIM mappings could not be imported.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-labelledby="bim-mapper-title">
      <div className="page-head">
        <div>
          <h3 id="bim-mapper-title">Structured BIM Object Mapper</h3>
          <p className="muted">
            Submit validated extraction results only. Raw IFC files, paths, URLs, and credentials
            are never accepted here.
          </p>
        </div>
        <button
          className="btn"
          type="button"
          onClick={() => setRows([...rows, emptyRow()])}
          disabled={busy}
        >
          Add object
        </button>
      </div>
      {!projectId && <p className="banner banner-info">Select the import project first.</p>}
      {error && <p className="banner banner-error">{error}</p>}
      {notice && <p className="banner banner-ok">{notice}</p>}
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>Validated BIM import ID</span>
          <input
            required
            spellCheck={false}
            value={importId}
            onChange={(event) => setImportId(event.target.value)}
          />
        </label>
        {rows.map((row, index) => (
          <fieldset className="bim-object-row" key={index}>
            <legend>Object {index + 1}</legend>
            <label className="field">
              <span>IFC GUID</span>
              <input
                required
                maxLength={100}
                spellCheck={false}
                value={row.ifcGuid}
                onChange={(event) => update(index, "ifcGuid", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Object type</span>
              <select
                value={row.objectType}
                onChange={(event) => update(index, "objectType", event.target.value)}
              >
                {TYPES.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Work package</span>
              <input
                maxLength={200}
                value={row.workPackage}
                onChange={(event) => update(index, "workPackage", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Material ID</span>
              <input
                spellCheck={false}
                value={row.materialId}
                onChange={(event) => update(index, "materialId", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Building ID</span>
              <input
                spellCheck={false}
                value={row.buildingId}
                onChange={(event) => update(index, "buildingId", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Floor ID</span>
              <input
                spellCheck={false}
                value={row.floorId}
                onChange={(event) => update(index, "floorId", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Unit ID</span>
              <input
                spellCheck={false}
                value={row.unitId}
                onChange={(event) => update(index, "unitId", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Room reference</span>
              <input
                maxLength={200}
                value={row.roomReference}
                onChange={(event) => update(index, "roomReference", event.target.value)}
              />
            </label>
            <button
              className="btn btn-danger"
              type="button"
              disabled={busy || rows.length === 1}
              onClick={() => setRows(rows.filter((_, rowIndex) => rowIndex !== index))}
            >
              Remove object
            </button>
          </fieldset>
        ))}
        <div>
          <button className="btn btn-primary" disabled={busy || !projectId}>
            {busy ? "Importing…" : "Import structured mappings"}
          </button>
        </div>
      </form>
    </section>
  );
}
