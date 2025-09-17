import re
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from typing_extensions import TypedDict
from typing import List, Dict
import requests
import os
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse

load_dotenv()

openai_api_key = os.environ.get("OPENAI_API_KEY")
google_api_key = os.environ.get("GOOGLESEARCH_API_KEY")
serper_api_key = os.environ.get("SERPER_API_KEY")

llm = ChatOpenAI(api_key=openai_api_key, model="gpt-4o-mini", temperature=0.1)

# Markdown-Tool primär nutzen, falls verfügbar
try:
    from .markdown_scrape_tool import scrape_website_to_markdown
except Exception:
    try:
        from tools.markdown_scrape_tool import scrape_website_to_markdown
    except Exception:
        scrape_website_to_markdown = None  # type: ignore

class ToolState(TypedDict):
    messages: str


def extract_and_format_links(text: str) -> List[Dict[str, str]]:
    """
    Extrahiert alle URLs aus einem Text-String und formatiert sie als Liste von Dictionaries.
    
    Args:
        text: Der Input-String, der nach Links durchsucht werden soll.
        
    Returns:
        Eine Liste von Dictionaries, wobei jedes Dictionary einen "url"-Schlüssel
        und die gefundene URL als Wert hat.
    """
    # Leere Liste zurückgeben, wenn Input kein String ist
    if not isinstance(text, str):
        return []

    # Robuster Regex: bis zum Zeilenende (inkl. Leerzeichen/Kommas), nicht nur bis zum ersten Space
    url_pattern = r"https?:\/\/[^\n\r]+"
    
    # Alle Matches im Input-Text finden
    raw_urls = re.findall(url_pattern, text, re.IGNORECASE)

    formatted_output: List[Dict[str, str]] = []
    for raw in raw_urls:
        # Trimme häufige Wrapper/Abschlüsse und Whitespace
        cleaned = raw.strip().strip('\'"<>').rstrip('.,;:)')
        # Percent-Encode ungültige Zeichen (Spaces, Kommas, Umlaute etc.)
        try:
            normalized = requests.utils.requote_uri(cleaned)
        except Exception:
            normalized = cleaned
        formatted_output.append({"url": normalized})
    
    return formatted_output

# Entferne die redundanten Funktionen extract_links und process_extracted_urls
# da wir jetzt extract_and_format_links verwenden


# --- Debug-Helfer ---
DEBUG_SNIPPET_CHARS = int(os.environ.get("DEBUG_SNIPPET_CHARS", "1000"))
MAX_LLM_INPUT_CHARS = int(os.environ.get("MAX_LLM_INPUT_CHARS", "120000"))


def debug_print_snippet(label: str, text: str, max_chars: int = 1200) -> None:
    try:
        length = len(text) if isinstance(text, str) else 0
        print(f"\n--- DEBUG {label}: length={length} chars ---")
        if length:
            print(text[:max_chars])
            if length > max_chars:
                print(f"... [truncated {length - max_chars} chars]")
        print(f"--- END DEBUG {label} ---\n")
    except Exception as e:
        print(f"[DEBUG] Fehler beim Debug-Print für {label}: {e}")


def trim_for_llm(text: str, max_chars: int = MAX_LLM_INPUT_CHARS) -> str:
    try:
        if not isinstance(text, str):
            return ""
        if len(text) <= max_chars:
            return text
        trimmed = text[:max_chars]
        removed = len(text) - max_chars
        return f"{trimmed}\n\n[Hinweis: Inhalt gekürzt, {removed} Zeichen entfernt]"
    except Exception:
        return text


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


