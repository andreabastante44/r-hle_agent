import React, { useState } from 'react';
import { useLeadsStore } from '../store/useLeadsStore';
import { useScoring, applyScoring, SIZE_BUCKETS } from '../hooks/useScoring';
import TagInput from './TagInput';

const POSITION_SUGGESTIONS = ['CEO','CTO','CFO','Head of Sales','Head of R&D','Einkauf','Procurement','Partner','Operations','Product Manager'];
const INDUSTRY_SUGGESTIONS = ['Software','Biotech','Logistics','Consulting','Retail','Energy','Healthcare','FinTech','Manufacturing','Media','Automotive'];

interface Props { open: boolean; onClose: () => void; }

const ScoringPanel: React.FC<Props> = ({ open, onClose }) => {
  const { leads, updateScores, resetScores } = useLeadsStore();
  const [scoring] = useScoring({});
  const [capInput, setCapInput] = useState('');

  if (!open) return null;

  const apply = () => {
    const scores = applyScoring(leads, {
      sizeKeywords: scoring.sizeKeywords,
      positionKeywords: scoring.positionKeywords,
      industryKeywords: scoring.industryKeywords,
      maxScorePerArea: scoring.maxScorePerArea
    });
    updateScores(scores);
    onClose();
  };

  const resetAll = () => {
    scoring.reset();
    resetScores();
  };

  const toggleCap = () => {
    if (!capInput) {
      scoring.setMaxCap(undefined);
      return;
    }
    const v = Number(capInput);
    scoring.setMaxCap(Number.isFinite(v) && v > 0 ? v : undefined);
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto h-full w-full max-w-xl bg-white shadow-large flex flex-col">
        <div className="px-5 py-4 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Keyword Scoring</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-700 text-sm">Schließen</button>
        </div>
        <div className="p-5 space-y-8 overflow-y-auto text-sm">
          <section>
            <h3 className="text-sm font-medium mb-3 text-slate-600">Mitarbeiteranzahl (Buckets)</h3>
            <div className="grid grid-cols-2 gap-3">
              {SIZE_BUCKETS.map(b => {
                const active = scoring.sizeKeywords.includes(b.id);
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => scoring.toggleSizeBucket(b.id)}
                    className={`border rounded px-2 py-1 text-xs text-left transition ${active ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white hover:bg-slate-50'}`}
                  >{b.id}</button>
                );
              })}
            </div>
          </section>

          <div className="space-y-3">
            <TagInput
              label="Berufsposition Keywords"
              tags={scoring.positionKeywords}
              onAdd={kw => scoring.addPosition(kw)}
              onRemove={kw => scoring.removePosition(kw)}
              placeholder="z.B. CEO, Einkauf..."
            />
            <div className="flex flex-wrap gap-2">
              {POSITION_SUGGESTIONS.map(p => {
                const active = scoring.positionKeywords.includes(p.toLowerCase());
                return (
                  <button
                    type="button"
                    key={p}
                    onClick={() => scoring.addPosition(p)}
                    className={`text-xs px-2 py-1 rounded border transition ${active ? 'bg-blue-600 text-white border-blue-600' : 'bg-white hover:bg-slate-50'}`}
                  >{p}</button>
                );
              })}
            </div>
          </div>

          <div className="space-y-3">
            <TagInput
              label="Branchen Keywords"
              tags={scoring.industryKeywords}
              onAdd={kw => scoring.addIndustry(kw)}
              onRemove={kw => scoring.removeIndustry(kw)}
              placeholder="z.B. Maschinenbau, Automotive..."
            />
            <div className="flex flex-wrap gap-2">
              {INDUSTRY_SUGGESTIONS.map(ind => {
                const active = scoring.industryKeywords.includes(ind.toLowerCase());
                return (
                  <button
                    type="button"
                    key={ind}
                    onClick={() => scoring.addIndustry(ind)}
                    className={`text-xs px-2 py-1 rounded border transition ${active ? 'bg-blue-600 text-white border-blue-600' : 'bg-white hover:bg-slate-50'}`}
                  >{ind}</button>
                );
              })}
            </div>
          </div>

          <section className="space-y-2">
            <h3 className="text-sm font-medium text-slate-600">Optionale Kappung pro Bereich</h3>
            <div className="flex gap-2 items-center">
              <input
                value={capInput}
                onChange={e => setCapInput(e.target.value)}
                placeholder="z.B. 3"
                className="h-9 w-24 rounded border px-2 text-sm"
              />
              <button onClick={toggleCap} className="h-9 px-3 bg-slate-700 text-white rounded text-xs">Setzen</button>
              <span className="text-xs text-slate-500">aktuell: {typeof scoring.maxScorePerArea === 'number' ? scoring.maxScorePerArea : '∞'}</span>
            </div>
          </section>

          <div className="flex items-center justify-between pt-4 border-t">
            <button onClick={resetAll} className="text-xs text-slate-500 hover:text-slate-700">Reset</button>
            <button onClick={apply} className="bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm px-4 py-2 rounded shadow-soft">Scoring anwenden</button>
          </div>
          {/* Optional Badge Farben aktivieren: In App.tsx <span> um Score mit Badge-Klassen ersetzen
            if (s <= 3) red, 4-6 yellow, >=7 green */}
        </div>
      </div>
    </div>
  );
};

export default ScoringPanel;