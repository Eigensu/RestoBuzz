import { ExternalLink } from "lucide-react";

export function MonitoringCard() {
  return (
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
  );
}
