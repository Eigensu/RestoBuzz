"use client";
import { toast } from "sonner";
import { ExternalLink } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Settings</h1>

      <div className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="font-medium text-sm">Meta / WhatsApp Configuration</h2>
        <p className="text-sm text-gray-500">
          WABA credentials are managed via environment variables. Update your <code className="bg-gray-100 px-1 rounded">.env</code> file and restart the backend service.
        </p>
        <div className="space-y-2 text-sm">
          {[
            "META_PRIMARY_PHONE_ID",
            "META_PRIMARY_ACCESS_TOKEN",
            "META_FALLBACK_PHONE_ID",
            "META_WEBHOOK_VERIFY_TOKEN",
          ].map((key) => (
            <div key={key} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
              <code className="text-xs text-gray-600">{key}</code>
              <span className="text-xs text-gray-400">••••••••</span>
            </div>
          ))}
        </div>
        <a
          href="https://developers.facebook.com/docs/whatsapp/cloud-api"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-sm text-green-600 hover:underline"
        >
          Meta Cloud API Docs <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      <div className="bg-white rounded-xl border p-5 space-y-3">
        <h2 className="font-medium text-sm">Monitoring</h2>
        <div className="flex gap-3">
          <a
            href="http://localhost:5555"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 border text-sm px-3 py-2 rounded-lg hover:bg-gray-50 transition"
          >
            Flower (Celery) <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
}
