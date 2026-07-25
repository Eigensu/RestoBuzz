"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  /** Rendered on the left of the bar. Defaults to "Page X of Y". */
  label?: string;
}

/** A page button, or a gap standing in for the pages skipped before it. */
type PageItem = { key: string; page: number | null };

/** Collapse the page list to first, last, and a window around the current page,
 * inserting an ellipsis wherever the sequence skips ahead. Keys are derived from
 * the page numbers themselves so they stay stable as the window moves. */
function pageItems(page: number, totalPages: number): PageItem[] {
  return Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
    .reduce<PageItem[]>((acc, p, idx, arr) => {
      const prev = arr[idx - 1];
      if (idx > 0 && p - prev > 1) {
        acc.push({ key: `gap-${prev}-${p}`, page: null });
      }
      acc.push({ key: `page-${p}`, page: p });
      return acc;
    }, []);
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  label,
}: Readonly<PaginationProps>) {
  if (totalPages <= 1) return null;

  return (
    <div className="px-4 py-3 border-t flex items-center justify-between text-xs text-gray-500">
      <span>{label ?? `Page ${page} of ${totalPages}`}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {pageItems(page, totalPages).map(({ key, page: p }) => {
          if (p === null) {
            return (
              <span key={key} className="px-1">
                …
              </span>
            );
          }
          return (
            <button
              key={key}
              type="button"
              onClick={() => onPageChange(p)}
              aria-current={page === p ? "page" : undefined}
              className={`w-7 h-7 rounded text-xs font-medium transition ${page === p ? "bg-gray-900 text-white" : "hover:bg-gray-100"}`}
            >
              {p}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
