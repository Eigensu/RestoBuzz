import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/lib/auth";
import type { Restaurant } from "@/types";

interface AuthState {
  user: User | null;
  restaurant: Restaurant | null;
  setUser: (user: User | null) => void;
  setRestaurant: (restaurant: Restaurant | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      restaurant: null,
      setUser: (user) => set({ user }),
      setRestaurant: (restaurant) => set({ restaurant }),
    }),
    {
      name: "wa-auth",
      partialize: (state) => ({ restaurant: state.restaurant }),
    },
  ),
);
