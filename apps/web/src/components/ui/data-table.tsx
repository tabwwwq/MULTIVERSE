import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/*
 * Responsive table following the responsive-table guidance: a keyboard-scrollable
 * named region, sticky column and row headers, and a stacked card layout below a
 * container width of 600px with column labels injected from data-label.
 */

export interface Column<Row> {
  key: keyof Row & string;
  /** Unique column id when several columns render from the same key. Defaults to `key`. */
  id?: string;
  header: string;
  /** Right-aligned with tabular figures. */
  numeric?: boolean;
  /** Renders the cell as the row header (<th scope="row">). Use for exactly one column. */
  rowHeader?: boolean;
  /** Lets long text wrap inside a minimum width instead of widening the table. */
  wrap?: boolean;
  render?: (row: Row) => ReactNode;
}

interface DataTableProps<Row> {
  id: string;
  caption: ReactNode;
  columns: ReadonlyArray<Column<Row>>;
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  className?: string;
}

export function DataTable<Row>({
  id,
  caption,
  columns,
  rows,
  rowKey,
  className,
}: DataTableProps<Row>) {
  const captionId = `${id}-caption`;
  return (
    <div
      role="region"
      aria-labelledby={captionId}
      tabIndex={0}
      className={cn("data-table rounded-panel border border-line bg-surface", className)}
    >
      <table>
        <caption id={captionId}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.id ?? column.key}
                scope="col"
                className={cn(column.numeric && "is-numeric", column.wrap && "is-wrap")}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => {
                const content = column.render ? column.render(row) : String(row[column.key] ?? "");
                const classes = cn(column.numeric && "is-numeric", column.wrap && "is-wrap");
                return column.rowHeader ? (
                  <th key={column.id ?? column.key} scope="row" className={classes}>
                    {content}
                  </th>
                ) : (
                  <td key={column.id ?? column.key} data-label={column.header} className={classes}>
                    {content}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
