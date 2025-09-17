from typing import Callable, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import GraphState, LeadData, CompanyData
from .nodes import OutReachAutomationNodes

def node_merge_reports(state: GraphState) -> Dict[str, Any]:
    """Führt die Ergebnisse der vorigen Knoten deterministisch zusammen"""
    reports = state.get("reports", [])
    return {
        "reports": reports,  # Reports wurden bereits akkumuliert
        "workflow_completed": True
    }

class OutReachAutomation:
    def __init__(self):
        # Initialize the automation workflow by building the graph
        self.app = self.build_graph()

    def build_graph(self):
        """
        Constructs the state graph for the outreach automation workflow.
        """
        # StateGraph erstellen
        graph = StateGraph(GraphState)

        # Knoten registrieren - direkt die statischen Methoden verwenden
        graph.add_node("unternehmensinformationen", OutReachAutomationNodes.pillar_unternehmensinformationen)
        graph.add_node("finanzen", OutReachAutomationNodes.pillar_finanzen)
        graph.add_node("linkedin", OutReachAutomationNodes.pillar_linkedin)
        graph.add_node("news", OutReachAutomationNodes.pillar_news)
        graph.add_node("merge", node_merge_reports)
        graph.add_node("unternehmensinformationen_s_m", OutReachAutomationNodes.pillar_unternehmensinformationen_services_materials)
        
        # Einstiegspunkt setzen
        graph.set_entry_point("unternehmensinformationen")

        # Deterministische Kanten
        # Unternehmensinformationen -> Finanzen -> LinkedIn -> News -> Merge -> END
        graph.add_edge("unternehmensinformationen", "unternehmensinformationen_s_m")
        graph.add_edge("unternehmensinformationen_s_m", "merge")
        # graph.add_edge("linkedin", "news")
        # graph.add_edge("news", "merge")
        graph.add_edge("merge", END)

        # App kompilieren (ohne Checkpointer für deterministischen Workflow)
        return graph.compile()

    def run_workflow(self, initial_state: GraphState) -> GraphState:
        """
        Führt den LangGraph-Workflow deterministisch aus und gibt den finalen State zurück.
        """
        # LangGraph akkumuliert bereits automatisch die Reports (wegen Annotated[list[Report], add])
        # Wir brauchen nur das fin^ ale Ergebnis
        final_state = None
        for event in self.app.stream(initial_state):
            # Das letzte Event enthält den finalen State
            final_state = event
            
        # Das letzte Event sollte vom "merge"-Knoten kommen
        if final_state and "merge" in final_state:
            return final_state["merge"]
        
        # Fallback: letzten verfügbaren State zurückgeben
        return final_state.get(list(final_state.keys())[-1], initial_state) if final_state else initial_state


# # Mock-Datensatz für Tests
# def create_mock_data() -> GraphState:
#     """Erstellt Mock-Daten für das Kundenprofil"""
#     mock_lead = LeadData(
#         id="LEAD-001",
#         name="Armin Ibrahimovic",
#         address="70771 Stuttgart",
#         email="armin.ibrahimovic@capgemini.de",
#         phone="+49 30 12345678",
#         profile=""
#     )
    
#     mock_company = CompanyData(
#         name="Capgemini",
#         profile="Consulting",
#         website=""
#     )
    
#     initial_state: GraphState = {
#         "leads_ids": ["LEAD-001"],
#         "leads_data": [mock_lead.model_dump()],
#         "current_lead": mock_lead,
#         "company_data": mock_company,
#         "reports": [],
#         "reports_folder_link": "",
#         "custom_outreach_report_link": "",
#         "personalized_email": "",
#         "interview_script": "",
#         "number_leads": 1
#     }
    
#     return initial_state

# # Test-Runner
# def test_workflow():
#     """Testet den Workflow mit Mock-Daten"""
#     print("🚀 Starte Test mit Mock-Daten...")
    
#     # Mock-Daten erstellen
#     initial_state = create_mock_data()
    
#     print(f"📊 Test-Lead: {initial_state['current_lead'].name}")
#     print(f"🏢 Test-Unternehmen: {initial_state['company_data'].name}")
#     print(f"📍 PLZ: 10115 (aus Adresse extrahiert)")
#     print(f"📧 Email: {initial_state['current_lead'].email}")
#     print("-" * 50)
    
#     # Workflow ausführen
#     automation = OutReachAutomation()
#     final_state = automation.run_workflow(initial_state)
    
#     # Ergebnisse anzeigen
#     print("✅ Workflow abgeschlossen!")
#     print(f"📋 Reports erstellt: {len(final_state.get('reports', []))}")
    
#     for i, report in enumerate(final_state.get('reports', []), 1):
#         print(f"\n📊 Report {i}: {report.title}")
#         content = report.content
#         print(content)
    
#     return final_state


# if __name__ == "__main__":
#     # Test ausführen
#     test_workflow()