def analyze_northdata_results(formatted_user_prompt: str, company: str) -> str:
    """
    Separate Node/Funktion für die LLM-Analyse der Northdata-Suchergebnisse.
    
    Args:
        formatted_user_prompt: Der formatierte Prompt mit den Suchergebnissen
        
    Returns:
        str: Die LLM-Antwort (URL oder "Keine passenden...")
    """
    system_prompt = SystemMessage(content=f"""Du bist ein KI-gestützter Experte für Suchanalysen. Deine Aufgabe ist es, in den folgenden Google-Suchergebnissen die exakte NorthData URL für das Unternehmen '{company}' zu finden.

**Anweisungen:**
1.  Fokussiere dich ausschließlich auf das Unternehmen: **{company}**. Ignoriere NorthData Einträge von anderen Unternehmen.
2.  Analysiere Titel, URL und Snippet jedes Suchergebnisses. Wähle die URL, die am wahrscheinlichsten zum Hauptprofil des Unternehmens '{company}' auf NorthData führt.
3.  Wenn es mehrere gute Treffer gibt (z.B. für verschiedene Standorte), wähle den, der am ehesten dem Hauptsitz oder einem allgemeinen Profil entspricht.
4.  Wenn die Suchergebnisse **keinen** passenden Eintrag für '{company}' enthalten, antworte ausschließlich mit dem Satz: "Es wurden keine passenden NorthData Einträge zu diesem Unternehmen gefunden."
5.  Gib als Ergebnis **nur die URL** aus, sonst nichts.

**Zielunternehmen:** {company}""")
    print(f"[DEBUG] analyze_northdata_results.company: {company}")
    print("--- SYSTEM PROMPT (mit Company) ---")
    print(system_prompt.content)
    print("------------------------------------")
    
    user_prompt = HumanMessage(content=formatted_user_prompt)
    llm_response = llm.invoke([system_prompt, user_prompt])
    
    return llm_response.content.strip()



def process_llm_response(llm_content: str, query: str) -> AIMessage:
    """
    Separate Node/Funktion für die Verarbeitung der LLM-Antwort mit if/else-Logik.
    
    Args:
        llm_content: Die Antwort des LLMs
        query: Die ursprüngliche Suchanfrage
        
    Returns:
        AIMessage: Die formatierte Antwort
    """
    if llm_content == "False":
        # Wenn keine validen Northdata-Ergebnisse gefunden wurden
        print("LLM hat 'False' zurückgegeben - keine validen Northdata-Ergebnisse gefunden")
        return AIMessage(content="Keine validen Northdata-Einträge für das angegebene Unternehmen gefunden.")
    else:
        # Wenn valide Northdata-URLs gefunden wurden
        print(f"LLM hat valide URLs zurückgegeben: {llm_content}")
        urls = [url.strip() for url in llm_content.split('\n') if url.strip()]
        
        if urls:
            formatted_result = f"Folgende Northdata-Einträge wurden für '{query}' gefunden:\n\n"
            for i, url in enumerate(urls, 1):
                formatted_result += f"{i}. {url}\n"
            
            return AIMessage(content=formatted_result)
        else:
            # Fallback falls die LLM-Antwort nicht das erwartete Format hat
            return AIMessage(content=f"Northdata-Suchergebnisse gefunden, aber Format unerwartet:\n{llm_content}")


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



def get_relevant_information(state: ToolState) -> AIMessage:
    """Fasst die Inhalte der URL Links mit den relevanten Informationen über das Unternehmen zusammen."""

    system_prompt = SystemMessage(content="""Du bist ein Experte für Finanzdaten-Analyse und Unternehmensrecherche.
Deine Aufgabe ist es, aus NorthData-Inhalten die wichtigsten Finanzkennzahlen und Unternehmensdaten zu extrahieren.

**Fokus auf folgende Finanzkennzahlen:**
- Umsatz (Jahresumsatz, letzte verfügbare Zahlen)
- Gewinn/Verlust (vor Steuern, nach Steuern)
- Bilanzsumme
- Mitarbeiteranzahl
- Geschäftsführung/Management
- Unternehmenshistorie (wichtige Meilensteine)
- Rechtsform und Registerdaten

**Anweisungen:**
1. Extrahiere alle verfügbaren Finanzkennzahlen aus den strukturierten Daten
2. Fokussiere auf die neuesten verfügbaren Zahlen
3. Strukturiere die Informationen klar nach Kategorien
4. Ignoriere irrelevante technische Details oder Navigationselemente
5. Gib nur die extrahierten Fakten aus, ohne Interpretationen

**Format:**
- Umsatz: [Zahl] EUR (Jahr)
- Gewinn: [Zahl] EUR (Jahr)  
- Mitarbeiter: [Zahl] (Jahr)
- Geschäftsführung: [Namen]
- etc.""")
            
    user_prompt = HumanMessage(content=state["messages"])
    response = llm.invoke([system_prompt, user_prompt])
    return response



