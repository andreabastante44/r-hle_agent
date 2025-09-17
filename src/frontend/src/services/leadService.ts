import { Lead } from '../types/lead';
import { mockLeads } from '../mocks/leads';
import { config } from '../config';

const USE_MOCK = config.USE_MOCK;
const API_BASE = config.API_BASE_URL;

export async function fetchLeads(): Promise<Lead[]> {
  if (USE_MOCK) {
    // Simulate network latency
    await new Promise(r => setTimeout(r, 150));
    return mockLeads;
  }
  const res = await fetch(`${API_BASE}/leads`);
  if (!res.ok) throw new Error('Failed to fetch leads');
  return res.json();
}

export async function createLead(lead: Partial<Lead>): Promise<Lead> {
  if (USE_MOCK) {
    const newLead: Lead = { ...lead, id: mockLeads.length + 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), score: 0 } as Lead;
    mockLeads.push(newLead);
    return newLead;
  }
  const res = await fetch(`${API_BASE}/leads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lead)
  });
  if (!res.ok) throw new Error('Failed to create lead');
  return res.json();
}
