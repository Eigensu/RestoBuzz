"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import { getMe, logout } from "@/lib/auth";
import { RESTAURANTS } from "@/types";
import {
  LayoutDashboard,
  Send,
  Inbox,
  FileText,
  Users,
  Settings,
  LogOut,
  MessageSquare,
  Menu,
  ChevronDown,
  Check,
  UserCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campaigns", icon: Send },
  { href: "/members", label: "Members", icon: UserCheck },
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/templates", label: "Templates", icon: FileText },
  { href: "/contacts", label: "Suppression", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, setUser, restaurant, setRestaurant, _hydrated } =
    useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!_hydrated) return; // wait for localStorage rehydration
    if (!user) {
      getMe().then((u) => {
        if (!u) router.push("/login");
        else setUser(u);
      });
    }
  }, [_hydrated, user, router, setUser]);

  useEffect(() => {
    if (!_hydrated) return;
    if (user && !restaurant) router.push("/select-restaurant");
  }, [_hydrated, user, restaurant, router]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleLogout = async () => {
    await logout();
    setUser(null);
    router.push("/login");
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed lg:static inset-y-0 left-0 z-30 w-60 bg-white border-r flex flex-col transition-transform duration-200",
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 h-14 border-b">
          <div className="w-8 h-8 bg-green-500 rounded-lg flex items-center justify-center">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-sm">RestoBuzz</span>
        </div>

        {/* Restaurant dropdown switcher */}
        {restaurant && (
          <div ref={dropdownRef} className="relative mx-3 mt-3">
            <button
              onClick={() => setDropdownOpen((o) => !o)}
              className="w-full flex items-center gap-2.5 rounded-lg border bg-gray-50 px-3 py-2.5 hover:bg-gray-100 transition"
            >
              <span className="text-xl leading-none">{restaurant.emoji}</span>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-xs font-semibold truncate">
                  {restaurant.name}
                </p>
                <p className="text-xs text-gray-400 truncate">
                  {restaurant.location}
                </p>
              </div>
              <ChevronDown
                className={cn(
                  "w-3.5 h-3.5 text-gray-400 shrink-0 transition-transform duration-150",
                  dropdownOpen && "rotate-180",
                )}
              />
            </button>

            {dropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-50 py-1 overflow-hidden">
                {RESTAURANTS.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => {
                      setRestaurant(r);
                      setDropdownOpen(false);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 transition text-left"
                  >
                    <span className="text-base leading-none">{r.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{r.name}</p>
                      <p className="text-xs text-gray-400 truncate">
                        {r.location}
                      </p>
                    </div>
                    {restaurant.id === r.id && (
                      <Check className="w-3.5 h-3.5 text-green-500 shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <nav className="flex-1 p-3 space-y-0.5 mt-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition",
                pathname.startsWith(href) && href !== "/dashboard"
                  ? "bg-green-50 text-green-700 font-medium"
                  : pathname === href
                    ? "bg-green-50 text-green-700 font-medium"
                    : "text-gray-600 hover:bg-gray-100",
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          ))}
        </nav>

        <div className="p-3 border-t">
          <div className="flex items-center gap-2 px-3 py-2 mb-1">
            <div className="w-7 h-7 rounded-full bg-green-100 flex items-center justify-center text-xs font-medium text-green-700">
              {user?.email?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{user?.email}</p>
              <p className="text-xs text-gray-400 capitalize">
                {user?.role?.replace("_", " ")}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 w-full transition"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-white border-b flex items-center px-4 gap-3 lg:hidden">
          <button onClick={() => setSidebarOpen(true)}>
            <Menu className="w-5 h-5" />
          </button>
          <span className="font-semibold text-sm">
            {restaurant
              ? `${restaurant.emoji} ${restaurant.name}`
              : "RestoBuzz"}
          </span>
        </header>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