def extract_structured_html_content(soup: BeautifulSoup, url: str) -> Dict[str, any]:
    """
    Extrahiert strukturierte Daten aus Northdata HTML-Seiten basierend auf spezifischen CSS-Selektoren.
    Diese Funktion wird vor dem HTML-Cleaner ausgeführt.
    
    Args:
        soup: BeautifulSoup-Objekt der HTML-Seite
        url: Die URL der Seite für Logging-Zwecke
        
    Returns:
        Dict mit extrahierten strukturierten Daten
    """
    extracted_data = {
        "url": url,
        "historie": [],
        "chartData": [],
        "drillDownData": []
    }
    
    try:
        # Parameter 1: Historie-Daten extrahieren
        # Key: historie, CSS Selector: figure.bizq, Attribute: data-data
        historie_elements = soup.select("figure.bizq")
        for element in historie_elements:
            data_attr = element.get("data-data")
            if data_attr:
                extracted_data["historie"].append(data_attr)
        
        print(f"Historie-Elemente gefunden: {len(extracted_data['historie'])} für {url}")
        
        # Parameter 2: Chart-Daten extrahieren  
        # Key: chartData, CSS Selector: div.tab-content.has-bar-charts, Attribute: data-data
        chart_elements = soup.select("div.tab-content.has-bar-charts")
        for element in chart_elements:
            data_attr = element.get("data-data")
            if data_attr:
                extracted_data["chartData"].append(data_attr)
        
        print(f"Chart-Elemente gefunden: {len(extracted_data['chartData'])} für {url}")
        
        # Parameter 3: Drill-Down-Daten extrahieren
        # Key: drillDownData, CSS Selector: div.tab-content[data-data], Attribute: data-data
        drill_elements = soup.select("div.tab-content[data-data]")
        for element in drill_elements:
            data_attr = element.get("data-data")
            if data_attr:
                extracted_data["drillDownData"].append(data_attr)
        
        print(f"Drill-Down-Elemente gefunden: {len(extracted_data['drillDownData'])} für {url}")
        
        # Zusätzliche Northdata-spezifische Selektoren
        # Unternehmensinformationen
        company_info = soup.select(".company-info, .company-details, .company-header")
        if company_info:
            extracted_data["company_info"] = [elem.get_text(strip=True) for elem in company_info[:3]]
        
        # Geschäftsführer/Management
        management = soup.select(".management, .directors, .executive")
        if management:
            extracted_data["management"] = [elem.get_text(strip=True) for elem in management[:5]]
        
        # Finanzdaten
        financial = soup.select(".financial, .balance, .revenue")
        if financial:
            extracted_data["financial"] = [elem.get_text(strip=True) for elem in financial[:5]]
            
    except Exception as e:
        print(f"Fehler bei der strukturierten HTML-Extraktion für {url}: {e}")
        extracted_data["error"] = str(e)
    
    return extracted_data


