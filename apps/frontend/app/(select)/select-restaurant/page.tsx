"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { getMe } from "@/lib/auth";
import { getRestaurants } from "@/lib/restaurants";
import type { Restaurant } from "@/types";
import {
  Store,
  Utensils,
  ChefHat,
  Pizza,
  Coffee,
  Salad,
  Wine,
  ChevronRight,
  Loader2,
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
  const [isResolvingSession, setIsResolvingSession] = useState(false);

  const {
    data: restaurants = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["restaurants", user?.id ?? null],
    queryFn: getRestaurants,
    enabled: Boolean(user) && !isResolvingSession,
  });

  useEffect(() => {
    if (!_hydrated) return;
    let cancelled = false;

    if (user) return;

    setIsResolvingSession(true);
    getMe()
      .then((u) => {
        if (cancelled) return;
        if (!u) router.push("/login");
        else setUser(u);
      })
      .finally(() => {
        if (!cancelled) setIsResolvingSession(false);
      });

    return () => {
      cancelled = true;
    };
  }, [_hydrated, user, router, setUser]);

  const handleSelect = (r: Restaurant) => {
    setRestaurant(r);
    router.push("/dashboard");
  };

  let statusContent;
  if (isLoading || isResolvingSession) {
    statusContent = (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="w-10 h-10 text-[#24422e] animate-spin mb-4" />
        <p className="text-sm text-gray-400 text-center">
          Fetching your restaurants...
        </p>
      </div>
    );
  } else if (isError) {
    const message = error instanceof Error ? error.message : "Unknown error";
    statusContent = (
      <div className="flex flex-col items-center justify-center py-12 border border-red-200 bg-red-50 rounded-xl w-full">
        <p className="text-sm font-medium text-red-700 text-center">
          We couldn't load your restaurants right now.
        </p>
        <p className="text-xs text-red-600 text-center mt-1">
          Please try again in a moment.
        </p>
        <p className="text-xs text-red-500 text-center mt-2">{message}</p>
      </div>
    );
  } else if (restaurants.length === 0) {
    statusContent = (
      <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-xl w-full">
        <Store className="w-10 h-10 text-gray-300 mb-4" />
        <p className="text-sm text-gray-500 text-center">
          No restaurants assigned to your account.
        </p>
        <p className="text-xs text-gray-400 text-center mt-1">
          Please contact your administrator.
        </p>
      </div>
    );
  } else {
    statusContent = (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full">
        {restaurants.map((r) => (
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
    );
  }

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
              DishPatch
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

          {statusContent}
        </div>
      </div>
    </div>
  );
}
