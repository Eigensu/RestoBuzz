import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User } from "@/lib/auth";
import type { Restaurant } from "@/types";

interface AuthState {
  user: User | null;
  restaurant: Restaurant | null;
  _hydrated: boolean;
  setUser: (user: User | null) => void;
  setRestaurant: (restaurant: Restaurant | null) => void;
  setHydrated: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      restaurant: null,
      _hydrated: false,
      setUser: (user) => set({ user }),
      setRestaurant: (restaurant) => set({ restaurant }),
      setHydrated: () => set({ _hydrated: true }),
    }),
    {
      name: "wa-auth",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        user: state.user,
        restaurant: state.restaurant,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated();
      },
    },
  ),
);
