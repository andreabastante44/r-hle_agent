import { Lead } from '../types/lead';

// API Base URL - kann über Umgebungsvariablen konfiguriert werden
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface GraphInput {
  company_name: string;
  lead: string;
  location: string;
  postal_code: string;
  email: string;
  website: string;
}

export interface GraphResult {
  success: boolean;
  reports: Report[];
  extracted_data?: {
    employee_count?: number;
    revenue?: number;
    linkedin?: string;
  };
  error?: string;
}

export interface Report {
  title: string;
  content: string;
  is_markdown: boolean;
}

export interface LeadData {
  id: string;
  name: string;
  address: string;
  email: string;
  phone: string;
  profile: string;
}

export interface CompanyData {
  name: string;
  profile: string;
  website: string;
}

export interface GraphState {
  leads_ids: string[];
  leads_data: any[];
  current_lead: LeadData;
  company_data: CompanyData;
  reports: Report[];
  reports_folder_link: string;
  custom_outreach_report_link: string;
  personalized_email: string;
  interview_script: string;
  number_leads: number;
}

/**
 * Konvertiert Lead-Daten vom Frontend zum GraphState-Format
 */
function convertLeadToGraphState(input: GraphInput): GraphState {
  // Extrahiere PLZ aus address falls verfügbar
  const leadAddress = `${input.postal_code} ${input.location}`;
  
  const leadData: LeadData = {
    id: `LEAD-${Date.now()}`, // Temporäre ID generieren
    name: input.lead,
    address: leadAddress,
    email: input.email,
    phone: '', // Phone nicht in GraphInput verfügbar
    profile: ''
  };

  const companyData: CompanyData = {
    name: input.company_name,
    profile: '', // Wird durch Graph-Workflow ermittelt
    website: input.website
  };

  const graphState: GraphState = {
    leads_ids: [leadData.id],
    leads_data: [leadData],
    current_lead: leadData,
    company_data: companyData,
    reports: [],
    reports_folder_link: '',
    custom_outreach_report_link: '',
    personalized_email: '',
    interview_script: '',
    number_leads: 1
  };

  return graphState;
}

/**
 * Startet den Graph-Workflow mit den Lead-Daten
 */
export async function startGraphAnalysis(input: GraphInput): Promise<GraphResult> {
  try {
    console.log('Converting lead data to GraphState format:', input);
    
    // Lead-Daten zum GraphState-Format konvertieren
    const graphState = convertLeadToGraphState(input);
    
    console.log('Prepared GraphState for API:', graphState);
    
    // API-Aufruf an das Python-Backend
    const response = await fetch(`${API_BASE_URL}/api/run-workflow`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(graphState)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    
    return {
      success: true,
      reports: result.reports || [],
    };
    
  } catch (error) {
    console.error('Error in graph analysis:', error);
    return {
      success: false,
      reports: [],
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}

/**
 * Prüft, ob alle erforderlichen Daten für den Graph vorhanden sind
 */
export function validateGraphInput(lead: Lead): boolean {
  return !!(
    lead.company_name &&
    lead.lead &&
    lead.location &&
    lead.postal_code &&
    lead.email
    // website ist optional
  );
}

/**
 * Erstellt eine lesbare Fehlermeldung für fehlende Daten
 */
export function getValidationError(lead: Lead): string {
  const missing: string[] = [];
  
  if (!lead.company_name) missing.push('Unternehmen');
  if (!lead.lead) missing.push('Lead-Name');
  if (!lead.location) missing.push('Standort');
  if (!lead.postal_code) missing.push('PLZ');
  if (!lead.email) missing.push('Email');
  
  if (missing.length === 0) return '';
  
  return `Fehlende Daten: ${missing.join(', ')}`;
}
