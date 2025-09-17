import os
import requests
import re 
import json
from dotenv import load_dotenv
from typing_extensions import TypedDict
from typing import Dict, Any
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from markdownify import markdownify as md
load_dotenv()
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# --- Initialisierung (Annahme) ---
openai_api_key = os.environ.get("OPENAI_API_KEY")
serper_api_key = os.environ.get("SERPER_API_KEY")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

# Markdown-Tool optional einbinden
try:
    from .markdown_scrape_tool import scrape_website_to_markdown
except Exception:
    try:
        from tools.markdown_scrape_tool import scrape_website_to_markdown
    except Exception:
        scrape_website_to_markdown = None  # type: ignore

# --- State Definition (Annahme) ---
class ToolState(TypedDict):
    messages: str

@tool
def wlw_scrape_tool(query: str) -> str:
    """WLW Scrape Tool: Verwende dieses Tool immer dann, wenn du die Mitarbeiteranzahl, den Lieferantentyp (Fertigungsunternehmen oder Händler?) und die Materialien (Welche Materialien werden verarbeitet?) eines Unternehmens scrapen willst. Verwende dieses Tool nur EINMALIG!"""
    
    # Validierung der Eingabe
    if not query or not query.strip():
        return "Fehler: Leere Suchanfrage erhalten"

def create_http_session() -> requests.Session:
    """Erstellt eine Session mit realistischen Headers und Retries für zuverlässiges HTML-Fetching."""
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
    }
    session.headers.update(headers)

    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def convert_html_to_markdown(html_content: str) -> str:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')  # optional: 'lxml' wenn verfügbar
        for script in soup(["script", "style"]):
            script.decompose()
        cleaned_html = str(soup)

        markdown_content = md(
            cleaned_html,
            heading_style="ATX"
            # keine convert-Whitelist, kein escape_misc
        )

        # Zero-loss: Markdown + bereinigtes Roh-HTML anhängen
        return f"{markdown_content}\n\n<!-- RAW_HTML -->\n{cleaned_html}"
    except Exception as e:
        print(f"Fehler bei HTML-zu-Markdown-Konvertierung: {e}")
        return html_content

def extract_structured_html_content(soup: BeautifulSoup, url: str) -> Dict[str, any]:
    """
    Extrahiert strukturierte Daten aus WLW HTML-Seiten basierend auf spezifischen CSS-Selektoren.
    
    Args:
        soup: BeautifulSoup-Objekt der HTML-Seite
        url: Die URL der Seite für Logging-Zwecke
        
    Returns:
        Dict mit extrahierten strukturierten Daten
    """
    extracted_data = {
        "url": url,
        "company_name": "",
        "employee_count": "",
        "supplier_type": "",
        "founding_year": "",
        "distribution_area": "",
        "address": "",
        "country": "",
        "description": ""
    }
    
    try:
        # Unternehmensname extrahieren
        company_name_elem = soup.select_one('.company-name, [data-test="company-name"]')
        if company_name_elem:
            extracted_data["company_name"] = company_name_elem.get_text(strip=True)
        
        # Mitarbeiteranzahl extrahieren
        employee_elem = soup.select_one('[data-test="employee-count"]')
        if employee_elem:
            employee_text = employee_elem.get_text(strip=True)
            # Extrahiere nur die Zahl aus "Mitarbeiter: 20-49"
            if "Mitarbeiter:" in employee_text:
                extracted_data["employee_count"] = employee_text.split("Mitarbeiter:")[-1].strip()
        
        # Lieferantentyp extrahieren
        supplier_type_elem = soup.select_one('[data-test="supplier-types"] .supplier-type span')
        if supplier_type_elem:
            extracted_data["supplier_type"] = supplier_type_elem.get_text(strip=True)
        
        # Gründungsjahr extrahieren
        founding_elem = soup.select_one('[data-test="founding-year"]')
        if founding_elem:
            founding_text = founding_elem.get_text(strip=True)
            if "Gegründet:" in founding_text:
                extracted_data["founding_year"] = founding_text.split("Gegründet:")[-1].strip()
        
        # Liefergebiet extrahieren
        distribution_elem = soup.select_one('[data-test="distribution-area"]')
        if distribution_elem:
            distribution_text = distribution_elem.get_text(strip=True)
            if "Lieferung:" in distribution_text:
                extracted_data["distribution_area"] = distribution_text.split("Lieferung:")[-1].strip()
        
        # Adresse extrahieren
        address_elem = soup.select_one('.company-address')
        if address_elem:
            extracted_data["address"] = address_elem.get_text(strip=True)
        
        # Land extrahieren
        country_elem = soup.select_one('.company-address').find_next_sibling()
        if country_elem:
            country_text = country_elem.get_text(strip=True)
            if country_text and not country_text.startswith("Deutschland"):
                extracted_data["country"] = country_text
        
        # Beschreibung extrahieren
        description_elem = soup.select_one('.description, [data-test="description"] .description')
        if description_elem:
            extracted_data["description"] = description_elem.get_text(strip=True)
        
        # Keine Keyword-basierte Extraktion - das macht später ein LLM
        
        print(f"WLW-Daten extrahiert für {url}:")
        print(f"  - Unternehmen: {extracted_data['company_name']}")
        print(f"  - Mitarbeiter: {extracted_data['employee_count']}")
        print(f"  - Lieferantentyp: {extracted_data['supplier_type']}")
            
    except Exception as e:
        print(f"Fehler bei der strukturierten HTML-Extraktion für {url}: {e}")
        extracted_data["error"] = str(e)
    
    return extracted_data

