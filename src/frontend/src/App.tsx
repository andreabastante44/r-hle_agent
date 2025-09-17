import React, { useEffect, useState } from 'react';
import { useLeadsStore } from './store/useLeadsStore';
import { Lead } from './types/lead';
import ScoringPanel from './components/ScoringPanel';
import { startGraphAnalysis, validateGraphInput, getValidationError } from './services/graphService';

const headers: { key: string; label: string; numeric?: boolean }[] = [
  { key: 'id', label: 'ID' },
  { key: 'company_name', label: 'Unternehmen' },
  { key: 'lead', label: 'Lead'},
  { key: 'location', label: 'Standort' },
  { key: 'postal_code', label: 'PLZ'},
  { key: 'country', label: 'Land' },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Telefon' },
  { key: 'website', label: 'Website' },
  { key: 'action', label: 'Aktion' },
  { key: 'employee_count', label: 'Mitarbeiter', numeric: true },
  { key: 'revenue', label: 'Umsatz', numeric: true },
  { key: 'industry', label: 'Branche' },
  { key: 'materials', label: 'Materialien' },
  { key: 'company_type', label: 'Unternehmensart' },
  { key: 'position', label: 'Position' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'score', label: 'Score', numeric: true },
  { key: 'status', label: 'Status' }
];

