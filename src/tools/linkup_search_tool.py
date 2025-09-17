import os
from dotenv import load_dotenv
from typing_extensions import TypedDict, List, Dict, Union
import requests
 
load_dotenv()

linkup_api_key = os.environ.get("LINKUP_API_KEY")

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

# TOKEN-LIMITING IMPORT
from tools.token_limiter import truncate_content, count_tokens

# --- State Definition (Annahme) ---
class ToolState(TypedDict):
    messages: str

@tool
def linkup_search_tool(query: str) -> str:
    """linkup_search_tool: Verwende dieses Tool immer dann, wenn du eine Webrecherche durchführen musst."""

    url = "https://api.linkup.so/v1/search"

    payload = {
        "q": query,
        "depth": "standard",
        "outputType": "sourcedAnswer",
        "structuredOutputSchema": "<string>",
        "includeImages": "false",
        "fromDate": "2020-01-01",
        "toDate": "2025-08-08",
        # "excludeDomains": ["wikipedia.com"],
        # "includeDomains": ["microsoft.com", "agolution.com"]
    }
    headers = {
        "Authorization": f"Bearer {linkup_api_key}",
        "Content-Type": "application/json"
    }

    print(f"Linkup-Search-Tool: {query}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        result = response.json()
        result_str = str(result)
        
        # TOKEN-LIMITING: Prüfe und begrenze die Antwort
        token_count = count_tokens(result_str)
        if token_count > 25000:
            print(f"⚠️ Linkup-Ergebnis zu lang ({token_count} tokens) - wird gekürzt")
            result_str = truncate_content(result_str, max_tokens=12000)
        
        print(f"Linkup-Ergebnis: {count_tokens(result_str)} tokens")
        return result_str
    except requests.exceptions.RequestException as e:
        return f"Fehler bei der Linkup-Suche: {str(e)}"
    except Exception as e:
        return f"Unerwarteter Fehler: {str(e)}"