def format_extracted_data_for_llm(extracted_data: Dict[str, any]) -> str:
    """
    Formatiert die extrahierten strukturierten Daten für die LLM-Verarbeitung.
    
    Args:
        extracted_data: Dictionary mit extrahierten Daten
        
    Returns:
        Formatierter String für LLM-Input
    """
    formatted_content = f"=== STRUKTURIERTE DATEN VON {extracted_data['url']} ===\n\n"
    
    # Historie-Daten
    if extracted_data.get("historie"):
        formatted_content += "**HISTORIE/ENTWICKLUNG:**\n"
        for i, data in enumerate(extracted_data["historie"], 1):
            formatted_content += f"{i}. {data}\n"
        formatted_content += "\n"
    
    # Chart-Daten
    if extracted_data.get("chartData"):
        formatted_content += "**CHART/GRAFIK-DATEN:**\n"
        for i, data in enumerate(extracted_data["chartData"], 1):
            formatted_content += f"{i}. {data}\n"
        formatted_content += "\n"
    
    # Drill-Down-Daten
    if extracted_data.get("drillDownData"):
        formatted_content += "**DETAILDATEN:**\n"
        for i, data in enumerate(extracted_data["drillDownData"], 1):
            formatted_content += f"{i}. {data}\n"
        formatted_content += "\n"
    
    # Zusätzliche Informationen
    for key in ["company_info", "management", "financial"]:
        if extracted_data.get(key):
            formatted_content += f"**{key.upper().replace('_', ' ')}:**\n"
            for item in extracted_data[key]:
                if item.strip():  # Nur nicht-leere Inhalte
                    formatted_content += f"- {item}\n"
            formatted_content += "\n"
    
    if extracted_data.get("error"):
        formatted_content += f"**FEHLER:** {extracted_data['error']}\n"
    
    return formatted_content



def finance_scrape_tool(query: str) -> AIMessage:
    """Dieses Tool durchsucht Northdata nach Unternehmensinformationen."""