export default function App() {
  const {
    load, loading, error, mode,
    getVisible, query, statusFilter, minScore,
    setQuery, setStatusFilter, setMinScore,
    sortBy, sortDir, setSort, updateLeadData
  } = useLeadsStore();
  const [panelOpen, setPanelOpen] = useState(false);
  const [runningLeads, setRunningLeads] = useState<Set<number>>(new Set());

  useEffect(() => { load(); }, [load]);
  const visible = getVisible();

  const sortIcon = (col: string) => {
    if (sortBy !== col) return '↕';
    return sortDir === 'asc' ? '▲' : '▼';
  };

  const startGraphWorkflow = async (lead: Lead) => {
    if (!lead.id) return;
    
    // Validierung der erforderlichen Daten
    if (!validateGraphInput(lead)) {
      const errorMsg = getValidationError(lead);
      alert(`Graph kann nicht gestartet werden: ${errorMsg}`);
      return;
    }
    
    setRunningLeads(prev => new Set(prev).add(lead.id!));
    
    try {
      // Daten für den Graph vorbereiten
      const graphInput = {
        company_name: lead.company_name || '',
        lead: lead.lead || '',
        location: lead.location || '',
        postal_code: lead.postal_code || '',
        email: lead.email || '',
        website: lead.website || ''
      };
      
      console.log('Starting graph workflow for lead:', graphInput);
      
      // Graph-Analyse starten
      const result = await startGraphAnalysis(graphInput);
      
      if (result.success) {
        console.log('Graph workflow completed successfully for lead:', lead.company_name);
        console.log('Generated reports:', result.reports);
        console.log('Extracted data:', result.extracted_data);
        
        // Extrahierte Daten in Lead eintragen
        if (result.extracted_data) {
          const updateData: Partial<Lead> = {};
          
          if (result.extracted_data.employee_count !== undefined) {
            updateData.employee_count = result.extracted_data.employee_count;
            console.log(`📊 Mitarbeiteranzahl extrahiert: ${result.extracted_data.employee_count}`);
          }
          
          if (result.extracted_data.revenue !== undefined) {
            updateData.revenue = result.extracted_data.revenue;
            console.log(`💰 Umsatz extrahiert: ${result.extracted_data.revenue}`);
          }
          
          if (result.extracted_data.linkedin) {
            updateData.linkedin = result.extracted_data.linkedin;
            console.log(`🔗 LinkedIn URL extrahiert: ${result.extracted_data.linkedin}`);
          }
          
          // Lead-Daten aktualisieren
          if (Object.keys(updateData).length > 0) {
            updateLeadData(lead.id!, updateData);
            console.log('✅ Lead-Daten aktualisiert:', updateData);
          }
        }
        
        // Erfolg anzeigen
        const extractedInfo = result.extracted_data ? 
          `\n\nExtrahierte Daten:\n` +
          (result.extracted_data.employee_count ? `• Mitarbeiter: ${result.extracted_data.employee_count}\n` : '') +
          (result.extracted_data.revenue ? `• Umsatz: ${Intl.NumberFormat('de-DE').format(result.extracted_data.revenue)} €\n` : '') +
          (result.extracted_data.linkedin ? `• LinkedIn: ${result.extracted_data.linkedin}\n` : '')
          : '';
        
        alert(`Graph-Analyse für "${lead.company_name}" abgeschlossen! ${result.reports.length} Berichte erstellt.${extractedInfo}`);
      } else {
        console.error('Graph workflow failed:', result.error);
        alert(`Fehler bei Graph-Analyse: ${result.error}`);
      }
      
    } catch (error) {
      console.error('Error running graph workflow:', error);
      alert(`Unerwarteter Fehler: ${error instanceof Error ? error.message : 'Unbekannter Fehler'}`);
    } finally {
      setRunningLeads(prev => {
        const newSet = new Set(prev);
        newSet.delete(lead.id!);
        return newSet;
      });
    }
  };

  return (
    <div className="px-6 py-6 max-w-[1500px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Lead Dashboard</h1>
        <span className={`text-xs font-medium px-2 py-1 rounded border ${mode==='mock' ? 'bg-yellow-100 text-yellow-700 border-yellow-300':'bg-green-100 text-green-700 border-green-300'}`}>Mode: {mode.toUpperCase()}</span>
      </div>
      <div className="flex justify-end mb-4">
        <button onClick={()=>setPanelOpen(true)} className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded shadow-soft">Scoring anpassen</button>
      </div>

      <div className="bg-card border border-card-border rounded-lg shadow-soft mb-5 p-4 flex flex-wrap gap-4 items-end">
        <div className="flex flex-col w-56">
          <label className="text-xs font-medium text-slate-500 mb-1">Search</label>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Company, industry, city..."
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
        </div>
        <div className="flex flex-col w-40">
          <label className="text-xs font-medium text-slate-500 mb-1">Status</label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <option value="">All</option>
            <option value="new">New</option>
            <option value="qualified">Qualified</option>
            <option value="contacted">Contacted</option>
          </select>
        </div>
        <div className="flex flex-col w-44">
          <label className="text-xs font-medium text-slate-500 mb-1">Min Score</label>
          <input
            type="number"
            value={minScore ?? ''}
            onChange={e => setMinScore(e.target.value === '' ? null : Number(e.target.value))}
            placeholder="e.g. 50"
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
        <button
          onClick={() => { setQuery(''); setStatusFilter(''); setMinScore(null); }}
          className="h-9 px-3 rounded-md text-sm font-medium border bg-white hover:bg-slate-50 transition"
        >Reset</button>
        <div className="ml-auto text-xs text-slate-500">{visible.length} result(s)</div>
      </div>

      <div className="overflow-auto border border-card-border rounded-lg shadow-soft bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
            <tr>
              {headers.map(h => (
                <th
                  key={h.key}
                  onClick={() => setSort(h.key)}
                  className="px-3 py-2 font-semibold cursor-pointer select-none whitespace-nowrap text-left hover:bg-slate-100 border-b border-card-border"
                >
                  <span className="inline-flex items-center gap-1">{h.label}<span className="text-[10px] opacity-60">{sortIcon(h.key)}</span></span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={headers.length} className="px-4 py-6 text-center text-slate-500">Loading...</td></tr>
            )}
            {!loading && visible.map((l: Lead) => (
              <tr key={l.id} className="border-b last:border-b-0 border-card-border hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-800">{l.id}</td>
                <td className="px-3 py-2 font-medium text-slate-800">{l.company_name}</td>
                <td className="px-3 py-2">{l.lead}</td>
                <td className="px-3 py-2">{l.location}</td>
                <td className="px-3 py-2">{l.postal_code}</td>
                <td className="px-3 py-2">{l.country}</td>
                <td className="px-3 py-2">{l.email}</td>
                <td className="px-3 py-2">{l.phone}</td>
                <td className="px-3 py-2 text-blue-600 underline decoration-dotted"><a href={l.website} target="_blank" rel="noreferrer" onClick={e => !l.website && e.preventDefault()}>{l.website?.replace(/^https?:\/\//,'')}</a></td>
                <td className="px-3 py-2 text-center">
                  <button
                    onClick={() => startGraphWorkflow(l)}
                    disabled={runningLeads.has(l.id!) || !validateGraphInput(l)}
                    className={`inline-flex items-center justify-center w-8 h-8 rounded-full transition-colors ${
                      runningLeads.has(l.id!)
                        ? 'bg-blue-100 text-blue-500 cursor-not-allowed'
                        : !validateGraphInput(l)
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-green-100 hover:bg-green-200 text-green-700'
                    }`}
                    title={runningLeads.has(l.id!) ? 'Graph läuft...' : !validateGraphInput(l) ? getValidationError(l) : 'Graph starten'}
                  >
                    {runningLeads.has(l.id!) ? (
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd"/>
                      </svg>
                    )}
                  </button>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{l.employee_count ?? '-'}</td>
                <td className="px-3 py-2 text-right tabular-nums">{l.revenue ? Intl.NumberFormat('en', { notation:'compact' }).format(l.revenue) : '-'}</td>
                <td className="px-3 py-2">{l.industry || '-'}</td>
                <td className="px-3 py-2">{l.materials || '-'}</td>
                <td className="px-3 py-2">{l.company_type || '-'}</td>
                <td className="px-3 py-2">{l.position || '-'}</td>
                <td className="px-3 py-2 text-blue-600 underline decoration-dotted">
                  {l.linkedin ? <a href={l.linkedin} target="_blank" rel="noreferrer">{l.linkedin.replace(/^https?:\/\/(www\.)?/,'')}</a> : '-'}
                </td>
                <td className="px-3 py-2 text-right font-semibold">
                  <span className={(() => {
                    const s = l.score ?? 0;
                    if (s === 0) return 'text-slate-400';
                    if (s === 1) return 'text-red-600';
                    if (s === 2) return 'text-amber-500';
                    return 'text-green-600';
                  })()}>{l.score ?? 0}</span>
                </td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${!l.status ? 'bg-slate-100 text-slate-600 border-slate-300':'status'}`}>{l.status || '—'}</span>
                </td>
              </tr>
            ))}
            {!loading && visible.length === 0 && (
              <tr><td colSpan={headers.length} className="px-4 py-10 text-center text-slate-500">No leads match filters</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {error && <div className="mt-4 text-sm text-red-600">{error}</div>}
      <ScoringPanel open={panelOpen} onClose={()=>setPanelOpen(false)} />
    </div>
  );
}
