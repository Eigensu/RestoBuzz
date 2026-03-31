import { MetaConfigCard } from "@/components/settings/organisms/MetaConfigCard";
import { MonitoringCard } from "@/components/settings/organisms/MonitoringCard";

export default function SettingsPage() {
  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Settings</h1>
      <MetaConfigCard />
      <MonitoringCard />
    </div>
  );
}