def format_wlw_data_to_markdown(structured_data: Dict[str, any]) -> str:
    """
    Formatiert die extrahierten WLW-Daten in Markdown-Format.
    
    Args:
        structured_data: Dictionary mit den extrahierten WLW-Daten
        
    Returns:
        str: Formatierte Markdown-Ausgabe
    """
    if "error" in structured_data:
        return f"Fehler: {structured_data['error']}"
    
    result = f"## WLW Profil: {structured_data['url']}\n\n"
    
    if structured_data['company_name']:
        result += f"**Unternehmen:** {structured_data['company_name']}\n"
    
    if structured_data['employee_count']:
        result += f"**Mitarbeiteranzahl:** {structured_data['employee_count']}\n"
    
    if structured_data['supplier_type']:
        result += f"**Lieferantentyp:** {structured_data['supplier_type']}\n"
    
    if structured_data['founding_year']:
        result += f"**Gegründet:** {structured_data['founding_year']}\n"
    
    if structured_data['distribution_area']:
        result += f"**Liefergebiet:** {structured_data['distribution_area']}\n"
    
    if structured_data['address']:
        result += f"**Adresse:** {structured_data['address']}\n"
    
    if structured_data['country']:
        result += f"**Land:** {structured_data['country']}\n"
    
    if structured_data['description']:
        result += f"\n**Beschreibung:**\n{structured_data['description']}\n"
    
    return result

