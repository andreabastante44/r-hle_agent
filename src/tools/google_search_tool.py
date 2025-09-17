import os
import re
import requests
import json
from typing_extensions import TypedDict, List, Dict, Union
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from markdownify import markdownify as md
from bs4 import BeautifulSoup
load_dotenv()

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

# --- Initialisierung (Annahme) ---
openai_api_key = os.environ.get("OPENAI_API_KEY")
googlesearch_api_key = os.environ.get("GOOGLESEARCH_API_KEY")
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
    mission_prompt: str


@tool
def google_search_tool(query: str, mission_prompt: str) -> str:
    """Google_Search_Tool: Verwende dieses Tool immer dann, wenn du im Web recherchieren und die Inhalte zu scrapen musst"""
    
    # Validierung der Eingabe
    if not query or not query.strip():
        return "Fehler: Leere Suchanfrage erhalten"
    
    def convert_html_to_markdown(html_content: str) -> str:
        try:
            # KORREKTUR: Entferne script und style Tags manuell vor der Markdown-Konvertierung
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            # Entferne auch Images mit data:-URIs und img-Tags
            for img in soup.find_all("img"):
                try:
                    src = (img.get("src") or "").strip()
                    if src.lower().startswith("data:"):
                        img.decompose()
                    else:
                        img.decompose()  # Für LLM irrelevant
                except Exception:
                    pass
            cleaned_html = str(soup)
            
            # Konvertiere HTML zu Markdown mit markdownify
            markdown_content = md(
                cleaned_html,
                heading_style="ATX",  # Verwende # für Überschriften
                convert=['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'ul', 'ol', 'li', 'strong', 'em', 'blockquote'],
                escape_misc=False
            )
            # Normalisieren/trimmen
            markdown_content = re.sub(r"\s+", " ", markdown_content).strip()
            return markdown_content
        except Exception as e:
            print(f"Fehler bei HTML-zu-Markdown-Konvertierung: {e}")
            return re.sub(r"\s+", " ", html_content).strip()  

    ### --- Agenten --- ###
    def get_url_picker(state: ToolState) -> AIMessage:
        """Diese LLM Chain ist dafür verantwortlich, den richtigen URL Link auszuwählen."""
        system_prompt = SystemMessage(content="""Du bist ein KI-gestützter Suchanalyst. Deine Aufgabe ist es, für eine gegebene Suchanfrage die relevantesten URLs zu identifizieren, die einen direkten Bezug zu einem Unternehmen haben.

**Regeln für die Auswahl:**

- Wähle ausschließlich URLs aus, die einen direkten Zusammenhang mit dem Unternehmen aus der Suchanfrage haben. Der Unternehmensname oder ähnliche relevante Begriffe sollten im Titel oder im Snippet der Google-Suche vorkommen.
- Bevorzuge offizielle Unternehmensseiten, öffentliche Register oder seriöse Branchenverzeichnisse.
- Ignoriere alle URLs, die auf eine PDF-Datei verweisen.
- Gib als Ergebnis eine Liste von URLs aus, die du für am relevantesten hältst. Füge keine weiteren Erklärungen, Titel oder Formatierungen hinzu.""")
        
        user_prompt = HumanMessage(content=state["messages"])
        response = llm.invoke([system_prompt, user_prompt])
        return response
    

    def get_relevant_information(state: ToolState) -> AIMessage:
        """Fasst die Inhalte der URL Links mit den relevanten Informationen über das Unternehmen zusammen."""

        system_prompt = SystemMessage(content=f"""Du bist ein Experte für Informationsanalyse und -zusammenfassung.
Deine Aufgabe ist es, den bereitgestellten Inhalt eines Web-Scrapes zu analysieren und eine prägnante Zusammenfassung zu erstellen.

**Mission der Recherche:**
{state["mission_prompt"]}

**Anweisungen:**
1.  Fokus liegt auf der **Mission der Recherche**: Extrahiere nur Informationen, die sich auf das angegebene Unternehmen beziehen **und** gleichzeitig mit den in der Mission definierten Themen übereinstimmen.
2.  Ignoriere alle irrelevanten Inhalte wie Werbung, Navigationslinks oder allgemeine, nicht unternehmensspezifische Texte. Selbst wenn ein Absatz das Unternehmen erwähnt, ist er zu ignorieren, wenn er nicht direkt ein Thema der Recherche-Mission behandelt.
3.  Fasse die relevanten Informationen kohärent und ohne unnötige Details zusammen. Das Ergebnis soll ausschließlich Fakten und wichtige Details enthalten.
4.  Gib nur die Zusammenfassung aus. Keine Einleitung, kein Fazit.

**Wichtig:** Wenn der Web-Scrape keine Informationen enthält, die den Kriterien aus Anweisung 1 entsprechen, gib als einziges Ergebnis einen **leeren String** aus!
"""
        )
        
        # Eingabe begrenzen
        limited = (state["messages"] or "").strip()
        if len(limited) > 18000:
            limited = limited[:12000]
        user_prompt = HumanMessage(content=limited)
        response = llm.invoke([system_prompt, user_prompt])
        return response
    
    def extract_and_format_links(text: str) -> List[Dict[str, str]]:
        """
        Extracts all URLs from a text string and formats them into a list of dictionaries.
        """
        if not isinstance(text, str):
            return []
        url_pattern = r"\bhttps?:\/\/[^\s<>\"']+"
        extracted_urls = re.findall(url_pattern, text, re.IGNORECASE)
        return [{"url": url} for url in extracted_urls]
    
    # API-Schlüssel prüfen
    if not googlesearch_api_key:
        return "Fehler: Umgebungsvariable 'GOOGLESEARCH_API_KEY' ist nicht gesetzt"

    try:
        
        response = requests.get(
            "https://www.searchapi.io/api/v1/search",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {googlesearch_api_key}",
            },
            params={
                "engine": "google",
                "q": query,
                "num": 10,
                "gl": "de",
                "hl": "de",
                "safe": "off",
                "lr": "lang_de",
                "device": "desktop",
            },
            timeout=30,
        )
        response.raise_for_status()
        search_results = response.json()

        # Debug-Ausgabe stark kürzen (keine Thumbnails/Base64 dumpen)
        try:
            preview = {
                "search_information": search_results.get("search_information", {}),
                "first_titles": [r.get("title") for r in (search_results.get("organic_results", []) or [])][:5]
            }
            print("--- GSearch Preview ---")
            print(preview)
            print("-----------------------")
        except Exception:
            pass

        print("Google Search API erfolgreich")

        # URL Picker verwenden, um relevante URLs zu identifizieren und PDFs zu filtern
        organic_results = search_results.get("organic_results", [])
        
        # Bereinige Ergebnisse für den URL-Picker LLM
        cleaned_results = []
        for item in organic_results:
            if isinstance(item, dict):
                cleaned_results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet")
                })

        if not cleaned_results:
            return "Keine organischen Suchergebnisse gefunden."
        
        # LLM soll aus den JSON-Daten die besten URLs auswählen
        url_picker_input = json.dumps(cleaned_results, indent=2, ensure_ascii=False)
        url_picker_response = get_url_picker(ToolState(messages=url_picker_input, mission_prompt=mission_prompt))
        
        # Extrahiere die vom LLM ausgewählten URLs
        urls = [item['url'] for item in extract_and_format_links(url_picker_response.content)]

        if not urls:
            return "Keine relevanten URLs vom URL-Picker ausgewählt."

        # Optional: Inhalte der gefundenen URLs mit Markdown-Tool scrapen
        if scrape_website_to_markdown is not None:
            summaries: List[str] = []
            for u in urls[:5]:  # begrenze auf die Top-5
                try:
                    md_out = scrape_website_to_markdown(u)
                    if isinstance(md_out, str):
                        md_out = re.sub(r"\s+", " ", md_out).strip()
                    if isinstance(md_out, str) and md_out:
                        # Länge vor LLM begrenzen
                        limited_md = md_out[:12000]
                        summarizer_response = get_relevant_information(ToolState(messages=limited_md, mission_prompt=mission_prompt))
                        summaries.append(f"## Inhalt: {u}\n\n{summarizer_response.content.strip()}")
                except Exception as md_err:
                    print(f"Markdown-Tool fehlgeschlagen für {u}: {md_err}")
            if summaries:
                return "\n\n---\n\n".join(summaries)

        # Fallback: Nur die URLs zurückgeben
        return "\n".join(urls)
    except requests.RequestException as e:
        print(f"Google Search API fehlgeschlagen: {e}")
        return f"Fehler bei der Google Search API: {e}"
        