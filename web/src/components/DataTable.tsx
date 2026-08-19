import type { ReactNode } from "react";

// One table for every list in the app. ERP screens are mostly tables, and
// twenty hand-rolled ones drift in spacing, empty states and date formatting
// within a week.

export interface Column<T> {
  header: string;
  /** Cell contents. Return a string for plain text, or a node for anything else. */
  cell: (row: T) => ReactNode;
  /** Renders in the monospace column style — ids, codes, hashes. */
  mono?: boolean;
  align?: "right";
}

interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Shown instead of the table when there are no rows. */
  empty: string;
  actions?: (row: T) => ReactNode;
}

export function DataTable<T>({ rows, columns, rowKey, empty, actions }: DataTableProps<T>) {
  if (rows.length === 0) return <p className="empty">{empty}</p>;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.header} className={column.align === "right" ? "align-right" : undefined}>
                {column.header}
              </th>
            ))}
            {actions && <th />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.header}
                  className={[column.mono ? "mono" : "", column.align === "right" ? "align-right" : ""]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {column.cell(row)}
                </td>
              ))}
              {actions && <td className="row-actions">{actions(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Shared cell helpers, so dates and money look the same everywhere. */

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed)
    ? new Date(parsed).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : value;
}

export function formatAmount(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(numeric)) return String(value);
  // Amounts are rupees throughout; grouping follows the viewer's locale.
  return numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Pill({ children }: { children: ReactNode }) {
  return <span className="pill">{children}</span>;
}