# === GEÄNDERTE SUCH ANFRAGE ===
    # Schritt 1: Verbessern Sie die Suchanfrage
    # Extrahiere nur den Firmennamen für eine robustere Suche
    company_name_only = query.split(" AND ")[0].strip()
    search_query = f"site:northdata.de ({company_name_only})"
    print(f"Angepasste Suchanfrage für die API: {search_query}")

    try:
        # Serper API erwartet POST mit JSON-Payload
        payload = {
            "q": search_query,
            "location": "Germany",
            "gl": "de",
            "hl": "de",
            "num": 8
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
        search_results = response.json()
    except Exception as e:
        return AIMessage(content=f"Fehler bei der Google-Suche: {e}")

    # Formatiere die Suchergebnisse für das LLM
    formatted_user_prompt = f"Hinweis (Unternehmen und Ort): {query}\n\n--- Suchergebnisse ---\n\n"

    # Korrigierte Datenstruktur: Ergebnisse sind in organic (Serper API)
    if 'organic' in search_results and search_results['organic']:
        for i, result in enumerate(search_results['organic']):
            title = result.get('title', 'Kein Titel')
            link = result.get('link', 'Kein Link')
            snippet = result.get('snippet', 'Kein Snippet')
            
            formatted_user_prompt += f"{i + 1}. Suchergebnis:\n"
            formatted_user_prompt += f"  - Title: {title}\n"
            formatted_user_prompt += f"  - Url: {link}\n"
            formatted_user_prompt += f"  - Snippet: {snippet}\n\n"
    else:
        formatted_user_prompt += "Es wurden keine Suchergebnisse gefunden."
        
    # ZUR KONTROLLE: Unbedingt die Ausgabe prüfen!
    print("--- PROMPT FÜR DAS LLM ---")
    print(formatted_user_prompt)
    print("--------------------------")

    # --- Rufe die LLM Chain auf --- #
    try:
        # NODE 1: LLM-Analyse
        print(f"[DEBUG] company/query: {query}")
        print(f"[DEBUG] company_name_only for LLM: {company_name_only}")
        llm_content = analyze_northdata_results(formatted_user_prompt, company_name_only)
        print(f"Gefundene URL-Info: {llm_content}")
        
        target_url = extract_and_format_links(llm_content)
        print(f"Gefundene URL-Info: {target_url}")

    except Exception as e:
        return AIMessage(content=f"Fehler im LLM-Agenten: {e}")
    

    ### --- Der Loop der durch alle URL Links einzeln iteriert --- ###
    all_summaries = []

    try: 
        for url_dict in target_url:  # Verwende target_url direkt
            url_string = url_dict['url']
            print(f"Verarbeite URL: {url_string}")

            try:
                markdown_content: str = ""
                structured_data: Dict[str, any] = {}
                session = create_http_session()

                # Primär: Markdown-Tool nutzen (außer für northdata.de)
                is_northdata = False
                try:
                    host = urlparse(url_string).netloc.lower()
                    is_northdata = "northdata.de" in host
                except Exception:
                    is_northdata = False

                if scrape_website_to_markdown is not None and not is_northdata:
                    try:
                        md_out = scrape_website_to_markdown(url_string)
                        if isinstance(md_out, str) and md_out.strip():
                            markdown_content = md_out.strip()
                            # Strukturierte HTML-Daten können ohne HTML nicht extrahiert werden
                            structured_data = {}
                            # Debug: Markdown aus Markdown-Tool anzeigen
                            debug_print_snippet("MARKDOWN (markdown_tool)", markdown_content, DEBUG_SNIPPET_CHARS)
                    except Exception as md_err:
                        print(f"Markdown-Tool fehlgeschlagen für {url_string}: {md_err}")

                # Fallback: klassische HTTP-GET + strukturierte Extraktion + lokale Markdown-Konvertierung
                if not markdown_content:
                    print("[DEBUG] Fallback-Fetch: Session mit Retries und erhöhtem Timeout aktiv")
                    response = session.get(url_string, timeout=(20, 60))
                    response.raise_for_status()
                    content = response.text

                    # Debug: Rohes HTML aus dem HTTP-Request anzeigen
                    debug_print_snippet("RAW_HTML", content, DEBUG_SNIPPET_CHARS)

                    soup = BeautifulSoup(content, 'html.parser')
                    structured_data = extract_structured_html_content(soup, url_string)
                    formatted_structured_data = format_extracted_data_for_llm(structured_data)
                    print(f"Strukturierte Daten extrahiert für URL: {url_string}")

                    if any(structured_data.get(key) for key in ["historie", "chartData", "drillDownData", "company_info", "management", "financial"]):
                        markdown_content = formatted_structured_data
                        print(f"Verwende strukturierte Daten für {url_string}")
                    else:
                        # Als Fallback nur Text/Markdown, aber gekürzt
                        text_content = soup.get_text(separator="\n")
                        fallback_markdown = convert_html_to_markdown(response.text)
                        # Bevorzugt reinen Text, da kompakter; wenn leer, nimm Markdown
                        markdown_content = text_content if text_content.strip() else fallback_markdown
                        print(f"Fallback: Verwende Text/Markdown für {url_string}")

                    # Vor LLM-Call auf sichere Länge kürzen
                    markdown_content = trim_for_llm(markdown_content, MAX_LLM_INPUT_CHARS)
                    # Debug: Markdown aus Fallback/strukturiertem Pfad anzeigen
                    debug_print_snippet("MARKDOWN (prepared)", markdown_content, DEBUG_SNIPPET_CHARS)

                # NODE 4: Relevante Informationen extrahieren
                summary = get_relevant_information(ToolState(messages=markdown_content))
                all_summaries.append({
                    "url": url_string,
                    "summary": summary.content,
                    "structured_data": structured_data  # Zusätzliche strukturierte Daten für Debugging
                })
                print(f"Zusammenfassung erstellt für URL: {url_string}")

            except requests.RequestException as e:
                print(f"Fehler beim Abrufen der URL {url_string}: {e}")
                all_summaries.append({
                    "url": url_string,
                    "summary": f"Fehler beim Abrufen der URL: {e}"
                })
            except Exception as e:
                print(f"Fehler bei der Verarbeitung von {url_string}: {e}")
                all_summaries.append({
                    "url": url_string,
                    "summary": f"Fehler bei der Verarbeitung: {e}"
                })

    except Exception as e:
        print(f"Fehler beim Verarbeiten der URLs: {e}")
        return AIMessage(content=f"Fehler beim Verarbeiten der URLs: {e}")

    # Erstelle finale Antwort
    if not all_summaries:
        return AIMessage(content="Keine URLs konnten erfolgreich verarbeitet werden.")

    final_result = f"Northdata-Analyse für '{query}':\n\n"
    for i, summary_data in enumerate(all_summaries, 1):
        final_result += f"**{i}. {summary_data['url']}**\n"
        final_result += f"{summary_data['summary']}\n\n"

    return AIMessage(content=final_result)
    

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Testlauf für finance_scrape_tool")
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default="Siemens AND München",
        help="Suchanfrage, z.B. '(Unternehmen Ort)'",
    )
    parser.add_argument(
        "--debug-chars",
        type=int,
        default=DEBUG_SNIPPET_CHARS,
        help="Maximale Zeichenanzahl für Debug-Snippets (Standard aus ENV DEBUG_SNIPPET_CHARS)",
    )
    args = parser.parse_args()

    # ggf. Debug-Länge zur Laufzeit anpassen
    if isinstance(args.debug_chars, int) and args.debug_chars > 0:
        DEBUG_SNIPPET_CHARS = args.debug_chars  # type: ignore

    print("[TEST] Starte Testlauf finance_scrape_tool...")
    print(f"[TEST] Query: {args.query}")
    try:
        result_message = finance_scrape_tool(args.query)
        print("\n[TEST] Ergebnis-Nachricht:\n")
        print(result_message.content)
    except Exception as test_err:
        print(f"[TEST] Fehler beim Testlauf: {test_err}")




