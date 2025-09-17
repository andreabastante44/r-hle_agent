import { create } from 'zustand';
import { Lead } from '../types/lead';
import { fetchLeads, createLead } from '../services/leadService';

interface LeadsState {
  leads: Lead[];
  loading: boolean;
  error?: string;
  mode: 'mock' | 'api';
  query: string;
  statusFilter: string;
  minScore: number | null;
  sortBy: string;
  sortDir: 'asc' | 'desc';
  load: () => Promise<void>;
  addLead: (lead: Partial<Lead>) => Promise<Lead | undefined>;
  setQuery: (q: string) => void;
  setStatusFilter: (v: string) => void;
  setMinScore: (v: number | null) => void;
  setSort: (col: string) => void;
  getVisible: () => Lead[];
  updateScores: (scores: Record<number, number>) => void; // id -> score
  resetScores: () => void;
  updateLeadData: (leadId: number, data: Partial<Lead>) => void; // Lead-Daten aktualisieren
}

export const useLeadsStore = create<LeadsState>((set, get) => ({
  leads: [],
  loading: false,
  mode: import.meta.env.VITE_USE_MOCK === 'true' ? 'mock' : 'api',
  query: '',
  statusFilter: '',
  minScore: null,
  sortBy: 'score',
  sortDir: 'desc',
  async load() {
    set({ loading: true, error: undefined });
    try {
      const data = await fetchLeads();
      set({ leads: data, loading: false });
    } catch (e: any) {
      set({ error: e.message || 'Error', loading: false });
    }
  },
  async addLead(lead: Partial<Lead>) {
    try {
      const created = await createLead(lead);
      if (created) {
        set({ leads: [...get().leads, created] });
      }
      return created;
    } catch (e: any) {
      set({ error: e.message || 'Error' });
    }
  },
  setQuery: (q: string) => set({ query: q }),
  setStatusFilter: (v: string) => set({ statusFilter: v }),
  setMinScore: (v: number | null) => set({ minScore: v }),
  setSort: (col: string) => {
    set((s) => {
      if (s.sortBy === col) {
        return { sortDir: s.sortDir === 'asc' ? 'desc' : 'asc' } as Partial<LeadsState>;
      }
      return { sortBy: col, sortDir: col === 'score' ? 'desc' : 'asc' } as Partial<LeadsState>;
    });
  },
  getVisible: () => {
    const { leads, query, statusFilter, minScore, sortBy, sortDir } = get();
    const q = query.trim().toLowerCase();
  let filtered = leads.filter((l: Lead) => {
      if (q) {
        const hay = `${l.company_name||''} ${l.industry||''} ${l.city||''} ${l.email||''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (statusFilter && l.status !== statusFilter) return false;
      if (minScore !== null && (l.score ?? 0) < minScore) return false;
      return true;
    });
  filtered = filtered.sort((a: Lead, b: Lead) => {
      const av: any = (a as any)[sortBy] ?? 0;
      const bv: any = (b as any)[sortBy] ?? 0;
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return filtered;
  },
  updateScores: (scores: Record<number, number>) => {
    set(s => ({
      leads: s.leads.map(l => l.id ? { ...l, score: scores[l.id] ?? l.score } : l)
    }));
  },
  resetScores: () => {
    set(s => ({
      leads: s.leads.map(l => ({ ...l, score: 0 }))
    }));
  },
  updateLeadData: (leadId: number, data: Partial<Lead>) => {
    set(s => ({
      leads: s.leads.map(l => 
        l.id === leadId ? { ...l, ...data } : l
      )
    }));
  }
}));
