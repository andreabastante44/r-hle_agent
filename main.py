"""
Main API Server - Verbindung zwischen Frontend und LangGraph Backend
Stellt REST API Endpoints für das Lead Dashboard bereit und integriert den LangGraph Workflow.
"""

import os
import sys
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import asyncio
from pathlib import Path

# Backend imports
sys.path.append(str(Path(__file__).parent / "src"))
from src.graph import OutReachAutomation
from src.state import GraphState, LeadData, CompanyData


# Pydantic Models für API
class Lead(BaseModel):
    """Frontend Lead Model - entspricht der TypeScript Lead Interface"""
    id: Optional[int] = None
    company_name: Optional[str] = None
    lead: Optional[str] = None
    location: Optional[str] = None
    postal_code: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    industry: Optional[str] = None
    materials: Optional[str] = None
    company_type: Optional[str] = None
    linkedin: Optional[str] = None
    position: Optional[str] = None
    employee_count: Optional[int] = None
    revenue: Optional[int] = None
    score: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    score_breakdown: Optional[Dict[str, int]] = None


class CreateLeadRequest(BaseModel):
    """Request Model für Lead-Erstellung"""
    company_name: str
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = "DE"
    city: Optional[str] = None
    industry: Optional[str] = None
    position: Optional[str] = None
    employee_count: Optional[int] = None
    revenue: Optional[int] = None


class ProcessLeadRequest(BaseModel):
    """Request Model für Lead-Processing mit LangGraph"""
    lead_id: int
    run_automation: bool = True


class GraphStateRequest(BaseModel):
    """Request Model für direkten GraphState-Aufruf vom Frontend"""
    leads_ids: List[str]
    leads_data: List[Dict[str, Any]]
    current_lead: Dict[str, Any]
    company_data: Dict[str, Any]
    reports: List[Dict[str, Any]] = []
    reports_folder_link: str = ""
    custom_outreach_report_link: str = ""
    personalized_email: str = ""
    interview_script: str = ""
    number_leads: int = 1


class APIResponse(BaseModel):
    """Standard API Response"""
    success: bool
    message: str
    data: Optional[Any] = None


class GraphResult(BaseModel):
    """Response Model für Graph-Workflow-Ergebnisse"""
    success: bool
    reports: List[Dict[str, Any]]
    extracted_data: Optional[Dict[str, Any]] = None  # Strukturierte Daten für Frontend
    error: Optional[str] = None


# FastAPI App
app = FastAPI(
    title="Lead Agent API",
    description="API für Lead Dashboard mit LangGraph Integration",
    version="1.0.0"
)

# CORS Middleware für Frontend-Verbindung
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:5173", 
        "http://localhost:5174",  # Lead Agent Frontend Port
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174"   # Lead Agent Frontend Port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Lead Storage (für Development)
# TODO: In Production durch echte Datenbank ersetzen
leads_db: List[Lead] = []
next_lead_id = 1

# LangGraph Automation Instance
automation = OutReachAutomation()


def initialize_mock_leads():
    """Initialisiert Mock-Leads für Development"""
    global leads_db, next_lead_id
    
    mock_leads = [
        Lead(id=1, company_name='Torsten Thiemann', lead='Torsten Thiemann', location='Westertimke', 
             postal_code='27412', country='DE', email='torsten.thiemann@thorsten-thiemann.de', 
             website='https://thorsten-thiemann.de', phone='+49 30 12345678', status='new', score=0,
             created_at=datetime.now().isoformat()),
        Lead(id=2, company_name='Beta BioTech AG', lead='Sarah Müller', location='Hamburg', 
             postal_code='20095', country='DE', email='sarah.mueller@beta.example', 
             website='https://beta.example', phone='+49 40 98765432', status='qualified', score=0,
             created_at=datetime.now().isoformat()),
        Lead(id=3, company_name='Gamma Logistics KG', lead='Thomas Schmidt', location='München', 
             postal_code='80331', country='DE', email='thomas.schmidt@gamma.example', 
             website='https://gamma.example', phone='+49 89 11223344', status='contacted', score=0,
             created_at=datetime.now().isoformat()),
        Lead(id=4, company_name='Delta Consulting GmbH', lead='Jennifer Wagner', location='Düsseldorf', 
             postal_code='40210', country='DE', email='jennifer.wagner@delta.example', 
             website='https://delta.example', phone='+49 211 55667788', status='new', score=0,
             created_at=datetime.now().isoformat()),
        Lead(id=5, company_name='Capgemini', lead='Armin Ibrahimovic', location='Stuttgart', 
             postal_code='70178', country='DE', email='armin.ibrahimovic@capgemini.de', 
             website='https://capgemini.com', phone='+49 30 12345678', status='new', score=0,
             created_at=datetime.now().isoformat()),
    ]
    
    leads_db.extend(mock_leads)
    next_lead_id = len(mock_leads) + 1