### DAS MUSS HIER STEHEN BLEIBEN ###

    # try:
    #     response = requests.get(
    #         "https://www.searchapi.io/api/v1/search",
    #         headers={
    #             "Accept": "application/json",
    #             "Authorization": f"Bearer {google_api_key}",
    #         },
    #         params={
    #             "engine": "google",
    #             "q": search_query,  # Verwende search_query statt query
    #             "num": 5,
    #             "gl": "de",
    #             "hl": "de",
    #             "safe": "off",
    #             "lr": "lang_de",
    #             "device": "desktop",
    #         },
    #         timeout=30,
    #     )
    #     response.raise_for_status()
    #     search_results = response.json()
    # except Exception as e:
    #     return AIMessage(content=f"Fehler bei der Google-Suche: {e}")

    # # Formatiere die Suchergebnisse für das LLM
    # formatted_user_prompt = f"Hinweis (Unternehmen und Ort): {query}\n\n--- Suchergebnisse ---\n\n"

    # # Korrigierte Datenstruktur: Ergebnisse sind in organic_results
    # if 'organic_results' in search_results and search_results['organic_results']:
    #     for i, result in enumerate(search_results['organic_results']):
    #         title = result.get('title', 'Kein Titel')
    #         typ = result.get('type', 'Kein Typ')
    #         link = result.get('link', 'Kein Link')
    #         snippet = result.get('snippet', 'Kein Snippet')
            
    #         formatted_user_prompt += f"{i + 1}. Suchergebnis:\n"
    #         formatted_user_prompt += f"  - Title: {title}\n"
    #         formatted_user_prompt += f"  - Url: {link}\n"
    #         formatted_user_prompt += f"  - Snippet: {snippet}\n\n"
    # else:
    #     formatted_user_prompt += "Es wurden keine Suchergebnisse gefunden."
        
    # # ZUR KONTROLLE: Unbedingt die Ausgabe prüfen!
    # print("--- PROMPT FÜR DAS LLM ---")
    # print(formatted_user_prompt)
    # print("--------------------------")
