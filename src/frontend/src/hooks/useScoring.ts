import { Lead } from '../types/lead';

export interface ScoringConfig {
  sizeKeywords: string[]; // actually selected size buckets e.g. ['0-50','51-500']
  positionKeywords: string[];
  industryKeywords: string[];
  maxScorePerArea?: number; // optional cap per area
}

export const SIZE_BUCKETS = [
  { id: '0-50', min:0, max:50 },
  { id: '51-500', min:51, max:500 },
  { id: '501-5000', min:501, max:5000 },
  { id: '5001-100000', min:5001, max:100000 }
];

function normalizeText(v?: string): string {
  if (!v) return '';
  return v
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .trim();
}

function inBucket(emp: number | undefined, bucketId: string): boolean {
  if (typeof emp !== 'number') return false;
  const b = SIZE_BUCKETS.find(b => b.id === bucketId);
  if (!b) return false;
  return emp >= b.min && emp <= b.max;
}

export function applyScoring(leads: Lead[], config: ScoringConfig): Record<number, number> {
  const posSet = Array.from(new Set(config.positionKeywords.map(normalizeText).filter(Boolean)));
  const indSet = Array.from(new Set(config.industryKeywords.map(normalizeText).filter(Boolean)));
  const sizeSet = Array.from(new Set(config.sizeKeywords.map(k => k))); // already bucket ids
  const maxCap = typeof config.maxScorePerArea === 'number' ? config.maxScorePerArea : Infinity;

  const scores: Record<number, number> = {};
  for (const l of leads) {
    if (!l.id) continue;
    let total = 0;

    // size area
    let sizePoints = 0;
    for (const bucket of sizeSet) {
      if (inBucket(l.employee_count, bucket)) sizePoints += 1;
    }
    total += Math.min(sizePoints, maxCap);

    const normPos = normalizeText(l.position);
    const normInd = normalizeText(l.industry);

    // position area
    let posPoints = 0;
    for (const pk of posSet) {
      if (pk && normPos.includes(pk)) posPoints += 1;
    }
    total += Math.min(posPoints, maxCap);

    // industry area
    let indPoints = 0;
    for (const ik of indSet) {
      if (ik && normInd.includes(ik)) indPoints += 1;
    }
    total += Math.min(indPoints, maxCap);

    scores[l.id] = total;
  }
  return scores;
}

export interface UseScoringState extends ScoringConfig {
  setSizeKeywords: (v: string[]) => void;
  addPosition: (kw: string) => void;
  removePosition: (kw: string) => void;
  addIndustry: (kw: string) => void;
  removeIndustry: (kw: string) => void;
  toggleSizeBucket: (id: string) => void;
  setMaxCap: (v: number | undefined) => void;
  reset: () => void;
}

import { useState, useCallback } from 'react';

export function useScoring(initial?: Partial<ScoringConfig>): [UseScoringState] {
  const [sizeKeywords, setSizeKeywords] = useState<string[]>(initial?.sizeKeywords || []);
  const [positionKeywords, setPositionKeywords] = useState<string[]>(initial?.positionKeywords || []);
  const [industryKeywords, setIndustryKeywords] = useState<string[]>(initial?.industryKeywords || []);
  const [maxScorePerArea, setMaxScorePerArea] = useState<number | undefined>(initial?.maxScorePerArea);

  const addPosition = useCallback((kw: string) => {
    const n = normalizeText(kw);
    if (!n) return;
    setPositionKeywords(list => list.includes(n) ? list : [...list, n]);
  }, []);
  const removePosition = useCallback((kw: string) => {
    setPositionKeywords(list => list.filter(i => i !== kw));
  }, []);

  const addIndustry = useCallback((kw: string) => {
    const n = normalizeText(kw);
    if (!n) return;
    setIndustryKeywords(list => list.includes(n) ? list : [...list, n]);
  }, []);
  const removeIndustry = useCallback((kw: string) => {
    setIndustryKeywords(list => list.filter(i => i !== kw));
  }, []);

  const toggleSizeBucket = useCallback((id: string) => {
    setSizeKeywords(list => list.includes(id) ? list.filter(b => b !== id) : [...list, id]);
  }, []);

  const setMaxCap = useCallback((v: number | undefined) => {
    setMaxScorePerArea(v);
  }, []);

  const reset = useCallback(() => {
    setSizeKeywords([]);
    setPositionKeywords([]);
    setIndustryKeywords([]);
    setMaxScorePerArea(undefined);
  }, []);

  return [{
    sizeKeywords, positionKeywords, industryKeywords, maxScorePerArea,
    setSizeKeywords,
    addPosition, removePosition,
    addIndustry, removeIndustry,
    toggleSizeBucket,
    setMaxCap,
    reset
  }];
}
