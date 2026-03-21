"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { getMe } from "@/lib/auth";
import { RESTAURANTS } from "@/types";
import { MessageSquare, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export default function SelectRestaurantPage() {
  const router = useRouter();
  const { user, setUser, setRestaurant } = useAuthStore();

  useEffect(() => {
    if (!user) {
      getMe().then((u) => {
        if (!u) router.push("/login");
        else setUser(u);
      });
    }
  }, [user, router, setUser]);

  const handleSelect = (r: (typeof RESTAURANTS)[number]) => {
    setRestaurant(r);
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 bg-green-500 rounded-lg flex items-center justify-center">
          <MessageSquare className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold">RestoBuzz</span>
        {user && (
          <span className="ml-auto text-sm text-gray-400">{user.email}</span>
        )}
      </header>

      {/* Content */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl">
          <h1 className="text-2xl font-bold text-center mb-1">
            Select a Restaurant
          </h1>
          <p className="text-gray-500 text-sm text-center mb-8">
            Choose which restaurant you want to manage
          </p>

          <div className="grid sm:grid-cols-2 gap-3">
            {RESTAURANTS.map((r) => (
              <button
                key={r.id}
                onClick={() => handleSelect(r)}
                className={cn(
                  "group flex items-center gap-4 bg-white border rounded-xl p-4",
                  "hover:border-green-400 hover:shadow-sm transition-all text-left",
                )}
              >
                <div
                  className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center text-2xl shrink-0",
                    r.color,
                    "bg-opacity-10",
                  )}
                >
                  {r.emoji}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm">{r.name}</p>
                  <p className="text-xs text-gray-400">{r.location}</p>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-green-500 transition shrink-0" />
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
