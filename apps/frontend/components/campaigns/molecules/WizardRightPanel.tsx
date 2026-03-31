import type { PreflightResult } from "@/types";

interface WizardRightPanelProps {
  step: number;
  preflight: PreflightResult | null;
}

export function WizardRightPanel({ step, preflight }: WizardRightPanelProps) {
  return (
    <div className="hidden lg:flex w-80 shrink-0 flex-col gap-4">
      {step === 1 && (
        <div className="bg-white rounded-xl border p-5 space-y-3">
          <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">
            Tips
          </p>
          <div className="space-y-3 text-sm text-gray-600">
            {[
              {
                icon: "📋",
                title: "CSV / XLSX",
                body: (
                  <>
                    first row must be headers with at least a{" "}
                    <code className="bg-gray-100 px-1 rounded text-xs">
                      phone
                    </code>{" "}
                    column.
                  </>
                ),
              },
              {
                icon: "📱",
                title: "Phone format",
                body: "numbers are auto-normalised to E.164. Include country code or prefix with 0.",
              },
              {
                icon: "👥",
                title: "From Members",
                body: "use your existing NFC or E-Card member list directly, no file needed.",
              },
              {
                icon: "🚫",
                title: "Suppressed numbers",
                body: "are automatically excluded from the send list.",
              },
            ].map(({ icon, title, body }) => (
              <div key={title} className="flex gap-3">
                <span className="text-lg">{icon}</span>
                <p>
                  <span className="font-semibold text-gray-800">{title}</span> —{" "}
                  {body}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {step === 2 && preflight && (
        <div className="bg-white rounded-xl border p-5 space-y-4">
          <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">
            Preflight Summary
          </p>
          <div className="space-y-2">
            {[
              {
                label: "Will be sent to",
                value: preflight.valid_count,
                color: "text-[#24422e]",
              },
              {
                label: "Skipped (invalid)",
                value: preflight.invalid_count,
                color: "text-red-500",
              },
              {
                label: "Skipped (duplicate)",
                value: preflight.duplicate_count,
                color: "text-amber-600",
              },
              {
                label: "Skipped (suppressed)",
                value: preflight.suppressed_count,
                color: "text-gray-400",
              },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-gray-500">{label}</span>
                <span className={`font-bold ${color}`}>
                  {value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
          {preflight.valid_count > 0 && (
            <div className="bg-[#eff2f0] rounded-lg px-3 py-2 text-xs text-[#24422e] font-medium">
              ✓ Ready to proceed with {preflight.valid_count.toLocaleString()}{" "}
              recipients
            </div>
          )}
        </div>
      )}

      {step === 3 && (
        <div className="bg-white rounded-xl border p-5 space-y-3">
          <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">
            Before you launch
          </p>
          <div className="space-y-3 text-sm text-gray-600">
            {[
              {
                icon: "✅",
                body: (
                  <>
                    Campaign will be created as a{" "}
                    <span className="font-semibold text-gray-800">draft</span> —
                    you can review before starting.
                  </>
                ),
              },
              {
                icon: "⚡",
                body: (
                  <>
                    Messages are sent at up to{" "}
                    <span className="font-semibold text-gray-800">
                      80 msg/sec
                    </span>{" "}
                    via your configured WABA endpoints.
                  </>
                ),
              },
              {
                icon: "📊",
                body: "Live delivery and read stats will appear on the campaign detail page once started.",
              },
            ].map(({ icon, body }, i) => (
              <div key={i} className="flex gap-3">
                <span className="text-lg">{icon}</span>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