def extract_structured_data_from_reports(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extrahiert strukturierte Daten aus den Reports für Frontend-Spalten"""
    extracted_data = {
        "employee_count": None,
        "revenue": None,
        "linkedin": None
    }
    
    for report in reports:
        title = report.get("title", "").lower()
        content = report.get("content", "")
        
        # Unternehmensinformationen -> Mitarbeiteranzahl
        if "unternehmensinformationen" in title or "unternehmens" in title:
            # Versuche Mitarbeiteranzahl aus dem Content zu extrahieren
            import re
            # Suche nach Zahlen mit "Mitarbeiter", "Angestellte", "Beschäftigte" etc.
            employee_patterns = [
                r'(\d+)\s*(?:Mitarbeiter|Angestellte|Beschäftigte|Personal)',
                r'(?:Mitarbeiter|Angestellte|Beschäftigte|Personal)[:\s]*(\d+)',
                r'(\d+)\s*(?:Mitarbeiter|Angestellte|Beschäftigte|Personal)',
                r'Personalstärke[:\s]*(\d+)',
                r'Belegschaft[:\s]*(\d+)'
            ]
            
            for pattern in employee_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    try:
                        extracted_data["employee_count"] = int(match.group(1))
                        break
                    except ValueError:
                        continue
        
        # Finanzen -> Umsatz
        elif "finanzen" in title or "finanz" in title:
            # Versuche Umsatz aus dem Content zu extrahieren
            revenue_patterns = [
                r'Umsatz[:\s]*(\d+(?:[.,]\d+)?)\s*(?:Mio|Millionen|Million|Mio\.|€|EUR|Euro)',
                r'(\d+(?:[.,]\d+)?)\s*(?:Mio|Millionen|Million|Mio\.|€|EUR|Euro)\s*Umsatz',
                r'Jahresumsatz[:\s]*(\d+(?:[.,]\d+)?)\s*(?:Mio|Millionen|Million|Mio\.|€|EUR|Euro)',
                r'Umsatz[:\s]*(\d+(?:[.,]\d+)?)\s*(?:Millionen|Million|Mio)',
                r'(\d+(?:[.,]\d+)?)\s*(?:Millionen|Million|Mio)\s*Umsatz'
            ]
            
            for pattern in revenue_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    try:
                        revenue_str = match.group(1).replace(',', '.')
                        revenue_value = float(revenue_str)
                        # Konvertiere zu Millionen Euro
                        if 'mio' in match.group(0).lower() or 'millionen' in match.group(0).lower():
                            extracted_data["revenue"] = int(revenue_value * 1_000_000)
                        else:
                            extracted_data["revenue"] = int(revenue_value)
                        break
                    except ValueError:
                        continue
        
        # LinkedIn -> LinkedIn URL
        elif "linkedin" in title:
            # Versuche LinkedIn URL aus dem Content zu extrahieren
            linkedin_patterns = [
                r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_]+/?',
                r'linkedin\.com/in/[a-zA-Z0-9\-_]+/?',
                r'https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9\-_]+/?',
                r'linkedin\.com/company/[a-zA-Z0-9\-_]+/?'
            ]
            
            for pattern in linkedin_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    url = match.group(0)
                    if not url.startswith('http'):
                        url = 'https://' + url
                    extracted_data["linkedin"] = url
                    break
    
    return extracted_data


def lead_to_graph_state(lead: Lead) -> GraphState:
    """Konvertiert Frontend Lead zu Backend GraphState"""
    
    # LeadData für Backend erstellen
    lead_data = LeadData(
        id=f"LEAD-{lead.id:03d}" if lead.id else "LEAD-000",
        name=lead.lead or lead.company_name or "Unknown",
        address=f"{lead.postal_code} {lead.location}" if lead.postal_code and lead.location else lead.location or "",
        email=lead.email or "",
        phone=lead.phone or "",
        profile=f"{lead.position} working in {lead.industry}" if lead.position and lead.industry else ""
    )
    
    # CompanyData für Backend erstellen
    company_data = CompanyData(
        name=lead.company_name or "",
        profile=lead.industry or "",
        website=lead.website or ""
    )
    
    # GraphState erstellen
    initial_state: GraphState = {
        "leads_ids": [lead_data.id],
        "leads_data": [lead_data.model_dump()],
        "current_lead": lead_data,
        "company_data": company_data,
        "reports": [],
        "reports_folder_link": "",
        "custom_outreach_report_link": "",
        "personalized_email": "",
        "interview_script": "",
        "number_leads": 1
    }
    
    return initial_state


async def process_lead_with_automation(lead: Lead) -> Dict[str, Any]:
    """Führt LangGraph Automation für einen Lead aus"""
    try:
        # Lead zu GraphState konvertieren
        graph_state = lead_to_graph_state(lead)
        
        # LangGraph Workflow ausführen
        print(f"🚀 Starte Automation für Lead: {lead.company_name}")
        final_state = automation.run_workflow(graph_state)
        
        # Ergebnisse verarbeiten
        reports = final_state.get('reports', [])
        score = len(reports)  # Einfaches Scoring basierend auf Report-Anzahl
        
        # Lead Score und Status aktualisieren
        lead.score = min(score, 10)  # Max Score von 10
        lead.status = 'processed' if score > 0 else 'failed'
        lead.updated_at = datetime.now().isoformat()
        
        return {
            'success': True,
            'reports_generated': len(reports),
            'reports': [{'title': r.title, 'content': r.content[:200] + '...' if len(r.content) > 200 else r.content} for r in reports],
            'score': lead.score
        }
        
    except Exception as e:
        print(f"❌ Fehler bei Lead Automation: {str(e)}")
        lead.status = 'error'
        lead.updated_at = datetime.now().isoformat()
        return {
            'success': False,
            'error': str(e),
            'score': 0
        }


# API Endpoints

@app.get("/")
async def root():
    """Root Endpoint - API Status"""
    return {"message": "Lead Agent API läuft", "version": "1.0.0", "status": "active"}


@app.get("/leads", response_model=List[Lead])
async def get_leads():
    """Alle Leads abrufen"""
    return leads_db


@app.get("/leads/{lead_id}", response_model=Lead)
async def get_lead(lead_id: int):
    """Einzelnen Lead abrufen"""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nicht gefunden")
    return lead


@app.post("/leads", response_model=Lead)
async def create_lead(request: CreateLeadRequest):
    """Neuen Lead erstellen"""
    global next_lead_id
    
    new_lead = Lead(
        id=next_lead_id,
        company_name=request.company_name,
        website=request.website,
        email=request.email,
        phone=request.phone,
        country=request.country,
        city=request.city,
        industry=request.industry,
        position=request.position,
        employee_count=request.employee_count,
        revenue=request.revenue,
        score=0,
        status='new',
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    leads_db.append(new_lead)
    next_lead_id += 1
    
    return new_lead


@app.post("/leads/{lead_id}/process", response_model=APIResponse)
async def process_lead(lead_id: int, background_tasks: BackgroundTasks, request: ProcessLeadRequest = ProcessLeadRequest(lead_id=0)):
    """Lead mit LangGraph Automation verarbeiten"""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nicht gefunden")
    
    if not request.run_automation:
        return APIResponse(
            success=True,
            message="Lead-Processing übersprungen",
            data={"lead_id": lead_id, "status": lead.status}
        )
    
    # Automation im Hintergrund ausführen
    lead.status = 'processing'
    lead.updated_at = datetime.now().isoformat()
    
    async def run_automation():
        result = await process_lead_with_automation(lead)
        print(f"✅ Automation abgeschlossen für Lead {lead_id}: {result}")
    
    background_tasks.add_task(run_automation)
    
    return APIResponse(
        success=True,
        message="Lead-Processing gestartet",
        data={"lead_id": lead_id, "status": "processing"}
    )


@app.put("/leads/{lead_id}", response_model=Lead)
async def update_lead(lead_id: int, updated_lead: CreateLeadRequest):
    """Lead aktualisieren"""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nicht gefunden")
    
    # Lead-Daten aktualisieren
    lead.company_name = updated_lead.company_name
    lead.website = updated_lead.website
    lead.email = updated_lead.email
    lead.phone = updated_lead.phone
    lead.country = updated_lead.country
    lead.city = updated_lead.city
    lead.industry = updated_lead.industry
    lead.position = updated_lead.position
    lead.employee_count = updated_lead.employee_count
    lead.revenue = updated_lead.revenue
    lead.updated_at = datetime.now().isoformat()
    
    return lead


@app.delete("/leads/{lead_id}", response_model=APIResponse)
async def delete_lead(lead_id: int):
    """Lead löschen"""
    global leads_db
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nicht gefunden")
    
    leads_db = [l for l in leads_db if l.id != lead_id]
    
    return APIResponse(
        success=True,
        message="Lead erfolgreich gelöscht",
        data={"lead_id": lead_id}
    )


@app.post("/api/run-workflow", response_model=GraphResult)
async def run_graph_workflow(graph_state_request: GraphStateRequest):
    """Führt den LangGraph-Workflow direkt mit GraphState aus"""
    try:
        # GraphState aus Request erstellen
        graph_state: GraphState = {
            "leads_ids": graph_state_request.leads_ids,
            "leads_data": graph_state_request.leads_data,
            "current_lead": LeadData(**graph_state_request.current_lead),
            "company_data": CompanyData(**graph_state_request.company_data),
            "reports": [{"title": r.get("title", ""), "content": r.get("content", ""), "is_markdown": r.get("is_markdown", False)} for r in graph_state_request.reports],
            "reports_folder_link": graph_state_request.reports_folder_link,
            "custom_outreach_report_link": graph_state_request.custom_outreach_report_link,
            "personalized_email": graph_state_request.personalized_email,
            "interview_script": graph_state_request.interview_script,
            "number_leads": graph_state_request.number_leads
        }
        
        print(f"🚀 Starte Graph-Workflow für: {graph_state['current_lead'].name} bei {graph_state['company_data'].name}")
        
        # LangGraph Workflow ausführen
        final_state = automation.run_workflow(graph_state)
        
        # Ergebnisse extrahieren
        reports = final_state.get('reports', [])
        
        # Reports in serializable Format konvertieren
        serializable_reports = []
        for report in reports:
            if hasattr(report, 'model_dump'):  # Pydantic model
                serializable_reports.append(report.model_dump())
            elif hasattr(report, 'dict'):  # Pydantic model (old version)
                serializable_reports.append(report.dict())
            elif isinstance(report, dict):  # Already a dict
                serializable_reports.append(report)
            else:
                # Fallback for other types
                serializable_reports.append({
                    "title": str(getattr(report, 'title', 'Unnamed Report')),
                    "content": str(getattr(report, 'content', 'No content')),
                    "is_markdown": bool(getattr(report, 'is_markdown', False))
                })
        
        print(f"✅ Graph-Workflow abgeschlossen. {len(serializable_reports)} Berichte generiert.")
        
        # Strukturierte Daten aus Reports extrahieren
        extracted_data = extract_structured_data_from_reports(serializable_reports)
        print(f"📊 Extrahierte Daten: {extracted_data}")
        
        return GraphResult(
            success=True,
            reports=serializable_reports,
            extracted_data=extracted_data
        )
        
    except Exception as e:
        error_msg = f"Fehler beim Ausführen des Graph-Workflows: {str(e)}"
        print(f"❌ {error_msg}")
        return GraphResult(
            success=False,
            reports=[],
            error=error_msg
        )


@app.post("/leads/batch-process", response_model=APIResponse)
async def batch_process_leads(background_tasks: BackgroundTasks, lead_ids: List[int] = None):
    """Mehrere Leads gleichzeitig verarbeiten"""
    if not lead_ids:
        lead_ids = [l.id for l in leads_db if l.status == 'new']
    
    if not lead_ids:
        return APIResponse(
            success=False,
            message="Keine Leads zum Verarbeiten gefunden"
        )
    
    # Alle Leads auf processing setzen
    for lead_id in lead_ids:
        lead = next((l for l in leads_db if l.id == lead_id), None)
        if lead:
            lead.status = 'processing'
            lead.updated_at = datetime.now().isoformat()
    
    async def run_batch_automation():
        for lead_id in lead_ids:
            lead = next((l for l in leads_db if l.id == lead_id), None)
            if lead:
                result = await process_lead_with_automation(lead)
                print(f"✅ Batch-Automation abgeschlossen für Lead {lead_id}: {result}")
    
    background_tasks.add_task(run_batch_automation)
    
    return APIResponse(
        success=True,
        message=f"Batch-Processing für {len(lead_ids)} Leads gestartet",
        data={"lead_ids": lead_ids, "status": "processing"}
    )


# Startup Events
@app.on_event("startup")
async def startup_event():
    """Initialisierung beim Server-Start"""
    print("🚀 Lead Agent API startet...")
    print("📊 Initialisiere Mock-Leads...")
    initialize_mock_leads()
    print(f"✅ {len(leads_db)} Mock-Leads geladen")
    print("🔗 LangGraph Automation bereit")
    print("✅ API Server bereit auf http://localhost:8000")


if __name__ == "__main__":
    # Development Server starten
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
