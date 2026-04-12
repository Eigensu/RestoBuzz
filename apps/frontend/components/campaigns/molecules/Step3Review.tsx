import { cn } from "@/lib/utils";
import { absoluteIST } from "@/lib/date";
import type { Template, PreflightResult } from "@/types";

const INPUT_CLS =
  "w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30";

// IST-only behavior is intentional. All campaigns are scheduled in IST universally
// to match our backend and server setups. Thus, hardcoding the 5.5 hour offset is required.

/** Returns a datetime-local string clamped to now in IST (UTC+5:30) */
function toDatetimeLocalMin(): string {
  const now = new Date();
  const istOffset = 5.5 * 60 * 60 * 1000;
  const istNow = new Date(now.getTime() + istOffset);
  return istNow.toISOString().slice(0, 16);
}

/** Parse a datetime-local value (YYYY-MM-DDTHH:MM) treated as IST → UTC Date */
function parseISTDatetimeLocal(value: string): Date {
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hours, minutes] = timePart.split(":").map(Number);
  // Subtract IST offset (5h 30m) from the local time components
  return new Date(Date.UTC(year, month - 1, day, hours - 5, minutes - 30));
}

/** Convert a UTC Date to the datetime-local input value displayed in IST */
function toInputValue(d: Date | null): string {
  if (!d) return "";
  const istOffset = 5.5 * 60 * 60 * 1000;
  const istDate = new Date(d.getTime() + istOffset);
  return istDate.toISOString().slice(0, 16);
}

interface Step3ReviewProps {
  campaignName: string;
  setCampaignName: (s: string) => void;
  includeUnsub: boolean;
  setIncludeUnsub: (b: boolean) => void;
  selectedTemplate: Template | null;
  preflight: PreflightResult | null;
  sendMode: "immediate" | "scheduled";
  setSendMode: (m: "immediate" | "scheduled") => void;
  scheduledAt: Date | null;
  setScheduledAt: (d: Date | null) => void;
}

export function Step3Review({
  campaignName,
  setCampaignName,
  includeUnsub,
  setIncludeUnsub,
  selectedTemplate,
  preflight,
  sendMode,
  setSendMode,
  scheduledAt,
  setScheduledAt,
}: Readonly<Step3ReviewProps>) {
  const minDatetime = toDatetimeLocalMin();

  function handleDatetimeChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.value) {
      setScheduledAt(null);
      return;
    }
    setScheduledAt(parseISTDatetimeLocal(e.target.value));
  }

  const scheduledAtFormatted = scheduledAt
    ? absoluteIST(scheduledAt) + " (IST)"
    : "—";

  const sendsAtLabel =
    sendMode === "immediate" ? "Immediately" : scheduledAtFormatted;

  const scheduledInPast =
    sendMode === "scheduled" &&
    scheduledAt !== null &&
    scheduledAt <= new Date();

  return (
    <div className="space-y-5">
      <h2 className="font-medium">Schedule &amp; Review</h2>

      {/* Campaign Name */}
      <div className="max-w-md">
        <label
          htmlFor="campaign-name"
          className="text-sm font-medium mb-1 block"
        >
          Campaign Name
        </label>
        <input
          id="campaign-name"
          value={campaignName}
          onChange={(e) => setCampaignName(e.target.value)}
          className={cn(INPUT_CLS, "py-2")}
          placeholder="e.g. Summer Promo 2026"
        />
      </div>

      {/* Unsubscribe footer */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={includeUnsub}
          onChange={(e) => setIncludeUnsub(e.target.checked)}
          className="w-4 h-4 accent-[#24422e] cursor-pointer"
        />
        <span className="text-sm">Include unsubscribe footer</span>
      </label>

      {/* ── When to send ─────────────────────────────────────────────── */}
      <div className="space-y-3">
        <p className="text-sm font-medium">When to send</p>

        {/* Send Immediately option */}
        <label
          htmlFor="send-mode-immediate"
          className={cn(
            "flex items-start gap-3 rounded-xl border p-4 cursor-pointer transition",
            sendMode === "immediate"
              ? "border-[#24422e] bg-[#f7fbf8]"
              : "border-gray-200 hover:border-gray-300",
          )}
        >
          <input
            id="send-mode-immediate"
            type="radio"
            name="send-mode"
            value="immediate"
            checked={sendMode === "immediate"}
            onChange={() => {
              setSendMode("immediate");
              setScheduledAt(null);
            }}
            className="mt-0.5 accent-[#24422e]"
          />
          <div>
            <span className="text-sm font-medium leading-none">
              Send immediately
            </span>
            <p className="mt-1 text-xs text-gray-500">
              Campaign starts as soon as you click Launch.
            </p>
          </div>
        </label>

        {/* Schedule for later option */}
        <label
          htmlFor="send-mode-scheduled"
          className={cn(
            "flex items-start gap-3 rounded-xl border p-4 cursor-pointer transition",
            sendMode === "scheduled"
              ? "border-[#24422e] bg-[#f7fbf8]"
              : "border-gray-200 hover:border-gray-300",
          )}
        >
          <input
            id="send-mode-scheduled"
            type="radio"
            name="send-mode"
            value="scheduled"
            checked={sendMode === "scheduled"}
            onChange={() => setSendMode("scheduled")}
            className="mt-0.5 accent-[#24422e]"
          />
          <div className="flex-1 space-y-3">
            <div>
              <span className="text-sm font-medium leading-none">
                Schedule for later
              </span>
              <p className="mt-1 text-xs text-gray-500">
                Pick a future date &amp; time — we&apos;ll fire it
                automatically.
              </p>
            </div>

            {sendMode === "scheduled" && (
              <div className="space-y-1">
                <label
                  htmlFor="scheduled-datetime"
                  className="text-xs font-medium text-gray-600"
                >
                  Scheduled date &amp; time
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="scheduled-datetime"
                    type="datetime-local"
                    min={minDatetime}
                    value={toInputValue(scheduledAt)}
                    onChange={handleDatetimeChange}
                    onClick={(e) => e.stopPropagation()}
                    className={cn(
                      INPUT_CLS,
                      "flex-1 py-2",
                      scheduledInPast
                        ? "border-red-400"
                        : !scheduledAt
                          ? "border-amber-400"
                          : ""
                    )}
                  />
                  <span className="shrink-0 rounded-md bg-[#24422e]/10 px-2 py-1.5 text-xs font-semibold text-[#24422e]">
                    IST
                  </span>
                </div>

                {scheduledInPast && (
                  <p className="text-xs text-red-500">
                    Please pick a future date and time.
                  </p>
                )}
              </div>
            )}
          </div>
        </label>
      </div>

      {/* ── Summary ──────────────────────────────────────────────────── */}
      <div className="border rounded-xl overflow-hidden">
        <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b bg-gray-50">
          Summary
        </div>
        <div className="divide-y text-sm">
          {[
            ["Campaign Name", campaignName || "—"],
            ["Template", selectedTemplate?.name ?? "—"],
            [
              "Recipients",
              preflight ? `${preflight.valid_count} contacts` : "—",
            ],
            ["Unsubscribe Footer", includeUnsub ? "Yes" : "No"],
            ["Sends At", sendsAtLabel],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between px-4 py-2.5">
              <span className="text-gray-500">{label}</span>
              <span className="font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
