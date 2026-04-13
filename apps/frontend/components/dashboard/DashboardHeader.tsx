import React from "react";
import { LayoutDashboard, Megaphone } from "lucide-react";
import Link from "next/link";
import { BRAND_GRADIENT } from "@/lib/brand";

export function DashboardHeader({
  restaurantName,
  activeChannel,
  setActiveChannel,
  campaignCount,
}: {
  restaurantName?: string;
  activeChannel: "whatsapp" | "email";
  setActiveChannel: (channel: "whatsapp" | "email") => void;
  campaignCount?: number;
}) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#eff2f0] rounded-lg">
            <LayoutDashboard className="w-6 h-6 text-[#24422e]" />
          </div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            Performance Intelligence
          </h1>
        </div>
        <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
          Real-time decision analytics for{" "}
          <span className="text-[#24422e] font-bold">{restaurantName || "your restaurant"}</span>
          {campaignCount !== undefined && (
            <span className="text-gray-400 ml-1.5">
              • {campaignCount.toLocaleString()} {activeChannel === "whatsapp" ? "Campaigns" : "Emails"}
            </span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex bg-[#eff2f0] p-1 rounded-2xl w-fit">
          <button
            onClick={() => setActiveChannel("whatsapp")}
            className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
              activeChannel === "whatsapp"
                ? "bg-white text-[#24422e] shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            WhatsApp
          </button>
          <button
            onClick={() => setActiveChannel("email")}
            className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
              activeChannel === "email"
                ? "bg-white text-[#24422e] shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Email
          </button>
        </div>

        <Link
          href={
            activeChannel === "whatsapp"
              ? "/campaigns/whatsapp/new"
              : "/campaigns/email/new"
          }
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          <Megaphone className="w-4 h-4" />
          {activeChannel === "whatsapp" ? "LAUNCH WHATSAPP" : "LAUNCH EMAIL"}
        </Link>
      </div>
    </div>
  );
}
