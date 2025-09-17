from colorama import Fore, Style
from dotenv import load_dotenv

load_dotenv()

from .tools.linkedin_scrape_tool import linkedin_scrape_tool
from .tools.google_search_tool_serper import google_search_tool
from .tools.finance_scrape_tool import finance_scrape_tool
from .tools.website_scraper import company_website_scraper as website_scraper
from .tools.markdown_scrape_tool import scrape_website_to_markdown
from .tools.wlw_scrape_tool import wlw_scrape_tool
from .state import LeadData, CompanyData, Report, GraphInputState, GraphState
from .structured_outputs import WebsiteData, EmailResponse
from .utils import invoke_llm, get_report, get_current_date, save_reports_locally
import os
import re
import time
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage


# Research-Prompts
from .prompts.research_prompts import (
    research_prompt_unternehmensidentifikation,
    research_prompt_finanzen,
    research_prompt_lead,
    research_prompt_news_wo_tools,
    query_writer_prompt,
)

# Enable or disable sending emails directly using GMAIL
# Should be confident about the quality of the email
SEND_EMAIL_DIRECTLY = False
# Enable or disable saving emails to Google Docs
# By defauly all reports are save locally in `reports` folder
SAVE_TO_GOOGLE_DOCS = False

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

class OutReachAutomationNodes:
    
    def __init__(self, loader=None):
        self.lead_loader = loader
        self.docs_manager = GoogleDocsManager()
        self.drive_folder_name = ""

    @staticmethod
    def pillar_unternehmensinformationen(state: GraphState):
        print(Fore.YELLOW + "----- Säule: Unternehmensinformationen (Website Scraper) -----\n" + Style.RESET_ALL)
        company_name = state.get("company_data", CompanyData()).name
        plz = _regex_extract_plz(state.get("current_lead").address if state.get("current_lead") else "")
        if not (company_name and plz):
            raise ValueError("Fehlende Daten: Firmenname und Postleitzahl benötigt für Unternehmensinformationen.")

        query = f"{company_name} AND {plz}"
        tool_output = ""
        if website_scraper:
            try:
                res = website_scraper(query)
                tool_output = getattr(res, "content", str(res))
            except Exception as e:
                tool_output = f"Website-Scraper Fehler: {e}"
        else:
            tool_output = "Website-Scraper nicht verfügbar."

        target_information_1 = "Das Ziel der Recherche ist es, die relevanten Target-Informationen zu sammeln.\n Target-Information: Mitarbeiteranzahl, Branche, Unternehmensart (Fertigungsunternehmen oder Händler?)"
        target_information_2 = "Das Ziel der Recherche ist es, die relevanten Target-Informationen zu sammeln.\n Target-Information: Dienstleistungen / Produkte, Materialien (Welche Materialien werden verarbeitet?)"

        mission_prompt_1 = f"Rechercheergebnisse: {tool_output} \n Mission Prompt: {target_information_1} "
        mission_prompt_2 = f"Rechercheergebnisse: {tool_output} \n Mission Prompt: {target_information_2} "

        llm_output_1 = invoke_llm(
            system_prompt=research_prompt_unternehmensidentifikation,
            user_message=mission_prompt_1,
            model="gpt-4o-mini",
            llm_provider="openai-agent",
        )

        print(f"Finaler Report Unternehmensinformationen_1: {llm_output_1}")
        report_1 = Report(title="Unternehmensinformationen_1", content=llm_output_1, is_markdown=True)

        llm_output_2 = invoke_llm(
            system_prompt=research_prompt_unternehmensidentifikation,
            user_message=mission_prompt_2,
            model="gpt-4o-mini",
            llm_provider="openai-agent",
        )

        print(f"Finaler Report Unternehmensinformationen_2: {llm_output_2}")
        report_2 = Report(title="Unternehmensinformationen_2", content=llm_output_2, is_markdown=True)
        return {"reports": [report_1, report_2], "sektion_unternehmensinformationen": [llm_output_1, llm_output_2]}

    @staticmethod
    def pillar_unternehmensinformationen_services_materials(state: GraphState):
        print(Fore.YELLOW + "----- Säule: Unternehmensinformationen (Website Scraper) -----\n" + Style.RESET_ALL)
        company_name = state.get("company_data", CompanyData()).name
        plz = _regex_extract_plz(state.get("current_lead").address if state.get("current_lead") else "")
        if not (company_name and plz):
            raise ValueError("Fehlende Daten: Firmenname und Postleitzahl benötigt für Unternehmensinformationen.")

        query = f"{company_name} AND {plz}"
        tool_output = ""
        if wlw_scrape_tool:
            try:
                res = wlw_scrape_tool(query)
                tool_output = getattr(res, "content", str(res))
            except Exception as e:
                tool_output = f"WLW-Scraper Fehler: {e}"
        else:
            tool_output = "WLW-Scraper nicht verfügbar."

        target_information_1 = "Das Ziel der Recherche ist es, die relevanten Target-Informationen zu sammeln.\n Target-Information: Dienstleistungen / Produkte, Materialien (Welche Materialien werden verarbeitet?)"
        target_information_2 = "Das Ziel der Recherche ist es, die relevanten Target-Informationen zu sammeln.\n Target-Information: Mitarbeiteranzahl, Branche, Unternehmensart (Fertigungsunternehmen oder Händler?)"

        mission_prompt_1 = f"Rechercheergebnisse: {tool_output} \n Mission Prompt: {target_information_1} "
        mission_prompt_2 = f"Rechercheergebnisse: {tool_output} \n Mission Prompt: {target_information_2} "

        llm_output_1 = invoke_llm(
            system_prompt=research_prompt_unternehmensidentifikation,
            user_message=mission_prompt_1,
            model="gpt-4o-mini",
            llm_provider="openai-agent",
        )

        llm_output_2 = invoke_llm(
            system_prompt=research_prompt_unternehmensidentifikation,
            user_message=mission_prompt_2,
            model="gpt-4o-mini",
            llm_provider="openai-agent",
        )

        print(f"Finaler Report Unternehmensinformationen_services_materials: {llm_output_1}")
        report_1 = Report(title="Unternehmensinformationen_services_materials_1", content=llm_output_1, is_markdown=True)

        print(f"Finaler Report Unternehmensinformationen_services_materials: {llm_output_2}")
        report_2 = Report(title="Unternehmensinformationen_services_materials_2", content=llm_output_2, is_markdown=True)
        return {"reports": [report_1, report_2], "sektion_unternehmensinformationen_services_materials": [llm_output_1, llm_output_2]}

    @staticmethod
    def pillar_finanzen(state: GraphState):
        print(Fore.YELLOW + "----- Säule: Finanzen -----\n" + Style.RESET_ALL)
        # Rate-Limiting: Warte 2 Sekunden vor dem nächsten API-Aufruf
        print("⏳ Warte 2 Sekunden für Rate-Limiting...")
        time.sleep(2)
        
        company_name = state.get("company_data", CompanyData()).name
        plz = _regex_extract_plz(state.get("current_lead").address if state.get("current_lead") else "")
        if not (company_name and plz):
            raise ValueError("Fehlende Daten: Firmenname und Postleitzahl benötigt für Finanzen.")

        query = f"{company_name} AND {plz}"
        tool_output = ""
        if finance_scrape_tool:
            try:
                res = finance_scrape_tool(query)
                tool_output = getattr(res, "content", str(res))
            except Exception as e:
                tool_output = f"Finance-Tool Fehler: {e}"
        else:
            tool_output = "Finance-Tool nicht verfügbar."

        finanzen_kennzahlen = """Die Mission der Recherche ist es, die relevanten Finanziellen Kennzahlen zu sammeln.
        Finanzielle Kennzahlen: Umsatz"""

        mission_prompt = f"Rechercheergebnisse: {tool_output} \n Mission Prompt: {finanzen_kennzahlen} "

        llm_output = invoke_llm(
            system_prompt=research_prompt_finanzen,
            user_message=mission_prompt,
            model="gpt-4o-mini",
            llm_provider="openai-agent",
        )
        print(f"Finaler Report Finanzen: {llm_output}")
        report = Report(title="Finanzen", content=llm_output, is_markdown=True)
        return {"reports": [report], "sektion_finanzen": llm_output}

    @staticmethod
    def pillar_linkedin(state: GraphState):
        print(Fore.YELLOW + "----- Säule: LinkedIn (LinkedIn Scraper) -----\n" + Style.RESET_ALL)
        # Rate-Limiting: Warte 2 Sekunden vor dem nächsten API-Aufruf
        print("⏳ Warte 2 Sekunden für Rate-Limiting...")
        time.sleep(2)
        
        lead_name = state.get("current_lead").name if state.get("current_lead") else ""
        company_name = state.get("company_data", CompanyData()).name
        plz = _regex_extract_plz(state.get("current_lead").address if state.get("current_lead") else "")
        if not (lead_name and plz):
            raise ValueError("Fehlende Daten: Lead-Name und Postleitzahl benötigt für LinkedIn.")

        if company_name:
            query = f"site:linkedin.com ({lead_name} AND {plz} OR {company_name})"
        else:
            query = f"{lead_name} AND {plz}"

        tool_output = ""
        if linkedin_scrape_tool:
            try:
                res = linkedin_scrape_tool.invoke({"query": query})
                tool_output = str(res)
            except Exception as e:
                tool_output = f"LinkedIn-Tool Fehler: {e}"
        else:
            tool_output = "LinkedIn-Tool nicht verfügbar."

        llm_output = invoke_llm(
            system_prompt=research_prompt_lead,
            user_message=tool_output,
            model="gpt-4.1-mini",
            llm_provider="openai",
        )
        print(f"Finaler Report LinkedIn: {llm_output}")
        report = Report(title="LinkedIn", content=llm_output, is_markdown=True)
        return {"reports": [report], "sektion_linkedin": llm_output}

    @staticmethod
    def pillar_news(state: GraphState):
        print(Fore.YELLOW + "----- Säule: News -----\n" + Style.RESET_ALL)
        # 1. Extrahiere Unternehmensnamen und Postleitzahl
        company_name = state.get("company_data", CompanyData()).name
        plz = _regex_extract_plz(state.get("current_lead").address if state.get("current_lead") else "")
        if not (company_name and plz):
            raise ValueError("Fehlende Daten: Firmenname und Postleitzahl benötigt für News.")

        # 2. Query Writer LLM: Erstelle 3 Suchanfragen
        company_input = f"Unternehmensname: {company_name}\nPostleitzahl: {plz}\n"
        mission_input = f"""Mission der Recherche: Die Mission der Recherche ist es, aktuelle Nachrichten über das Unternehmen {company_name} zu identifizieren und gezielt auffindbar zu machen.
Im Fokus stehen dabei insbesondere folgende Nachrichtenthemen:

- Veränderungen im Management oder Geschäftsführerwechsel
- Strategische Investitionen
- Kooperationen und Partnerschaften
- Akquisitionen und Unternehmensübernahmen"""

        mission_prompt = f"{company_input}\n{mission_input}"

        print(f"Query Writer Input:\n {mission_prompt}")
        
        query_writer_output = invoke_llm(
            system_prompt=query_writer_prompt,
            user_message=mission_prompt,
            model="gpt-4o-mini",
            llm_provider="openai",
        )
        
        # Parse die 3 Suchanfragen aus der LLM-Antwort
        suchanfragen = [line.strip() for line in query_writer_output.strip().split('\n') if line.strip()][:3]
        print(f"Generierte Suchanfragen: {suchanfragen}")

        # 3. Führe alle 3 Suchanfragen durch das Google Search Tool aus
        tool_output = ""
        if google_search_tool and suchanfragen:
            search_results = []
            for i, query in enumerate(suchanfragen, 1):
                try:
                    print(f"Führe Suchanfrage {i} aus: {query}")
                    res = google_search_tool.invoke({"query": query, "mission_prompt": mission_prompt})
                    search_results.append(f"=== Suchergebnisse {i} ===\n{str(res)}")
                except Exception as e:
                    search_results.append(f"=== Suchanfrage {i} - Fehler ===\n{e}")
            
            tool_output = "\n\n".join(search_results)
        else:
            tool_output = "Google-Search-Tool nicht verfügbar oder keine Suchanfragen generiert."

        # 4. Verarbeite die Ergebnisse mit dem LLM
        llm_output = invoke_llm(
            system_prompt=research_prompt_news_wo_tools,
            user_message=tool_output,
            model="gpt-4o-mini",
            llm_provider="openai",
        )
        report = Report(title="News", content=llm_output, is_markdown=True)
        return {"reports": [report], "sektion_news": llm_output}

    def run_deterministic_workflow(self, state: GraphState):
        print(Fore.YELLOW + "===== Starte deterministischen Outreach-Workflow =====\n" + Style.RESET_ALL)
        reports: List[Report] = []

        # 1) Unternehmensinformationen
        r1 = self.pillar_unternehmensinformationen(state)
        reports.extend(r1.get("reports", []))

        # 2) Finanzen
        r2 = self.pillar_finanzen(state)
        reports.extend(r2.get("reports", []))

        # 3) Unternehmensinformationen_services_materials
        r3 = self.pillar_unternehmensinformationen_services_materials(state)
        reports.extend(r3.get("reports", []))

        # 4) Unternehmensinformationen_services_materials
        r4 = self.pillar_unternehmensinformationen_services_materials(state)
        reports.extend(r4.get("reports", []))

        # 5) Unternehmensinformationen_services_materials
        r5 = self.pillar_unternehmensinformationen_services_materials(state)
        reports.extend(r4.get("reports", []))

        # 6) LinkedIn
        r6 = self.pillar_linkedin(state)
        reports.extend(r3.get("reports", []))

        # 7) News
        r7 = self.pillar_news(state)
        reports.extend(r4.get("reports", []))

        # Ergebnisse in State zusammenführen (DB-Anbindung später)
        updated_state = {
            "reports": reports,
            "unternehmensinformationen": r1.get("sektion_unternehmensinformationen", ""),
            "finanzen": r2.get("sektion_finanzen", ""),
            "linkedin": r3.get("sektion_linkedin", ""),
            "news": r4.get("sektion_news", ""),
        }
        return updated_state
    

def _regex_extract_plz(address: str) -> str:
    """
    Extrahiert die Postleitzahl aus einer Adresse mittels RegEx.
    Deutsche PLZ: 5 Ziffern
    """
    import re
    if not address:
        return ""
    
    # RegEx für deutsche PLZ (5 Ziffern)
    plz_match = re.search(r'\b(\d{5})\b', address)
    if plz_match:
        return plz_match.group(1)
    
    return ""
    