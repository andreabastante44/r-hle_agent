export interface Lead {
  id?: number;
  company_name?: string;
  lead?: string;
  location?: string;
  postal_code?: string;
  website?: string;
  email?: string;
  phone?: string;
  country?: string;
  city?: string;
  industry?: string;
  materials?: string;
  company_type?: string;
  linkedin?: string;
  position?: string; // Berufsposition
  employee_count?: number;
  revenue?: number;
  score?: number;
  status?: string;
  created_at?: string;
  updated_at?: string;
  // Add any derived fields we might calculate client-side
  score_breakdown?: Record<string, number>;
}
