import React, { useState, useMemo, useEffect, useRef } from "react";
import { LayoutDashboard, Megaphone, Filter, Check, Search, ChevronDown } from "lucide-react";
import Link from "next/link";
import { BRAND_GRADIENT } from "@/lib/brand";
import type { Campaign } from "@/types";

export function DashboardHeader({
  restaurantName,
  activeChannel,
  setActiveChannel,
  campaignCount,
  allWaCampaigns = [],
  allEmailCampaigns = [],
  selectedCampaignIds = [],
  setSelectedCampaignIds = () => {},
}: {
  restaurantName?: string;
  activeChannel: "whatsapp" | "email";
  setActiveChannel: (channel: "whatsapp" | "email") => void;
  campaignCount?: number;
  allWaCampaigns?: Campaign[];
  allEmailCampaigns?: any[];
  selectedCampaignIds?: string[];
  setSelectedCampaignIds?: (ids: string[]) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentChannelCampaigns = useMemo(() => {
    // Only show root campaigns in the filter dropdown
    const waRoots = allWaCampaigns.filter(c => !c.parent_campaign_id);
    const combined = [...waRoots, ...allEmailCampaigns].sort((a, b) => new Date(b.created_at || b.scheduled_at || 0).getTime() - new Date(a.created_at || a.scheduled_at || 0).getTime());
    return combined;
  }, [allWaCampaigns, allEmailCampaigns]);

  const filteredCampaigns = useMemo(() => {
    if (!search.trim()) return currentChannelCampaigns;
    return currentChannelCampaigns.filter(c => (c.name || c.template_name || (c as any).subject || "Unnamed").toLowerCase().includes(search.toLowerCase()));
  }, [currentChannelCampaigns, search]);

  const toggleCampaign = (id: string) => {
    if (selectedCampaignIds.includes(id)) {
      setSelectedCampaignIds(selectedCampaignIds.filter(cid => cid !== id));
    } else {
      setSelectedCampaignIds([...selectedCampaignIds, id]);
    }
  };

  const toggleAll = () => {
    if (selectedCampaignIds.length === currentChannelCampaigns.length && currentChannelCampaigns.length > 0) {
      setSelectedCampaignIds([]);
    } else {
      setSelectedCampaignIds(currentChannelCampaigns.map(c => c.id));
    }
  };

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
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold bg-[#eff2f0] text-gray-700 hover:bg-gray-200 transition-colors"
          >
            <Filter className="w-4 h-4" />
            {selectedCampaignIds.length === 0 
              ? "All Campaigns" 
              : `${selectedCampaignIds.length} Selected`}
            <ChevronDown className="w-4 h-4 text-gray-400" />
          </button>
          
          {isOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-xl border border-gray-100 z-50 overflow-hidden flex flex-col max-h-[400px]">
              <div className="p-3 border-b border-gray-100">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search campaigns..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 bg-gray-50 rounded-xl text-sm outline-none focus:ring-2 focus:ring-[#24422e]/20"
                  />
                </div>
              </div>
              
              <div className="p-2 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
                <button
                  onClick={toggleAll}
                  className="text-xs font-bold text-[#24422e] hover:text-[#1a2f21] px-2 py-1 rounded-lg hover:bg-[#24422e]/10 transition-colors"
                >
                  {selectedCampaignIds.length === currentChannelCampaigns.length && currentChannelCampaigns.length > 0
                    ? "Deselect All"
                    : "Select All"}
                </button>
                {selectedCampaignIds.length > 0 && (
                  <button
                    onClick={() => setSelectedCampaignIds([])}
                    className="text-xs font-bold text-gray-500 hover:text-red-600 px-2 py-1 rounded-lg hover:bg-red-50 transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
              
              <div className="overflow-y-auto flex-1 p-2 space-y-1">
                {filteredCampaigns.length === 0 ? (
                  <div className="text-center py-6 text-sm text-gray-500">
                    No campaigns found
                  </div>
                ) : (
                  filteredCampaigns.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => toggleCampaign(c.id)}
                      className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-50 rounded-xl transition-colors text-left group"
                    >
                      <div className="flex flex-col overflow-hidden pr-2">
                        <span className="text-sm font-semibold text-gray-700 truncate group-hover:text-gray-900">
                          {c.name || c.template_name || (c as any).subject || "Unnamed Campaign"}
                        </span>
                        <span className="text-xs text-gray-400 truncate">
                          {c.template_id ? "WhatsApp" : "Email"}
                        </span>
                      </div>
                      <div className={`w-5 h-5 rounded flex-shrink-0 border flex items-center justify-center transition-colors ${selectedCampaignIds.includes(c.id) ? 'bg-[#24422e] border-[#24422e]' : 'border-gray-300'}`}>
                        {selectedCampaignIds.includes(c.id) && <Check className="w-3 h-3 text-white" />}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

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
