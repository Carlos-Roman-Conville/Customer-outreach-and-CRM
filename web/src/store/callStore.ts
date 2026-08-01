import { create } from 'zustand';

interface Bbox {
  west: number;
  south: number;
  east: number;
  north: number;
}

interface CallState {
  bbox: Bbox | null;
  setBbox: (bbox: Bbox | null) => void;
  index: number;
  setIndex: (index: number | ((prev: number) => number)) => void;
}

export const useCallStore = create<CallState>((set) => ({
  bbox: null,
  setBbox: (bbox) => set({ bbox, index: 0 }),
  index: 0,
  setIndex: (index) => set((s) => ({
    index: typeof index === 'function' ? index(s.index) : index,
  })),
}));
