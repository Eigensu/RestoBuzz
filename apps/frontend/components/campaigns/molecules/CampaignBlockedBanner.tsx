"use client";
import { AlertTriangle, ExternalLink } from "lucide-react";
import type { CampaignPauseReason } from "@/types";

const WA_MANAGER_TEMPLATES_URL =
  "https://business.facebook.com/wa/manage/message-templates/";

/** Remediation steps, keyed by the Meta error that blocked the send. */
const NEXT_STEPS: Record<string, string[]> = {
  "132015": [
    "Edit the template to improve its content — an edit lifts the pause immediately.",
    "Adjust the template audience to improve targeting, then manually unpause it.",
    "Exclude recipients who returned 131049 in the last run; they were frequency-capped by Meta.",
  ],
  "132016": [
    "This template has been paused too many times and is now disabled permanently.",
    "Create a new template with revised content rather than editing this one.",
  ],
  "132001": [
    "Check the template still exists and is approved for this language in WhatsApp Manager.",
    "If it was recently edited, wait for Meta to re-approve it before resuming.",
  ],
  "131048": [
    "Your account hit Meta's spam rate limit — this clears on its own over time.",
    "Reduce send volume and improve targeting before resuming.",
  ],
};

function formatPausedAt(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function CampaignBlockedBanner({
  reason,
}: Readonly<{ reason: CampaignPauseReason }>) {
  const steps = NEXT_STEPS[reason.code] ?? [];
  const pausedAt = formatPausedAt(reason.paused_at);

  return (
    <div
      role="alert"
      className="rounded-lg border border-amber-300 bg-amber-50 p-4"
    >
      <div className="flex gap-3">
        <AlertTriangle
          className="h-5 w-5 shrink-0 text-amber-600"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h3 className="font-semibold text-amber-900">{reason.summary}</h3>
            <span className="font-mono text-xs text-amber-700">
              error {reason.code}
            </span>
          </div>

          <p className="mt-1 text-sm text-amber-900">
            This campaign was paused automatically and no further messages have
            been sent. Recipients who had not yet been messaged are still queued
            — resuming picks up exactly where it stopped.
          </p>

          {/* Meta's own wording, verbatim, so it matches WhatsApp Manager. */}
          <blockquote className="mt-3 border-l-2 border-amber-400 pl-3 text-sm italic text-amber-800">
            {reason.message}
          </blockquote>

          {steps.length > 0 && (
            <>
              <p className="mt-3 text-sm font-medium text-amber-900">
                What you can do:
              </p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-amber-900">
                {steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-amber-700">
            <a
              href={WA_MANAGER_TEMPLATES_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium underline hover:text-amber-900"
            >
              Open WhatsApp Manager
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
            {reason.template_name && (
              <span>
                Template: <span className="font-mono">{reason.template_name}</span>
              </span>
            )}
            {pausedAt && <span>Paused {pausedAt}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
