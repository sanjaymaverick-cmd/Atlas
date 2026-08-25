import { DataTable, Pill, formatAmount, formatDate, type Column } from "./DataTable";
import { useResource } from "../hooks/useResource";
import type { Register } from "../workflows/registers";

// Renders one register from its descriptor.
//
// A component rather than a loop inside the screen because each register needs
// its own useResource call, and hooks cannot be called in a loop.

type Row = Record<string, unknown>;

function cell(row: Row, column: Register["columns"][number]) {
  const value = row[column.field];
  if (value === null || value === undefined || value === "") return "—";
  switch (column.kind) {
    case "date":
      return formatDate(String(value));
    case "amount":
      return formatAmount(value as number | string);
    case "pill":
      return <Pill>{String(value)}</Pill>;
    case "mono":
      // Ids and hashes are truncated: the full value is rarely what a reader
      // wants on a register, and it crowds out the columns that are.
      return String(value).length > 20 ? `${String(value).slice(0, 12)}…` : String(value);
    default:
      return String(value);
  }
}

export function RegisterTable({
  register,
  scope,
  blocked,
}: {
  register: Register;
  scope: { entity: string; project: string };
  blocked: string | null;
}) {
  const ready = register.scope === "entity" ? scope.entity !== "" : scope.project !== "";
  const resource = useResource<Row[]>(ready && blocked === null ? register.path(scope) : null);

  const columns: Column<Row>[] = register.columns.map((column) => ({
    header: column.header,
    cell: (row) => cell(row, column),
    ...(column.kind === "mono" ? { mono: true } : {}),
    ...(column.kind === "amount" ? { align: "right" as const } : {}),
  }));

  return (
    <div className="card stack">
      <div className="page-head">
        <div>
          <h3>{register.title}</h3>
          {register.note && <p className="muted">{register.note}</p>}
        </div>
        {!blocked && ready && (
          <button className="btn btn-small" onClick={() => void resource.reload()}>
            Refresh
          </button>
        )}
      </div>

      {blocked && <p className="muted">{blocked}</p>}
      {!blocked && !ready && (
        <p className="muted">
          {register.scope === "entity"
            ? "Enter a legal entity ID above."
            : "Select a project above."}
        </p>
      )}
      {resource.error && <p className="banner banner-error">{resource.error}</p>}
      {resource.loading && <p className="muted">Loading…</p>}
      {resource.data && (
        <DataTable
          rows={resource.data}
          columns={columns}
          rowKey={(row) => String(row["id"] ?? Math.random())}
          empty={register.empty}
        />
      )}
    </div>
  );
}
