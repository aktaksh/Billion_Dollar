"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo } from "react";

import type { StrategyMatrixRow } from "@/types/marketRegimeDashboard";

type Props = {
  rows: StrategyMatrixRow[];
  highlightRegime?: string;
};

const col = createColumnHelper<StrategyMatrixRow>();

export default function StrategyMatrixTable({ rows, highlightRegime }: Props) {
  const columns = useMemo(
    () => [
      col.accessor("regime", { header: "Regime" }),
      col.accessor("bull_call", { header: "Bull Call" }),
      col.accessor("bear_put", { header: "Bear Put" }),
      col.accessor("bull_put", { header: "Bull Put" }),
      col.accessor("bear_call", { header: "Bear Call" }),
      col.accessor("iron_condor", { header: "Iron Condor" }),
      col.accessor("wait", { header: "Wait" }),
      col.accessor("notes", { header: "Notes" }),
    ],
    [],
  );

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="table-wrap">
      <table className="qqq-table mr-table-compact">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className={highlightRegime && row.original.regime === highlightRegime ? "mr-highlight-row" : undefined}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
