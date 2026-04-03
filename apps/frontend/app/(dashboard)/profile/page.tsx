"use client";

import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { getRestaurants } from "@/lib/restaurants";
import { api } from "@/lib/api";
import { BRAND_GRADIENT } from "@/lib/brand";
import { 
  User, 
  Mail, 
  Phone, 
  Calendar, 
  Shield, 
  Store, 
  Activity,
  Clock,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { User as UserType } from "@/lib/auth";

interface UserAccessDetail {
  restaurant_name: string;
  role: string;
}

interface UserAccessReport {
  user: UserType;
  accesses: UserAccessDetail[];
}

export default function ProfilePage() {
  const { user } = useAuthStore();
  
  const { data: restaurants = [], isLoading: loadingRestaurants } = useQuery({
    queryKey: ["restaurants", user?.id],
    queryFn: getRestaurants,
    enabled: !!user,
  });

  const { data: accessReport = [], isLoading: reportLoading } = useQuery<UserAccessReport[]>({
    queryKey: ["admin", "access-report"],
    queryFn: () => api.get("/admin/access-report").then(r => r.data),
    enabled: user?.role === "super_admin",
  });

  if (!user) return null;

  const initials = user.email?.[0]?.toUpperCase() || "U";
  const fullName = user.first_name && user.last_name 
    ? `${user.first_name} ${user.last_name}` 
    : user.email.split("@")[0];

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Profile Header */}
      <div className="relative overflow-hidden bg-white rounded-3xl border border-gray-100 shadow-sm p-8 md:p-10">
        <div className="absolute top-0 right-0 w-64 h-64 bg-[#24422e]/5 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl" />
        
        <div className="flex flex-col md:flex-row items-center gap-8 relative z-10">
          <div 
            className="w-24 h-24 md:w-32 md:h-32 rounded-full flex items-center justify-center text-3xl md:text-4xl font-black text-white shadow-2xl shadow-green-900/20"
            style={{ background: BRAND_GRADIENT }}
          >
            {initials}
          </div>
          
          <div className="text-center md:text-left space-y-3">
            <div className="flex flex-col md:flex-row items-center gap-3">
              <h1 className="text-3xl md:text-4xl font-black text-gray-900 tracking-tight">
                {fullName}
              </h1>
              <span className="px-4 py-1 bg-[#24422e] text-white text-[10px] font-black uppercase tracking-widest rounded-full shadow-sm">
                {user.role.replace("_", " ")}
              </span>
            </div>
            <p className="text-gray-500 font-medium flex items-center justify-center md:justify-start gap-2">
              <Mail className="w-4 h-4" />
              {user.email}
            </p>
            <div className="flex items-center justify-center md:justify-start gap-4">
              <div className="flex items-center gap-1.5 text-xs font-bold text-green-600 bg-green-50 px-2.5 py-1 rounded-lg">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Active Account
              </div>
              <div className="text-xs text-gray-400 font-medium">
                Member since {user.created_at ? new Date(user.created_at).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : "March 2024"}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-8 items-start">
        {/* Sidebar: Account Details & Compact Activity */}
        <div className="w-full lg:w-[320px] space-y-6 lg:sticky lg:top-8 shrink-0">
          <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden h-fit">
            <div className="px-6 py-5 border-b border-gray-50 bg-gray-50/50">
              <h2 className="text-sm font-black text-gray-900 uppercase tracking-widest flex items-center gap-2">
                <User className="w-4 h-4 text-[#24422e]" />
                Account Info
              </h2>
            </div>
            <div className="p-6 space-y-6">
              <DetailItem 
                icon={Mail} 
                label="Email Address" 
                value={user.email} 
              />
              <DetailItem 
                icon={Phone} 
                label="Phone Number" 
                value={user.phone || "Not provided"} 
              />
              <DetailItem 
                icon={Shield} 
                label="System Role" 
                value={user.role.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')} 
              />
              <DetailItem 
                icon={Calendar} 
                label="Joined Date" 
                value={user.created_at ? new Date(user.created_at).toLocaleDateString() : "3/28/2026"} 
              />
            </div>
            
            {/* Compact Activity at the bottom of the Card */}
            <div className="border-t border-gray-50">
              <div className="px-6 py-4 bg-gray-50/30">
                <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                  <Activity className="w-3 h-3 text-[#24422e]" />
                  Recent Activity
                </h2>
              </div>
              <div className="divide-y divide-gray-50">
                <CompactActivityRow 
                  icon={CheckCircle2} 
                  title="Authenticated" 
                  time="2m ago" 
                />
                <CompactActivityRow 
                  icon={Clock} 
                  title="Session Refresh" 
                  time="1h ago" 
                />
                <CompactActivityRow 
                  icon={Calendar} 
                  title="Account Setup" 
                  time="Joined" 
                />
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 space-y-8 min-w-0">
          <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-50 flex items-center justify-between">
              <h2 className="text-sm font-black text-gray-900 uppercase tracking-widest flex items-center gap-2">
                <Store className="w-4 h-4 text-[#24422e]" />
                Managed Restaurants
              </h2>
              <span className="px-2.5 py-1 bg-gray-100 text-gray-500 text-[10px] font-black rounded-full whitespace-nowrap">
                {restaurants.length} TOTAL
              </span>
            </div>
            <div className="p-6">
              {loadingRestaurants ? (
                <div className="space-y-4">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-16 bg-gray-50 rounded-2xl animate-pulse" />
                  ))}
                </div>
              ) : restaurants.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {restaurants.map((r: any) => (
                    <div 
                      key={r.id}
                      className="flex items-center gap-4 p-4 rounded-2xl border border-gray-100 hover:border-[#24422e]/20 hover:bg-[#24422e]/5 transition group"
                    >
                      <div className="text-2xl shrink-0">{r.emoji}</div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-bold text-gray-900 truncate group-hover:text-[#24422e] transition">
                          {r.name}
                        </p>
                        <p className="text-[10px] text-gray-400 font-medium truncate uppercase tracking-tighter">
                          {r.location}
                        </p>
                      </div>
                      <div className="px-2 py-1 bg-white border border-gray-100 rounded text-[10px] font-black text-gray-400 group-hover:text-[#24422e] group-hover:border-[#24422e]/10 transition whitespace-nowrap">
                        ADMIN
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-12 text-center bg-gray-50/50 rounded-2xl border border-dashed border-gray-200">
                  <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm">
                    <AlertCircle className="w-6 h-6 text-gray-300" />
                  </div>
                  <p className="text-sm text-gray-400 font-bold uppercase tracking-tight">No restaurant assignments found.</p>
                  <p className="text-[10px] text-gray-400/60 mt-1 uppercase font-black tracking-widest">Assignments are managed by the System Administration.</p>
                </div>
              )}
            </div>
          </div>

          {user.role === "super_admin" && (
            <div className="bg-white rounded-3xl border border-gray-100 shadow-sm overflow-hidden">
              <div className="px-6 py-5 border-b border-gray-50 flex items-center justify-between">
                <h2 className="text-sm font-black text-gray-900 uppercase tracking-widest flex items-center gap-2">
                  <Shield className="w-4 h-4 text-[#24422e]" />
                  User Access Report
                </h2>
                <span className="px-2.5 py-1 bg-[#24422e] text-white text-[10px] font-black rounded-full uppercase tracking-tighter whitespace-nowrap">
                  Superadmin Only
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50/50">
                      <th className="px-6 py-4 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-50 whitespace-nowrap">User</th>
                      <th className="px-6 py-4 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-50 whitespace-nowrap">Global Role</th>
                      <th className="px-6 py-4 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-50 whitespace-nowrap">Restaurant Accesses</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {reportLoading ? (
                      [1, 2, 3].map(i => (
                        <tr key={i} className="animate-pulse">
                          <td colSpan={3} className="px-6 py-4 h-12 bg-gray-50/30" />
                        </tr>
                      ))
                    ) : accessReport.map((item) => (
                      <tr key={item.user.id} className="hover:bg-gray-50/50 transition">
                        <td className="px-6 py-4">
                          <div className="flex flex-col">
                            <span className="text-sm font-bold text-gray-900 truncate max-w-[150px]">
                              {item.user.first_name ? `${item.user.first_name} ${item.user.last_name}` : item.user.email.split('@')[0]}
                            </span>
                            <span className="text-[10px] text-gray-400 font-medium">{item.user.email}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={cn(
                            "px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-tighter",
                            item.user.role === "super_admin" ? "bg-purple-50 text-purple-600" : "bg-blue-50 text-blue-600"
                          )}>
                            {item.user.role.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap gap-1.5">
                            {item.accesses.length > 0 ? (
                              item.accesses.map((acc, idx) => (
                                <span 
                                  key={idx}
                                  className="px-2 py-0.5 bg-gray-100 text-gray-600 text-[9px] font-bold rounded flex items-center gap-1"
                                >
                                  {acc.restaurant_name}
                                  <span className="opacity-40 font-black text-[8px] uppercase">{acc.role}</span>
                                </span>
                              ))
                            ) : (
                              <span className="text-[10px] text-gray-300 italic">No restaurants assigned</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailItem({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
        <Icon className="w-3 h-3" />
        {label}
      </p>
      <p className="text-sm font-bold text-gray-900 truncate">
        {value}
      </p>
    </div>
  );
}

function CompactActivityRow({ icon: Icon, title, time }: { icon: any; title: string; time: string }) {
  return (
    <div className="px-6 py-3 flex items-center justify-between gap-4 hover:bg-gray-50/50 transition duration-300">
      <div className="flex items-center gap-3 min-w-0">
        <div className="p-1.5 bg-gray-100 rounded-lg">
          <Icon className="w-3 h-3 text-gray-500" />
        </div>
        <p className="text-[11px] font-bold text-gray-700 truncate tracking-tight">{title}</p>
      </div>
      <span className="text-[9px] font-black text-gray-300 uppercase tracking-tighter whitespace-nowrap">{time}</span>
    </div>
  );
}
