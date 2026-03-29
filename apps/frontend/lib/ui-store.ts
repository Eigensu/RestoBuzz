import { create } from "zustand";

interface UIStore {
  inboxUnread: number;
  setInboxUnread: (count: number) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  inboxUnread: 0,
  setInboxUnread: (count) => set({ inboxUnread: count }),
}));
