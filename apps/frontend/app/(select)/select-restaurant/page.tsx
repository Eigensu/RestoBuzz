"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { getMe } from "@/lib/auth";
import { RESTAURANTS } from "@/types";
import {
  Store,
  Utensils,
  ChefHat,
  Pizza,
  Coffee,
  Salad,
  Wine,
  ChevronRight,
} from "lucide-react";

const getIcon = (id: string) => {
  switch (id) {
    case "r1":
      return <Utensils className="w-6 h-6" />;
    case "r2":
      return <ChefHat className="w-6 h-6" />;
    case "r3":
      return <Pizza className="w-6 h-6" />;
    case "r4":
      return <Coffee className="w-6 h-6" />;
    case "r5":
      return <Salad className="w-6 h-6" />;
    case "r6":
      return <Wine className="w-6 h-6" />;
    default:
      return <Store className="w-6 h-6" />;
  }
};

export default function SelectRestaurantPage() {
  const router = useRouter();
  const { user, setUser, setRestaurant, _hydrated } = useAuthStore();

  useEffect(() => {
    if (!_hydrated) return;
    if (!user) {
      getMe().then((u) => {
        if (!u) router.push("/login");
        else setUser(u);
      });
    }
  }, [_hydrated, user, router, setUser]);

  const handleSelect = (r: (typeof RESTAURANTS)[number]) => {
    setRestaurant(r);
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-[#24422e] flex flex-col items-center justify-center p-6 md:p-12">
      <div className="bg-white w-full max-w-6xl rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header inside the modal */}
        <div className="px-8 py-6 border-b border-gray-100 flex items-center justify-between bg-white">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#24422e] flex items-center justify-center">
              <Utensils className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-semibold text-[#24422e]">
              RestoBuzz
            </span>
          </div>
          {user && (
            <span className="text-xs text-gray-400 font-medium">
              {user.email}
            </span>
          )}
        </div>

        {/* Content */}
        <div className="p-8 md:p-12 flex flex-col items-center flex-1 bg-white">
          <h1 className="text-2xl md:text-3xl font-light text-[#24422e] mb-2 text-center">
            Select Your Restaurant
          </h1>
          <p className="text-sm text-gray-500 mb-8 text-center max-w-sm">
            Choose which restaurant workspace you want to manage right now.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full">
            {RESTAURANTS.map((r) => (
              <button
                key={r.id}
                onClick={() => handleSelect(r)}
                className="group flex items-center gap-4 bg-[#eff2f0] rounded-xl p-4 hover:bg-[#24422e] transition-colors text-left border border-transparent hover:border-[#24422e]"
              >
                <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 bg-white text-[#24422e] group-hover:text-white group-hover:bg-white/10 transition-colors">
                  {getIcon(r.id)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-[#24422e] group-hover:text-white transition-colors">
                    {r.name}
                  </p>
                  <p className="text-xs text-gray-500 group-hover:text-gray-300 transition-colors">
                    {r.location}
                  </p>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors shrink-0" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
