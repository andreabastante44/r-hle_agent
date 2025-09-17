import os
import re
import requests
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
brave_api_key = os.environ.get("BRAVESEARCH_API_KEY")
llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2)

# --- State Definition (Annahme) ---
class ToolState(TypedDict):
    messages: str

@tool
def brave_scrape_tool(query: str) -> str:
    """Brave_Scrape_Tool: Verwende dieses Tool immer dann, wenn du im Web recherchieren und die Inhalte zu scrapen musst"""
    
    # Validierung der Eingabe
    if not query or not query.strip():
        return "Fehler: Leere Suchanfrage erhalten"
    
    def convert_html_to_markdown(html_content: str) -> str:
        """
        Konvertiert HTML-Inhalt zu Markdown-Format.
        
        Args:
            html_content: Der HTML-Inhalt als String
            
        Returns:
            Der konvertierte Markdown-Inhalt
        """
        try:
            # KORREKTUR: Entferne script und style Tags manuell vor der Markdown-Konvertierung
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            cleaned_html = str(soup)
            
            # Konvertiere HTML zu Markdown mit markdownify
            markdown_content = md(
                cleaned_html,
                heading_style="ATX",  # Verwende # für Überschriften
                convert=['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'ul', 'ol', 'li', 'strong', 'em', 'blockquote'],
                escape_misc=False
            )
            return markdown_content
        except Exception as e:
            print(f"Fehler bei HTML-zu-Markdown-Konvertierung: {e}")
            # Fallback: Return original content if conversion fails
            return html_content

    ### --- Agenten --- ###
    def get_url_picker(state: ToolState) -> AIMessage:
        """Diese LLM Chain ist dafür verantwortlich, den richtigen URL Link auszuwählen."""
        system_prompt = SystemMessage(content="""Du bist ein KI-gestützter Experte für Suchanalysen. Deine Aufgabe ist es, für eine gegebene Benutzeranfrage die drei optimalsten URL Links zu identifizieren und auszugeben.

**SEHR WICHTIGE REGEL:** Wähle **ausschließlich** Links aus, bei denen der Titel oder der Snippet sowohl den **Unternehmensnamen** als auch den **Standort** aus der Benutzeranfrage enthält. Es muss ein zwingender und direkter Unternehmensbezug bestehen. Wenn diese Bedingung nicht erfüllt ist, wähle den Link NICHT aus.

Priorisierung offizieller Quellen: Bevorzuge bei deiner Auswahl offizielle Register, bekannte Nachrichtenportale oder die Unternehmenswebseite selbst.

Gib als Ergebnis ausschließlich den URL Link aus. Füge keine Erklärungen, Titel, Nummerierungen oder sonstige Texte hinzu.
WICHTIG: IGNORIERE URL LINKS mit ".pdf" oder einen Verweis darauf, dass es sich um eine PDF Datei handelt!""")
        
        user_prompt = HumanMessage(content=state["messages"])
        response = llm.invoke([system_prompt, user_prompt])
        return response

    def get_markdown_cleaner(state:ToolState) -> AIMessage:
        """
        Säubert die Markdown Ausgabe der HTML-zu-Markdown-Konvertierung
        HINWEIS: Aktuell nicht verwendet - markdownify erledigt bereits die meiste Bereinigung.
        Funktion wird für mögliche zukünftige Verwendung beibehalten.
        """

        system_prompt = SystemMessage(content="""Markdown-Bereinigungsprompt für LLMs
Du bist ein Experte für die Bereinigung und Strukturierung von Markdown-Inhalten. Deine Aufgabe ist es, bereits in Markdown konvertierte Webinhalte zu bereinigen und dabei alle wichtigen Textinhalte zu erhalten.

Deine Aufgaben:
1. Entfernen von überflüssigen Markdown-Elementen
- Entferne Navigationsmenüs, Header, Footer und Seitenleisten
- Eliminiere Werbebanner, Pop-ups und Marketing-Elemente
- Entferne redundante oder dekorative Elemente
- Lösche Cookie-Hinweise und rechtliche Disclamer die nicht relevant sind

2. Beibehalten wichtiger Inhalte
- Haupttext: Alle Überschriften, Absätze und Fließtext
- Strukturelle Elemente: Listen, Tabellen und deren Inhalte
- Links: Wichtige interne und externe Verlinkungen mit Ankertext
- Zitate und Hervorhebungen: Blockquotes, wichtige Texthervorhebungen
- FAQ-Bereiche: Fragen und Antworten

3. Strukturierung des bereinigten Markdown-Inhalts
- Organisiere den Text in logischer Reihenfolge
- Verwende klare Markdown-Formatierung für Überschriften (# ## ###)
- Formatiere Links als [Linktext](URL)
- Behalte wichtige Listen und Tabellen bei

4. Entfernung irrelevanter Inhalte
- Entferne Auflistungen von Menüoptionen, Suchoptionen, Filteroptionen
- Entferne allgemeine FAQ-Bereiche, die nicht unternehmensspezifisch sind
- Entferne alle Links, die nicht zum Unternehmen gehören
- Entferne Social Media Buttons und Share-Buttons

5. Qualitätskontrolle
- Stelle sicher, dass der bereinigte Text zusammenhängend und verständlich ist
- Entferne doppelte oder redundante Inhalte
- Korrigiere offensichtliche Formatierungsfehler
- Behalte nur relevante Kontaktdaten und wichtige Metainformationen

Ausgabeformat:
Liefere den bereinigten Inhalt als gut strukturierten Markdown-Text zurück. Beginne mit dem Haupttitel der Seite und folge einer logischen Gliederung.

Beispiel für das gewünschte Ergebnis:
# Haupttitel der Seite

## Erste Hauptüberschrift
Bereinigter Fließtext...

### Unterüberschrift
- Listenpunkt 1
- Listenpunkt 2

[Wichtiger Link](https://example.com)

## Wichtige Informationen
**Frage:** Wie funktioniert das?
**Antwort:** Erklärung...""")
        
        user_prompt = HumanMessage(content=state["messages"])
        response = llm.invoke([system_prompt, user_prompt])
        return response

    def get_relevant_information(state: ToolState) -> AIMessage:
        """Fasst die Inhalte der URL Links mit den relevanten Informationen über das Unternehmen zusammen."""

        system_prompt = SystemMessage(content="""Du bist ein Experte für Informationsanalyse und -zusammenfassung.
Deine Aufgabe ist es, den folgenden Inhalt eines Web-Scrapes sorgfältig zu analysieren und eine prägnante Zusammenfassung der **wichtigsten unternehmensbezogenen Informationen** zu erstellen.
**Anweisungen:**
1.  Analysiere den bereitgestellten Web-Scrape Inhalt.
2.  Identifiziere und extrahiere *ausschließlich* Fakten, Zahlen, Hauptargumente und sonstige wichtige Details, die in **direktem Zusammenhang mit dem in der Benutzeranfrage genannten Unternehmen** stehen. Dies können auch spezifische Themen wie Insolvenzverfahren, Mahnverfahren etc. sein. (Achte darauf, wonach in der Benutzeranfrage gesucht wird. Ist nur der Unternehmensname und die Postleitzahl in der Benutzeranfrage, heißt das, dass nach grundlegenden Informationen des Unternehmens gesucht wird!)
3.  **SEHR WICHTIG:** Ignoriere allgemeine Informationen, Definitionen oder Texte, die nicht spezifisch auf das Unternehmen eingehen, auch wenn sie thematisch passen. Die Zusammenfassung darf nur unternehmensspezifische Inhalte enthalten.
4.  Ignoriere alle Informationen im Scrape, die nicht wichtig für die Benutzeranfrage sind (z.B. Werbung, irrelevante Navigationselemente, themenfremde Informationen, falscher Unternehmensname etc.).
5.  Erstelle eine kohärente und gut strukturierte Zusammenfassung der relevanten Informationen.
6.  Gib nur die Zusammenfassung aus, ohne zusätzliche Einleitung oder Fazit.

Wichtig: Wenn der Web-Scrape Inhalt nichts mit dem Unternehmen aus der Benutzeranfrage zu tun hat, gebe ausschließlich folgendes als Ergebnis aus = "Zur 'Suchanfrage' konnte nichts relevantes gefunden werden.""")
        
        user_prompt = HumanMessage(content=state["messages"])
        response = llm.invoke([system_prompt, user_prompt])
        return response
    
    def extract_and_format_links(text: str) -> List[Dict[str, str]]:
        """
        Extracts all URLs from a text string and formats them into a list of dictionaries.

        Args:
            text: The input string to search for links.

        Returns:
            A list of dictionaries, where each dictionary has a "url" key
            and the found URL as its value.
        """
        # Return an empty list if the input is not a string
        if not isinstance(text, str):
            return []

        # Regular expression to find URLs (http and https)
        url_pattern = r"\bhttps?:\/\/[^\s<>\"']+"

        
        # Find all matches in the input text, ignoring case
        extracted_urls = re.findall(url_pattern, text, re.IGNORECASE)
        
        # Use a list comprehension to format the output
        # e.g., [{"url": "http://..."}, {"url": "https://..."}]
        formatted_output = [{"url": url} for url in extracted_urls]
        
        return formatted_output

        # --- Brave Search Suche durchführen --- #  
    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": brave_api_key
            },
            params={
                "q": query,
                "count": 3,
                "country": "DE",
                "search_lang": "de",
                "safesearch": "off",
                "freshness": "py", # YYYY-MM-DDtoYYYY-MM-DD
                }
            )
        response.raise_for_status()
        search_results = response.json()

            # KORREKTUR: Die komplette Antwort zur Fehlersuche ausgeben
        print("--- Vollständige API-Antwort von Brave ---")
        print(search_results)
        print("-----------------------------------------")

        print("Brave Search erfolgreich")
    except requests.RequestException as e:
        print(f"Brave Search fehlgeschlagen: {e}")
        # Beenden Sie hier nicht, sondern geben eine Fehlermeldung zurück
        return f"Fehler bei der Brave Search: {e}"
        
