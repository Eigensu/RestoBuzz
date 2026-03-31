import { ExternalLink } from "lucide-react";

const META_KEYS = [
  "META_PRIMARY_PHONE_ID",
  "META_PRIMARY_ACCESS_TOKEN",
  "META_FALLBACK_PHONE_ID",
  "META_WEBHOOK_VERIFY_TOKEN",
];

export function MetaConfigCard() {
  return (
    <div className="bg-white rounded-xl border p-5 space-y-4">
      <h2 className="font-medium text-sm">Meta / WhatsApp Configuration</h2>
      <p className="text-sm text-gray-500">
        WABA credentials are managed via environment variables. Update your{" "}
        <code className="bg-gray-100 px-1 rounded">.env</code> file and restart
        the backend service.
      </p>
      <div className="space-y-2 text-sm">
        {META_KEYS.map((key) => (
          <div
            key={key}
            className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2"
          >
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
  );
}