@tool
def wlw_scrape_tool(query: str) -> str:
    """WLW Scrape Tool: Verwende dieses Tool immer dann, wenn du die Mitarbeiteranzahl, den Lieferantentyp (Fertigungsunternehmen oder Händler?) und die Materialien (Welche Materialien werden verarbeitet?) eines Unternehmens scrapen willst. Verwende dieses Tool nur EINMALIG!"""
    
    # Validierung der Eingabe
    if not query or not query.strip():
        return "Fehler: Leere Suchanfrage erhalten"

    # --- LLM Chains Definieren --- #
    def get_wlw_profil(state: ToolState) -> AIMessage:
        """Dieser Agent ist dafür verantwortlich, den richtigen WLW Link auszuwählen."""

        system_prompt = SystemMessage(content=f"""Du bist ein Experte darin, aus einer Liste von Suchergebnissen das korrekte WLW-Profil (Wer-liefer-Was Profil) eines Unternehmens zu identifizieren.
Deine Aufgabe ist es, die untenstehenden Suchergebnisse zu analysieren und das relevanteste WLW-Profil auszuwählen.
- Fokussiere dich ausschließlich auf das Unternehmen: **{query}**. Ignoriere Einträge von anderen Unternehmen.
- Wenn das Unternehmen aus dem 'title', dem 'link' und dem 'snippet' aus der Google Suche zum gesuchten Unternehmen: **{query}** passt, kannst du diesen Link auswählen.
- Gib als Ergebnis **nur die URL** aus, sonst nichts.

Beispiel-Ausgabe:
https://www.wlw.de/de/firma/dfw-kunststoff-und-anlagenbau-gmbh-1483147 

Wenn unter den Ergebnissen kein passendes Profil zu finden ist, antworte mit: "Kein passendes WLW Profil in den Suchergebnissen gefunden."
        
**Zielunternehmen:** {query}""")

        print(f"[DEBUG] analyze_wlw_results.company: {query}")
        print("--- SYSTEM PROMPT (mit Company) ---")
        print(system_prompt.content)
        print("------------------------------------")
        
        user_prompt = HumanMessage(content=state["messages"])
        llm_response = llm.invoke([system_prompt, user_prompt])
        
        return llm_response

    # === GEÄNDERTE SUCH ANFRAGE ===
    # Schritt 1: Verbessern Sie die Suchanfrage
    search_query = f"site:wlw.de {query}"
    print(f"Angepasste Suchanfrage für die API: {search_query}")

    try:
        # Serper API erwartet POST mit JSON-Payload
        payload = {
            "q": search_query,
            "location": "Germany",
            "gl": "de",
            "hl": "de",
            "num": 5
        }
        
        response = requests.post(
            "https://google.serper.dev/search",
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": f"{serper_api_key}",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        print("Google Search erfolgreich")
    except Exception as e:
        return f"Fehler bei der Google-Suche: {e}"

    # +++++++++ HIER BEGINNT DIE KORREKTE IMPLEMENTIERUNG +++++++++
    formatted_user_prompt = f"Hinweis (Unternehmen): {query}\n\n--- Suchergebnisse ---\n\n"

    # KORREKTUR: Serper API verwendet 'organic' (nicht 'organic_results')
    if 'organic' in data and data['organic']:
        for i, result in enumerate(data['organic']):
            title = result.get('title', 'Kein Titel')
            link = result.get('link', 'Kein Link')
            snippet = result.get('snippet', 'Kein Snippet')
            
            formatted_user_prompt += f"{i + 1}. Suchergebnis:\n"
            formatted_user_prompt += f"  - Title: {title}\n"
            formatted_user_prompt += f"  - Link: {link}\n"
            formatted_user_prompt += f"  - Snippet: {snippet}\n\n"
    else:
        formatted_user_prompt += "Es wurden keine WLW Suchergebnisse gefunden."
        
    # ZUR KONTROLLE: Unbedingt die Ausgabe prüfen!
    print("--- PROMPT FÜR DAS LLM ---")
    print(formatted_user_prompt)
    print("--------------------------")

    # --- Rufe die LLM Chain auf --- #
    try:
        wlw_profil_response = get_wlw_profil(ToolState(messages=formatted_user_prompt))
        found_profile_info = wlw_profil_response.content
        print(f"Gefundene Profil-Info: {found_profile_info}")

        # Extrahiere die erste URL aus der LLM-Antwort
        url_match = re.search(r"https?://[^\s]+", found_profile_info)
        profile_url = url_match.group(0) if url_match else None

        # Falls eine URL gefunden wurde: scrape und HTML-Daten extrahieren
        if profile_url:
            try:
                # Erstelle HTTP-Session für das Scraping
                session = create_http_session()
                response = session.get(profile_url, timeout=30)
                response.raise_for_status()
                
                # Parse HTML mit BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extrahiere strukturierte HTML-Daten
                structured_data = extract_structured_html_content(soup, profile_url)
                
                # Gib die rohen HTML-Daten zurück (ohne Markdown-Formatierung)
                return structured_data
                
            except Exception as scrape_err:
                print(f"Scraping fehlgeschlagen für {profile_url}: {scrape_err}")
                return {"error": f"Scraping fehlgeschlagen für {profile_url}: {scrape_err}"}
        
        # Fallback: bisheriges Verhalten (nur die Profil-Info ausgeben)
        return found_profile_info
        
    except Exception as e:
        print(f"Agent 'get_wlw_profil' fehlgeschlagen: {e}")
        return f"Fehler im LLM-Agenten: {e}"