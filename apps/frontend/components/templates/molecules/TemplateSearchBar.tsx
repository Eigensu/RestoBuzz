import { Search } from "lucide-react";

const GREEN_DARKEST = "#24422e";
const GREEN_DARK = "#3a6b47";

type FilterStatus = "ALL" | "APPROVED" | "PENDING";

interface TemplateSearchBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  filterStatus: FilterStatus;
  onFilterChange: (status: FilterStatus) => void;
}

export function TemplateSearchBar({
  search,
  onSearchChange,
  filterStatus,
  onFilterChange,
}: TemplateSearchBarProps) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm flex flex-col sm:flex-row gap-3">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search templates..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
        />
      </div>
      <div className="flex gap-2">
        {(["ALL", "APPROVED", "PENDING"] as const).map((s) => (
          <button
            key={s}
            onClick={() => onFilterChange(s)}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
              filterStatus === s
                ? "text-white shadow-sm"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200"
            }`}
            style={
              filterStatus === s
                ? {
                    background: `linear-gradient(135deg, ${GREEN_DARKEST}, ${GREEN_DARK})`,
                  }
                : {}
            }
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
