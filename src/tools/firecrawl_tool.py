import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

url = "https://www.fehrenbach-klaus.de/"

def firecrawl_tool(target_url: str) -> str:
    """
    Crawlt eine Website mit Firecrawl API (direkte HTTP-Requests) und gibt den Inhalt als String zurück.
    """
    try:
        # API-Key überprüfen
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            return "Fehler: FIRECRAWL_API_KEY Umgebungsvariable ist nicht gesetzt"
        
        print(f"Crawle URL: {target_url}")
        
        # API-Endpoint und Payload
        api_url = "https://api.firecrawl.dev/v2/crawl"
        
        payload = {
            "url": target_url,
            "sitemap": "include",
            "crawlEntireDomain": False,
            "limit": 10,
            "maxDiscoveryDepth": 1,
            "excludePaths": ["/en/", "/english/", "/eng/", "en.html", "english.html"],
            "scrapeOptions": {
                "onlyMainContent": True,
                "maxAge": 172800000,
                "formats": [
                    "markdown"
                ],
                "excludeTags": ["img", "picture", "figure"]
            }
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Crawl-Request senden
        response = requests.post(api_url, json=payload, headers=headers)
        
        if response.status_code != 200:
            return f"Fehler: API-Request fehlgeschlagen mit Status {response.status_code}: {response.text}"
        
        job_data = response.json()
        
        # Job-ID für Status-Abfrage
        if 'id' not in job_data:
            return f"Fehler: Keine Job-ID erhalten: {job_data}"
        
        job_id = job_data['id']
        print(f"Crawl-Job gestartet mit ID: {job_id}")
        
        # Status-Endpoint für Job-Ergebnisse
        status_url = f"https://api.firecrawl.dev/v2/crawl/{job_id}"
        status_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Auf Job-Completion warten (Polling)
        import time
        max_attempts = 60  # 5 Minuten bei 5-Sekunden-Intervallen
        attempt = 0
        
        while attempt < max_attempts:
            status_response = requests.get(status_url, headers=status_headers)
            
            if status_response.status_code != 200:
                return f"Fehler beim Abrufen des Job-Status: {status_response.status_code}: {status_response.text}"
            
            status_data = status_response.json()
            
            if status_data.get('status') == 'completed':
                print("Crawl-Job erfolgreich abgeschlossen")
                break
            elif status_data.get('status') == 'failed':
                return f"Crawl-Job fehlgeschlagen: {status_data.get('error', 'Unbekannter Fehler')}"
            
            print(f"Job-Status: {status_data.get('status')} - warte 5 Sekunden...")
            time.sleep(3)
            attempt += 1
        
        if attempt >= max_attempts:
            return "Fehler: Crawl-Job Timeout - Job nicht innerhalb der erwarteten Zeit abgeschlossen"
        
        # Endergebnisse abrufen
        if 'data' not in status_data:
            return "Fehler: Keine Crawl-Daten im Ergebnis gefunden"
        
        # Inhalte extrahieren und zusammenfassen
        crawled_content = []
        for page_data in status_data['data']:
            if 'markdown' in page_data:
                crawled_content.append(f"URL: {page_data.get('url', 'Unbekannt')}\n")
                crawled_content.append(f"Titel: {page_data.get('title', 'Kein Titel')}\n")
                crawled_content.append(f"Inhalt:\n{page_data['markdown']}\n")
                crawled_content.append("-" * 80 + "\n")
        
        result = "\n".join(crawled_content)
        print(f"Crawl erfolgreich - {len(status_data['data'])} Seiten gefunden")
        return result
        
    except Exception as e:
        error_message = f"Fehler beim Crawlen von {target_url}: {str(e)}"
        print(error_message)
        return error_message


if __name__ == "__main__":
    result = firecrawl_tool(url)
    print("=" * 80)
    print("FIRECRAWL ERGEBNISSE:")
    print("=" * 80)
    print(result)

