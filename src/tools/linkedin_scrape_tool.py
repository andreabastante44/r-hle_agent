import os
import requests
import re 
import json
from dotenv import load_dotenv
from typing_extensions import TypedDict
load_dotenv()
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# --- Initialisierung (Annahme) ---
openai_api_key = os.environ.get("OPENAI_API_KEY")
google_api_key = os.environ.get("GOOGLESEARCH_API_KEY")
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
def linkedin_scrape_tool(query: str) -> str:
    """LinkedIn Scrape Tool: Verwende dieses Tool immer dann, wenn du das LinkedIn einer Person/Kontakts scrapen willst."""
    
    # Validierung der Eingabe
    if not query or not query.strip():
        return "Fehler: Leere Suchanfrage erhalten"

    # --- LLM Chains Definieren --- #
    def get_linkedin_profil(state: ToolState) -> AIMessage:
        """Dieser Agent ist dafür verantwortlich, den richtigen URL Link, also den richtigen LinkedIn Url ausuzuwählen."""

        system_prompt = SystemMessage(content="""Du bist ein Experte darin, aus einer Liste von Suchergebnissen das korrekte LinkedIn-Profil einer Person zu identifizieren.
Deine Aufgabe ist es, die untenstehenden Suchergebnisse zu analysieren und das relevanteste LinkedIn-Profil auszuwählen.
- Das Profil sollte zum Namen und Unternehmen aus dem Hinweis passen.
- Wenn Unternehmen und Standort übereinstimmen, ist eine Abweichung beim Vornamen (z.B. 'Tim' statt 'Thomas') akzeptabel.
- Gib als Ergebnis NUR den URL-Link und den zugehörigen Snippet-Text aus.

Beispiel-Ausgabe:
url: https://www.linkedin.com/in/max-mustermann/
snippet: Max Mustermann - CEO bei Musterfirma GmbH | Standort: Berlin ...

Wenn unter den Ergebnissen kein passendes Profil zu finden ist, antworte mit: "Kein passendes LinkedIn Profil in den Suchergebnissen gefunden." """)
        
        user_prompt = HumanMessage(content=state["messages"])

        response = llm.invoke([system_prompt, user_prompt])
        return response

# === GEÄNDERTE SUCH ANFRAGE ===
    # Schritt 1: Verbessern Sie die Suchanfrage
    search_query = f"site:linkedin.com/in/ {query}"
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
        data = response.json()
        print("Google Search erfolgreich")
    except Exception as e:
        return f"Fehler bei der Google-Suche: {e}"

    # +++++++++ HIER BEGINNT DIE KORREKTE IMPLEMENTIERUNG +++++++++
    formatted_user_prompt = f"Hinweis (Person und Unternehmen): {query}\n\n--- Suchergebnisse ---\n\n"

    # KORREKTUR: Serper API verwendet 'organic' (nicht 'organic_results')
    if 'organic' in data and data['organic']:
        for i, result in enumerate(data['organic']):
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
        linkedin_profil_response = get_linkedin_profil(ToolState(messages=formatted_user_prompt))
        found_profile_info = linkedin_profil_response.content
        print(f"Gefundene Profil-Info: {found_profile_info}")

        # Extrahiere die erste URL aus der LLM-Antwort
        url_match = re.search(r"https?://[^\s]+", found_profile_info)
        profile_url = url_match.group(0) if url_match else None

        # Falls eine URL gefunden wurde und Markdown-Tool verfügbar ist: scrape und zurückgeben
        if profile_url and scrape_website_to_markdown is not None:
            try:
                md = scrape_website_to_markdown(profile_url)
                if isinstance(md, str) and md.strip():
                    return f"## LinkedIn Profil: {profile_url}\n\n{md.strip()}"
            except Exception as md_err:
                print(f"Markdown-Tool fehlgeschlagen für {profile_url}: {md_err}")
        
        # Fallback: bisheriges Verhalten (nur die Profil-Info ausgeben)
        return found_profile_info
        
    except Exception as e:
        print(f"Agent 'get_linkedin_profil' fehlgeschlagen: {e}")
        return f"Fehler im LLM-Agenten: {e}"
    
# def run_linkedin_scrape_tool():
#     print("=== LinkedIn Scrape Tool ===")
#     query = "LinkedIn AND Stefan Hencke AND Stuttgart Convensis"
#     result = linkedin_scrape_tool.invoke({"query": query})
#     print(result)

# if __name__ == "__main__":
#     run_linkedin_scrape_tool()




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