# +++++++++ HIER BEGINNT DIE FINALE, KORREKTE IMPLEMENTIERUNG +++++++++
    
    formatted_user_prompt = f"Hinweis (Benutzeranfrage): {query}\n\n--- Suchergebnisse ---\n\n"

    # KORREKTUR: Überprüfe 'web' und 'results'
    if 'web' in search_results and 'results' in search_results['web'] and search_results['web']['results']:
        
        # KORREKTUR: Iteriere durch das 'results'-Array innerhalb von 'web'
        for i, result in enumerate(search_results['web']['results']):
            
            title = result.get('title', 'Kein Titel')
            link = result.get('url', 'Kein Link') 
            snippet = result.get('description', 'Kein Snippet')
                
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

    # --- Rufe die LLM Chain auf um die passenden URLs auszuwählen --- #
    try:
        url_picker_response = get_url_picker(ToolState(messages=formatted_user_prompt))
        found_url = url_picker_response.content

        formatted_url_picker_response = extract_and_format_links(found_url)
        print(f"Gefundene URL-Info: {found_url}")
        
    except Exception as e:
        print(f"Agent 'get_url_picker' fehlgeschlagen: {e}")

    ### --- Der Loop der durch alle URL Links einzeln iteriert --- ###
    all_summaries = []
    
    try:
        # Verarbeite die gefilterten URLs
        # KORREKTUR: Iteriere über die Liste von Wörterbüchern
        for url_dict in formatted_url_picker_response:
            # KORREKTUR: Greife auf den Wert des Schlüssels 'url' zu
            url_string = url_dict['url']
            
            print(f"Verarbeite URL: {url_string}") # Druckt jetzt korrekt: https://...
            try:
                # KORREKTUR: Übergib den URL-String an requests.get()
                response = requests.get(url_string, timeout=5)
                response.raise_for_status()

                # --- HTML zu Markdown Konvertierung ---
                markdown_content = convert_html_to_markdown(response.text)
                print(f"HTML für {url_string} erfolgreich zu Markdown konvertiert.")

                # --- Direkte Zusammenfassung (ohne Markdown-Cleaning) ---
                summarizer_response = get_relevant_information(ToolState(messages=markdown_content))
                single_summary = summarizer_response.content
                print(f"Zusammenfassung für {url_string} erfolgreich erstellt.")

                all_summaries.append(f"## Zusammenfassung von: {url_string}\n\n{single_summary}")

            except Exception as e:
                print(f"Fehler bei der Verarbeitung der URL {url_string}: {e}")
                continue

    except Exception as e:
        print(f"Das URL Cleaning und Zusammenfassen konnte nicht durchgeführt werden: {e}")

    # --- FINALE AUSGABE ---
    # Stelle sicher, dass am Ende etwas zurückgegeben wird
    if not all_summaries:
        final_summary_text = "Es konnten keine relevanten Informationen über das Unternehmen in diesem Artikel gefunden werden."
    else:
        # Verbinde alle Zusammenfassungen zu einem finalen Text
        final_summary_text = "\n\n---\n\n".join(all_summaries)

    # KORREKTER RETURN: Gib einen String zurück, wie für LangChain Tools erforderlich
    return final_summary_text 
    

