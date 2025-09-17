import os
import re
import time
import json
import xmltodict
import threading
from typing import TypedDict, List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse, urljoin
from urllib.robotparser import RobotFileParser

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

# --------------------------------------------------------------------------------------
# Globale Settings
# --------------------------------------------------------------------------------------
openai_api_key = os.environ.get("OPENAI_API_KEY")
google_api_key = os.environ.get("GOOGLESEARCH_API_KEY")
serper_api_key = os.environ.get("SERPER_API_KEY")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

DEBUG = False
USER_AGENT = "Mozilla/5.0 (compatible; CompanyScraper/1.0; +https://example.com/bot)"
RATE_SLEEP_SECONDS = 0.5  # globale, sanfte Rate-Limitierung
MAX_WORKERS = 4
SITEMAP_MAX_DEPTH = 2
MAX_PAGES_TO_SUMMARIZE = 8

# Domains, die wir bei der Homepage-Auswahl meiden (Soziale Netzwerke, Verzeichnisse etc.)
EXCLUDE_DOMAINS = {
    "facebook.com", "www.facebook.com", "linkedin.com", "www.linkedin.com",
    "xing.com", "www.xing.com", "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.twitter.com", "www.x.com",
    "youtube.com", "www.youtube.com", "kununu.com", "www.kununu.com",
    "stepstone.de", "www.stepstone.de", "glassdoor.de", "www.glassdoor.de",
    "glassdoor.com", "www.glassdoor.com", "indeed.com", "www.indeed.com",
    "northdata.de", "www.northdata.de", "northdata.com", "www.northdata.com"
}

# --------------------------------------------------------------------------------------
# HTTP Session mit Pooling, Retries, Gzip, Timeout
# --------------------------------------------------------------------------------------

# Integration des Markdown-Tools für Website-Scraping
try:
    from .markdown_scrape_tool import scrape_website_to_markdown
except Exception:
    try:
        from tools.markdown_scrape_tool import scrape_website_to_markdown
    except Exception:
        scrape_website_to_markdown = None  # type: ignore


def _build_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "OPTIONS"]
    )
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",  # Verhindert veraltete Cache-Probleme
    })
    return s

SESSION = _build_session()
RATE_LOCK = threading.Lock()
LAST_REQUEST_TS: float = 0.0


def _rate_sleep():
    global LAST_REQUEST_TS
    with RATE_LOCK:
        now = time.time()
        dt = now - LAST_REQUEST_TS
        if dt < RATE_SLEEP_SECONDS:
            time.sleep(RATE_SLEEP_SECONDS - dt)
        LAST_REQUEST_TS = time.time()

# --------------------------------------------------------------------------------------
# URL Normalisierung & Domain-Utilities
# --------------------------------------------------------------------------------------


def norm_base_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    p = urlparse(u if "://" in u else "https://" + u)
    scheme = "https"
    netloc = (p.netloc or p.path).lower()
    if not netloc:
        return ""
    return urlunparse((scheme, netloc, "", "", "", "")).rstrip("/")



def same_domain(base: str, candidate: str) -> bool:
    try:
        b = urlparse(base).netloc
        c = urlparse(candidate).netloc
        return bool(c == b or c.endswith("." + b))
    except Exception:
        return False


# --------------------------------------------------------------------------------------
# robots.txt Handling (Cache) & Allowance Checks
# --------------------------------------------------------------------------------------
_RP_CACHE: Dict[str, RobotFileParser] = {}
_RP_LOCK = threading.Lock()



def get_robot_parser(base_url: str) -> RobotFileParser:
    key = norm_base_url(base_url)
    with _RP_LOCK:
        rp = _RP_CACHE.get(key)
        if rp:
            return rp
        rp = RobotFileParser()
        robots_url = urljoin(key + "/", "robots.txt")
        try:
            _rate_sleep()
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            # Bei Fehlern lieber erlauben
            pass
        _RP_CACHE[key] = rp
        return rp



def robots_allowed(base_url: str, url: str) -> bool:
    try:
        rp = get_robot_parser(base_url)
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


# --------------------------------------------------------------------------------------
# Google Search: Homepage Heuristik ohne LLM
# --------------------------------------------------------------------------------------


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""



def _path_len(url: str) -> int:
    try:
        p = urlparse(url).path or "/"
        # Kürzer ist besser für Homepage
        return 0 if p in ("/", "") else len(p.strip("/"))
    except Exception:
        return 9999



def select_company_homepage_from_brave(query: str) -> Optional[str]:
    # API-Schlüssel prüfen
    if not serper_api_key:
        return "Fehler: Umgebungsvariable 'SERPER_API_KEY' ist nicht gesetzt"

    try:
        # Serper API erwartet POST mit JSON-Payload
        payload = {
            "q": query,
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
    except Exception:
        return None

    results = (data or {}).get("organic", []) or []
    if not results:
        # Try alternative formats
        results = data.get("web", {}).get("results", []) or data.get("results", [])
        if not results:
            print("❌ Keine Suchergebnisse gefunden")
            return None

    print(f"📋 {len(results)} Suchergebnisse gefunden:")
    for i, result in enumerate(results[:5], 1):
        title = result.get("title", "Kein Titel")[:60]
        url = result.get("link") or result.get("url") or "Keine URL"
        print(f"   {i}. {title}... → {url}")
    if len(results) > 5:
        print(f"   ... und {len(results) - 5} weitere")

    # Heuristik: gleiche/ähnliche Domain, keine Social/Directory-Domains, kurze Pfade bevorzugen
    q_tokens = {t.lower() for t in re.findall(r"[\w\-]+", query) if len(t) > 2}
    print(f"🔍 Query-Tokens für Bewertung: {q_tokens}")

    def score(item: dict) -> Tuple[int, int]:
        url = item.get("link") or item.get("url") or ""
        dom = _domain(url)
        if dom in EXCLUDE_DOMAINS:
            return (-100, 9999)
        # Domain enthält einen der Query-Tokens?
        dom_tokens = set(re.findall(r"[\w\-]+", dom))
        hit = len(q_tokens.intersection(dom_tokens))
        plen = _path_len(url)
        return (hit, -plen)

    best = max(results, key=score)
    best_url = best.get("link") or best.get("url")
    print(f"🎯 Beste URL ausgewählt: {best_url}")
    return norm_base_url(best_url) if best_url else None


# --------------------------------------------------------------------------------------
# Sitemap-Ermittlung & -Rekursion
# --------------------------------------------------------------------------------------


def prioritize_sitemap_urls(urls: List[str]) -> List[str]:
    """Priorisiert Sitemap-URLs nach Standard-Konventionen.
    
    Priorität (höchste zuerst):
    1. page-sitemap.xml (Hauptseiten-Sitemap) ⭐
    2. sitemap_index.xml (Standard-Index)
    3. sitemap.xml (Standard-Sitemap)
    4. sitemapindex.xml (Alternative)
    5. Andere Varianten
    """
    if len(urls) <= 1:
        return urls
    
    def get_sitemap_priority(url: str) -> int:
        try:
            filename = url.split('/')[-1].lower()
            if 'page-sitemap' in filename or filename == 'page-sitemap.xml':
                return 110  # Höchste Priorität für Hauptseiten
            elif filename == 'sitemap_index.xml':
                return 100  # Standard-Index
            elif filename == 'sitemap.xml':
                return 90
            elif filename == 'sitemapindex.xml':
                return 80
            elif 'index' in filename:
                return 70
            else:
                return 60
        except Exception:
            return 50
    
    # Sortiere nach Priorität (höchste zuerst)
    prioritized = sorted(urls, key=get_sitemap_priority, reverse=True)
    return prioritized


def find_sitemaps(base_url: str) -> List[str]:
    urls: List[str] = []
    # 1) robots.txt nach Sitemap: Zeilen durchsuchen
    try:
        robots_url = urljoin(base_url + "/", "robots.txt")
        if robots_allowed(base_url, robots_url):
            _rate_sleep()
            rr = SESSION.get(robots_url, timeout=(3, 10))
            if rr.status_code == 200:
                for line in rr.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sm = line.split(":", 1)[1].strip()
                        if sm:
                            urls.append(sm)
    except Exception:
        pass
    # 2) Fallback-Pfade - Standard-Varianten in Prioritäts-Reihenfolge
    if not urls:
        fallback_paths = ["/sitemap_index.xml", "/sitemap.xml", "/sitemapindex.xml"]
        for path in fallback_paths:
            urls.append(base_url + path)
    
    # 3) Duplikate entfernen (order-preserving)
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    
    # 4) Nach Standard-Priorität sortieren
    prioritized = prioritize_sitemap_urls(deduped)
    
    return prioritized



def filter_relevant_sitemaps(sitemaps: List[dict]) -> List[dict]:
    """Filtert aus einer Liste von Sitemaps nur die für Hauptseiten relevanten heraus.
    
    Bevorzugt: page, main, content, general sitemaps
    Ausgeschlossen: job, career, news, blog, product catalogs etc.
    """
    # Priorität: höhere Zahlen = wichtiger
    SITEMAP_PRIORITIES = {
        # Hoch relevante Sitemaps (Hauptseiten)
        'page': 120,  # Höchste Priorität für page-sitemap.xml
        'main': 90,
        'content': 80,
        'general': 70,
        'index': 60,
        'site': 50,
        
        # Mittel relevante Sitemaps
        'about': 40,
        'company': 35,
        'contact': 30,
        'service': 25,
        
        # Niedrig relevante / auszuschließende Sitemaps
        'job': -100,
        'jobs': -100,
        'career': -100,
        'careers': -100,
        'news': -50,
        'blog': -50,
        'article': -50,
        'product': -30,
        'shop': -30,
        'catalog': -30,
    }
    
    def get_sitemap_priority(sitemap_url: str) -> int:
        """Bewertet eine Sitemap-URL nach Relevanz für Unternehmensinfo"""
        url_lower = sitemap_url.lower()
        
        # Extrahiere den Dateinamen ohne Pfad und Endung
        filename = url_lower.split('/')[-1].replace('.xml', '').replace('-sitemap', '').replace('_sitemap', '')
        
        # Prüfe auf bekannte Muster
        for pattern, priority in SITEMAP_PRIORITIES.items():
            if pattern in filename:
                return priority
                
        # Fallback: wenn keine spezifischen Muster, moderate Priorität
        return 10
    
    # Bewerte und sortiere Sitemaps
    sitemap_scores = []
    for sitemap in sitemaps:
        loc = sitemap.get('loc', '')
        if loc:
            priority = get_sitemap_priority(loc)
            sitemap_scores.append((priority, sitemap))
    
    # Sortiere nach Priorität (höchste zuerst) und nimm nur positive Scores
    sitemap_scores.sort(key=lambda x: x[0], reverse=True)
    relevant_sitemaps = [sitemap for score, sitemap in sitemap_scores if score > 0]
    
    # Begrenze auf maximal 3 relevante Sitemaps um Performance zu schonen
    return relevant_sitemaps[:3]


def iter_sitemap_locs(url: str, depth: int = 0, max_depth: int = SITEMAP_MAX_DEPTH) -> List[str]:
    if depth > max_depth:
        return []
    try:
        _rate_sleep()
        # Explizit GZIP-Dekomprimierung aktivieren durch Accept-Encoding Header
        headers = {
            'Accept': 'application/xml,text/xml,*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'User-Agent': USER_AGENT
        }
        r = SESSION.get(url, timeout=(3, 10), headers=headers)
        r.raise_for_status()
        
        if DEBUG:
            print(f"   📄 Content-Type: {r.headers.get('Content-Type', 'Unbekannt')}")
            print(f"   📦 Content-Encoding: {r.headers.get('Content-Encoding', 'Keine')}")
            print(f"   📏 Content-Length: {len(r.content)} bytes")
            
    except Exception as e:
        if DEBUG:
            print(f"   ❌ HTTP-Fehler für {url}: {e}")
        return []
    
    try:
        # Robuste Dekomprimierung: Verschiedene Ansätze probieren
        content = None
        encoding = r.headers.get('Content-Encoding', '').lower()
        
        if DEBUG:
            print(f"   🔍 Dekomprimiere Content (Encoding: {encoding})...")
        
        # Ansatz 1: requests automatische Dekomprimierung (r.text)
        if r.text and len(r.text.strip()) > 0:
            content = r.text
            if DEBUG:
                print(f"   ✅ Ansatz 1 (r.text): {len(content)} Zeichen dekomprimiert")
        
        # Ansatz 2: Manuelle Dekomprimierung falls nötig  
        if not content or not content.strip():
            if encoding == 'br':
                try:
                    import brotli
                    content = brotli.decompress(r.content).decode('utf-8', errors='ignore')
                    if DEBUG:
                        print(f"   ✅ Ansatz 2 (brotli): {len(content)} Zeichen dekomprimiert")
                except (ImportError, Exception) as br_err:
                    if DEBUG:
                        print(f"   ⚠️ Brotli-Dekomprimierung fehlgeschlagen: {br_err}")
            elif encoding in ['gzip', 'deflate']:
                try:
                    import gzip
                    content = gzip.decompress(r.content).decode('utf-8', errors='ignore')
                    if DEBUG:
                        print(f"   ✅ Ansatz 2 (gzip): {len(content)} Zeichen dekomprimiert")
                except Exception as gz_err:
                    if DEBUG:
                        print(f"   ⚠️ GZIP-Dekomprimierung fehlgeschlagen: {gz_err}")
        
        # Ansatz 3: Raw content als UTF-8 (falls keine Komprimierung)
        if not content or not content.strip():
            content = r.content.decode('utf-8', errors='ignore')
            if DEBUG:
                print(f"   ✅ Ansatz 3 (raw): {len(content)} Zeichen")
        
        # Debug: Zeige ersten Teil des Contents
        if DEBUG and content:
            preview = content[:200].replace('\n', '\\n').replace('\r', '\\r')
            print(f"   📄 Content-Preview: {preview}...")
        
        # XML parsen
        if not content or not content.strip():
            if DEBUG:
                print(f"   ❌ Kein Content zum Parsen verfügbar")
            return []
            
        data = xmltodict.parse(content)
        
        if DEBUG:
            print(f"   ✅ XML erfolgreich geparst, Root-Keys: {list(data.keys())}")
            
    except Exception as e:
        if DEBUG:
            print(f"   ❌ XML-Parsing-Fehler für {url}: {e}")
            if content:
                print(f"   🔍 Content-Länge: {len(content)}, Erste 100 Zeichen: {content[:100]}")
        return []

    locs: List[str] = []
    if "sitemapindex" in data:
        sitems = data["sitemapindex"].get("sitemap", [])
        if isinstance(sitems, dict):
            sitems = [sitems]
            
        # Intelligente Sitemap-Filterung nur auf oberster Ebene (depth=0)
        if depth == 0:
            print(f"   🔍 Sitemap-Index gefunden mit {len(sitems)} Einträgen")
            relevant_sitems = filter_relevant_sitemaps(sitems)
            print(f"   📌 {len(relevant_sitems)} relevante Sitemaps ausgewählt:")
            for i, sitemap in enumerate(relevant_sitems, 1):
                sitemap_url = sitemap.get('loc', 'Unbekannt')
                filename = sitemap_url.split('/')[-1] if sitemap_url != 'Unbekannt' else 'Unbekannt'
                if i == 1 and 'page-sitemap' in filename.lower():
                    print(f"      • {filename} 🎯 (Hauptseiten-Priorität)")
                else:
                    print(f"      • {filename}")
            sitems = relevant_sitems
        
        for s in sitems:
            loc = (s or {}).get("loc")
            if loc:
                locs.extend(iter_sitemap_locs(loc, depth + 1, max_depth))
    elif "urlset" in data:
        uitems = data["urlset"].get("url", [])
        if isinstance(uitems, dict):
            uitems = [uitems]
        for u in uitems:
            loc = (u or {}).get("loc")
            if loc:
                locs.append(loc)
    return locs


# --------------------------------------------------------------------------------------
# Robuste Contact-/Info-URL-Filterung (Regex mit Varianten)
# --------------------------------------------------------------------------------------
# Sprachpräfix-Definitionen
LANG_PREFIX_GERMAN = r"(?:/(?:de|de-de|de_at|de-ch))?"  # Deutsche Varianten
LANG_PREFIX_OTHER = r"(?:/(?:en|fr|es|it|en-gb|en-us|fr-fr|es-es))?"  # Andere Sprachen
SEG_END = r"(?:/|$|\\.html|\\.htm)"
# Flexibles Suffix-Pattern für Unternehmensnamen (z.B. "-variolytics", "-company", "_firma")
COMPANY_SUFFIX = r"(?:[-_][\w\-]+)?"

# Robuste Kernmuster inkl. Umlaut-/ASCII-Varianten, Synonyme UND Unternehmenssuffixe
# WICHTIG: Fokus auf geschäftsrelevante Informationen, keine Datenschutz-Seiten
CONTACT_PATTERNS = [
    # KONTAKT: Alle Formen von Kontaktaufnahme und Kundenservice
    rf"^{LANG_PREFIX_GERMAN}/?(kontakt|kontaktformular|kontaktieren|anfrage|anfragen|erreichen|schreiben|nachricht|email|telefon|hotline|kundenservice|kundendienst|support|hilfe|beratung|service|contact|contact-us|get-in-touch|reach-us|write-us){COMPANY_SUFFIX}{SEG_END}",
    
    # IMPRESSUM & RECHTLICHES: Alle rechtlichen Informationen
    rf"^{LANG_PREFIX_GERMAN}/?(impressum|imprint|legal-notice|legal|disclaimer|rechtliches|rechtliche-hinweise|agb|allgemeine-geschaeftsbedingungen|allgemeine-geschäftsbedingungen|terms|terms-of-service|terms-conditions|nutzungsbedingungen|geschaeftsbedingungen|geschäftsbedingungen){COMPANY_SUFFIX}{SEG_END}",
    
    # ÜBER UNS: Alle Formen der Unternehmensvorstellung
    rf"^{LANG_PREFIX_GERMAN}/?(ueber-uns|über-uns|uber-uns|unternehmen|historie|geschichte|philosophie|vision|mission|werte|leitbild|firma|betrieb|organisation|corporate|wir|portrait|porträt|about|about-us|who-we-are|company|profil|firmenprofil|unternehmensportraet|unternehmensportrait|firmengeschichte|firmenphilosophie){COMPANY_SUFFIX}{SEG_END}",
    
    # TEAM: Alle Formen der Personalvorstellung
    rf"^{LANG_PREFIX_GERMAN}/?(team|teams|mitarbeiter|mitglieder|kollegen|belegschaft|personal|führung|fuehrung|geschäftsleitung|geschaeftsleitung|geschaeftsfuehrung|geschäftsführung|führungsteam|fuehrungsteam|management|leitung|vorstand|organigramm|organisation|experten|fachkräfte|fachkraefte|crew|staff|partner|ansprechpartner|ansprechpersonen|kontaktpersonen|unser-team|our-team|who-is-who){COMPANY_SUFFIX}{SEG_END}",
    
    # STANDORTE: Alle Formen der Standort-/Adressinformationen  
    rf"^{LANG_PREFIX_GERMAN}/?(standorte|standort|büro|buero|office|offices|niederlassungen|filialen|zentrale|hauptsitz|hauptstandort|adresse|adressen|kontaktdaten|wo-finden-sie-uns|anfahrt|wegbeschreibung|locations|location|find-us|directions|map|maps|lageplan){COMPANY_SUFFIX}{SEG_END}",
]

CONTACT_REGEXES = [re.compile(p, re.IGNORECASE) for p in CONTACT_PATTERNS]



def is_foreign_language_url(url: str) -> bool:
    """Prüft ob eine URL anderssprachig ist und ausgeschlossen werden soll.
    
    Schließt URLs mit expliziten Sprachpräfixen aus: /en/, /fr/, /es/, etc.
    Deutsche URLs (/de/) und URLs ohne Sprachpräfix werden NICHT ausgeschlossen.
    """
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return False
    
    # Liste der auszuschließenden Sprachpräfixe (alles außer Deutsch)
    FOREIGN_LANGUAGE_PREFIXES = [
        '/en/', '/en-gb/', '/en-us/',  # Englisch
        '/fr/', '/fr-fr/',             # Französisch  
        '/es/', '/es-es/',             # Spanisch
        '/it/', '/it-it/',             # Italienisch
        '/nl/', '/nl-nl/',             # Niederländisch
        '/pt/', '/pt-pt/', '/pt-br/',  # Portugiesisch
        '/pl/', '/pl-pl/',             # Polnisch
        '/ru/', '/ru-ru/',             # Russisch
        '/zh/', '/zh-cn/', '/zh-tw/',  # Chinesisch
        '/ja/', '/ja-jp/',             # Japanisch
        '/ko/', '/ko-kr/',             # Koreanisch
    ]
    
    path_lower = path.lower()
    
    # Prüfe ob der Pfad mit einem der Fremdsprachen-Präfixe beginnt
    for prefix in FOREIGN_LANGUAGE_PREFIXES:
        if path_lower.startswith(prefix):
            return True
    
    return False


def get_url_priority(url: str) -> int:
    """Bewertet eine URL nach Relevanz.
    
    Da anderssprachige URLs bereits ausgeschlossen sind, 
    fokussieren wir auf Content-Typ und deutsche Sprachvarianten.
    """
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return 0
    
    path_lower = path.lower()
    
    # Sprach-Bonus: Deutsche URLs oder Standard-URLs (ohne Sprachpräfix)
    if re.match(r'^(?:/(?:de|de-de|de_at|de-ch))?/', path, re.IGNORECASE):
        language_bonus = 100  # Deutsche URLs oder Standard
    else:
        language_bonus = 75   # Fallback (sollte nicht auftreten, da anderssprachige URLs ausgeschlossen sind)
    
    # Content-Typ Bewertung mit erweiterten Begriffen
    base_score = 60  # Fallback-Wert
    
    # IMPRESSUM & RECHTLICHES (höchste Priorität)
    if any(term in path_lower for term in ['impressum', 'imprint', 'legal', 'rechtlich']):
        base_score = 95
        
    # KONTAKT (sehr hohe Priorität)  
    elif any(term in path_lower for term in ['kontakt', 'contact', 'anfrage', 'erreichen', 'schreiben', 'nachricht', 'hotline', 'kundenservice', 'support', 'hilfe', 'beratung', 'service']):
        base_score = 90
        
    # TEAM & PERSONAL (hohe Priorität)
    elif any(term in path_lower for term in ['team', 'mitarbeiter', 'personal', 'führung', 'fuehrung', 'geschäftsleitung', 'geschaeftsleitung', 'management', 'leitung', 'staff', 'crew', 'organigramm', 'experten', 'ansprechpartner', 'ansprechpersonen', 'kontaktpersonen', 'unser-team', 'our-team', 'who-is-who', 'team-mitarbeiter', 'team-mitglieder', 'team-kollegen', 'team-belegschaft', 'team-personal', 'team-führung', 'team-fuehrung', 'team-geschäftsleitung', 'team-geschaeftsleitung', 'team-management', 'team-leitung', 'team-staff', 'team-crew', 'team-organigramm', 'team-experten', 'team-ansprechpartner', 'team-ansprechpersonen', 'team-kontaktpersonen', 'team-unser-team', 'team-our-team', 'team-who-is-who']):
        base_score = 95
        
    # ÜBER UNS & UNTERNEHMEN (wichtig)
    elif any(term in path_lower for term in ['ueber', 'über', 'uber', 'about', 'unternehmen', 'firma', 'company', 'profil', 'historie', 'geschichte', 'vision', 'mission', 'werte', 'philosophie', 'portrait', 'porträt', 'unternehmensportrait', 'unternehmensportraet', 'firmengeschichte', 'firmenphilosophie']):
        base_score = 95
    
    # Dienstleistungen & Produkte (wichtig)
    elif any(term in path_lower for term in ['dienstleistungen', 'produkte', 'leistungen', 'service', 'produkt', 'dienst', 'leistung', 'dienstleistung', 'produktleistung', 'produktdienstleistung', 'produktdienst', 'dienstleistung', 'produktleistung', 'produktdienstleistung', 'produktdienst']):
        base_score = 95

    # STANDORTE & ADRESSEN (mittel wichtig)
    elif any(term in path_lower for term in ['standort', 'location', 'büro', 'buero', 'office', 'adresse', 'zentrale', 'hauptsitz', 'niederlassung', 'anfahrt', 'wegbeschreibung', 'finden', 'find']):
        base_score = 75
    
    return language_bonus + base_score


def filter_urls(base_url: str, urls: List[str]) -> List[str]:
    base = norm_base_url(base_url)
    candidates: List[Tuple[int, str]] = []
    seen = set()
    excluded_count = 0

    # Basis-URL immer mitnehmen (höchste Priorität)
    candidates.append((300, base))
    seen.add(base)

    for u in urls:
        if not same_domain(base, u):
            continue
        try:
            up = urlparse(u)
            path = up.path or "/"
        except Exception:
            continue
        
        # Normalisierung: Basis + Pfad, Query/Fragmente verwerfen
        norm = urlunparse(("https", urlparse(base).netloc, path.rstrip("/"), "", "", "")) or u
        if norm in seen:
            continue
            
        # ❌ AUSSCHLUSS: Anderssprachige URLs komplett ausschließen
        if is_foreign_language_url(norm):
            excluded_count += 1
            if DEBUG and excluded_count <= 5:  # Zeige nur erste 5 ausgeschlossene URLs
                excluded_path = norm.replace(base, '') or '/'
                print(f"   🚫 Ausgeschlossen (Fremdsprache): {excluded_path}")
            continue
            
        # ✅ Prüfe ob URL einem Relevanz-Pattern entspricht
        if any(rx.search(path) for rx in CONTACT_REGEXES):
            priority = get_url_priority(norm)
            candidates.append((priority, norm))
            seen.add(norm)

    # Sortiere nach Priorität (höchste zuerst) und nimm die besten URLs
    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = [url for priority, url in candidates[:MAX_PAGES_TO_SUMMARIZE]]
    
    # Informative Ausgabe
    if excluded_count > 0:
        print(f"   🚫 {excluded_count} anderssprachige URLs ausgeschlossen")
    
    print(f"   📋 URL-Priorisierung (Top {len(chosen)}):")
    for i, (priority, url) in enumerate(candidates[:MAX_PAGES_TO_SUMMARIZE], 1):
        path = url.replace(base, '') or '/'
        lang = "🇩🇪" if priority >= 150 else "🌐"
        print(f"      {i}. {lang} {path} (Priorität: {priority})")

    return chosen


# --------------------------------------------------------------------------------------
# Text-Extraktion (deterministisch) und Zusammenfassung (LLM)   ########## MARKDOWN-TOOL-INTEGRATION ###########
# --------------------------------------------------------------------------------------


def extract_social_media_links(html: str) -> str:
    """Extrahiert Social Media Links (besonders LinkedIn) aus HTML"""
    social_links = []
    
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        
        # Finde alle Links
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link['href'].lower()
            # LinkedIn Company/Unternehmens-Profile
            if 'linkedin.com/company/' in href or 'linkedin.com/in/' in href:
                # Vollständige URL rekonstruieren falls relativ
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    continue  # relative LinkedIn-Links ignorieren
                
                # Bereinigen (Parameter entfernen)
                clean_url = href.split('?')[0].split('#')[0]
                if clean_url not in [link.lower() for link in social_links]:
                    social_links.append(clean_url)
            
            # Weitere Social Media (optional erweitern)
            # elif 'twitter.com/' in href or 'x.com/' in href:
            # elif 'facebook.com/' in href:
    except Exception:
        pass
    
    if social_links:
        return f"\n\n**GEFUNDENE SOCIAL MEDIA LINKS:**\n" + "\n".join(f"- {link}" for link in social_links)
    return ""


def extract_text(html: str) -> str:
    """Extrahiert reinen, kompakten Text aus HTML.
    Bevorzugt trafilatura; Fallbacks entfernen Skripte/Styles/Inline-Bilder (data: URIs)."""
    # Zuerst Social Media Links extrahieren
    social_media_section = extract_social_media_links(html)
    
    # bevorzugt trafilatura
    try:
        import trafilatura
        txt = trafilatura.extract(html, favor_recall=True, include_links=False)
        if txt and txt.strip():
            cleaned = re.sub(r"\s+", " ", txt).strip()
            return (cleaned + social_media_section).strip()
    except Exception:
        pass
    
    # Fallback readability → HTML zusammenfassen, dann in Text umwandeln
    try:
        from readability import Document
        doc = Document(html)
        base_html = (doc.summary(html_partial=False) or html)
    except Exception:
        base_html = html
    
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(base_html, 'html.parser')
        # Entferne störende/gewichtige Elemente
        for tag in ["script", "style", "noscript", "svg", "iframe", "video", "picture", "source", "canvas"]:
            for el in soup.find_all(tag):
                el.decompose()
        # Entferne <img> komplett und jegliche data: URIs
        for img in soup.find_all("img"):
            try:
                img.decompose()
            except Exception:
                pass
        # Entferne alle Attribute mit data:-URIs, falls vorhanden
        for el in soup.find_all(True):
            attrs = getattr(el, "attrs", {}) or {}
            for k, v in list(attrs.items()):
                try:
                    if isinstance(v, str) and v.strip().lower().startswith("data:"):
                        del el.attrs[k]
                except Exception:
                    pass
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return (text + social_media_section).strip()
    except Exception:
        # allerletzter Fallback: roher Text aus Original-HTML
        try:
            soup2 = BeautifulSoup(html, 'html.parser')
            text2 = re.sub(r"\s+", " ", soup2.get_text(" ", strip=True)).strip()
            return (text2 + social_media_section).strip()
        except Exception:
            return (html + social_media_section)[:5000]



def summarize_text(text: str) -> str:              # LLM-Call für Zusammenfassung des Website Inhalts
    # Sicherheitsbegrenzungen für Eingabelänge
    MAX_INPUT_CHARS = 50000
    CHUNK_SIZE = 5000
    OVERLAP = 200

    def _chunk_text(t: str) -> List[str]:
        if len(t) <= CHUNK_SIZE:
            return [t]
        chunks: List[str] = []
        start = 0
        while start < len(t):
            end = min(len(t), start + CHUNK_SIZE)
            chunks.append(t[start:end])
            if end == len(t):
                break
            start = end - OVERLAP
        return chunks

    # Text vorverarbeiten/trimmen
    base_text = re.sub(r"\s+", " ", (text or "")).strip()
    if not base_text:
        return ""

    # Wenn sehr lang: in Teile zusammenfassen und anschließend eine Meta-Zusammenfassung bilden
    if len(base_text) > MAX_INPUT_CHARS:
        parts = _chunk_text(base_text)
        partial_summaries: List[str] = []
        for idx, part in enumerate(parts, 1):
            try:
                system_prompt = SystemMessage(content=(
"""Du bist ein Experte für Unternehmensrecherche. Fasse präzise nur relevante Fakten zusammen.
Wenn vorhanden, fokussiere: 1) Geschäftsführung/Leitung, 2) Leistungen/Produkte, 3) Teamgröße, 4) LinkedIn, 5) Impressum/Kontakt."""
                ))
                user_prompt = HumanMessage(content=part)
                resp = llm.invoke([system_prompt, user_prompt])
                partial_summaries.append(resp.content.strip())
            except Exception:
                partial_summaries.append(part[:1500])
        # Meta-Zusammenfassung der Teilzusammenfassungen
        try:
            system_prompt2 = SystemMessage(content=(
"""Fasse die folgenden Teilsummaries zu einer kurzen, strukturierten Übersicht zusammen (nur Fakten, keine Wiederholungen)."""
            ))
            user_prompt2 = HumanMessage(content="\n\n".join(partial_summaries)[:MAX_INPUT_CHARS])
            resp2 = llm.invoke([system_prompt2, user_prompt2])
            return resp2.content
        except Exception:
            return "\n\n".join(partial_summaries)[:2000]

    # Normale (nicht zu lange) Eingabe direkt zusammenfassen
    system_prompt = SystemMessage(content=(
"""Du bist ein Experte für Unternehmensrecherche.
<Aufgabe>
Fasse die relevanten Informationen des Unternehmens präzise und strukturiert zusammen.
Wenn vorhanden, extrahiere folgende Punkte (in der Reihenfolge):
1. Geschäftsführer / Leitung / Partner

2. Dienstleistungen / Produkte / Was macht das Unternehmen?

3. Mitarbeiteranzahl / Teamgröße

4. LinkedIn-Link des Unternehmens

5. Impressum / Kontaktinformationen
</Aufgabe>

<Ausgabeformat>
Format:

Nutze klare Überschriften für jede Kategorie.

Falls eine Information nicht auffindbar ist, gebe für diese Information einen leeren String zurück.
</Ausgabeformat>"""
    ))
    user_prompt = HumanMessage(content=base_text)
    try:
        resp = llm.invoke([system_prompt, user_prompt])
        return resp.content
    except Exception:
        return base_text[:2000]


# --------------------------------------------------------------------------------------
# Seiten-Fetch mit robots.txt-Respekt und Rate-Limit
# --------------------------------------------------------------------------------------


def fetch_url_text(base_url: str, url: str) -> Optional[str]:
    try:
        if not robots_allowed(base_url, url):
            if DEBUG:
                print(f"Robots disallow: {url}")
            return None
        _rate_sleep()
        # Primär: Markdown-Tool verwenden, das intern robust rendert/fetched
        if scrape_website_to_markdown is not None:
            try:
                md = scrape_website_to_markdown(url)
                if md and md.strip():
                    return md.strip()
            except Exception as md_err:
                if DEBUG:
                    print(f"Markdown-Tool fehlgeschlagen für {url}: {md_err}")
        # Fallback: klassisches HTTP + Extraktion
        r = SESSION.get(url, timeout=(3, 15))
        r.raise_for_status()
        return extract_text(r.text)
    except Exception as e:
        if DEBUG:
            print(f"Fehler beim Laden {url}: {e}")
        return None


# --------------------------------------------------------------------------------------
# Hauptfunktion
# --------------------------------------------------------------------------------------
class ToolState(TypedDict):
    messages: str



def company_website_scraper(query: str) -> AIMessage:
    """Deterministischer Website-Scraper für Unternehmensrecherche.
    Ablauf:
    1) Firmendomäne bestimmen (Google Search, heuristische Auswahl)
    2) robots.txt lesen und Sitemaps ermitteln (deterministisch)
    3) Sitemaps rekursiv parsen (bis Depth=2) und alle <loc> einsammeln
    4) URLs auf gleiche Domäne + Contact/Info-Pattern filtern
    5) Seiten (parallel) laden unter Respekt von robots.txt und Rate-Limit
    6) Text extrahieren (trafilatura/readability), nur dann LLM zum Summarizen
    """
    print(f"🔍 SCHRITT 1: Suche nach Homepage für Query: '{query}'")
    
    # Für Homepage-Suche nur den Firmennamen verwenden, nicht die PLZ
    company_name = query.split(" AND ")[0].strip() if " AND " in query else query
    print(f"🔍 Vereinfachte Query für Homepage-Suche: '{company_name}'")
    
    try:
        base_url = select_company_homepage_from_brave(company_name) or ""
        if not base_url:
            print("❌ Keine Homepage gefunden!")
            return AIMessage(content="Es konnte keine Unternehmens-Homepage ermittelt werden.")

        print(f"✅ Homepage gefunden: {base_url}")
        print(f"\n🤖 SCHRITT 2: Analysiere Website-Struktur...")

        # Sitemaps ermitteln
        print(f"🔍 Suche nach Sitemaps in robots.txt und Standardpfaden...")
        sitemap_urls = find_sitemaps(base_url)
        
        if sitemap_urls:
            print(f"📋 Gefundene Sitemaps ({len(sitemap_urls)}):")
            for i, sm in enumerate(sitemap_urls, 1):
                filename = sm.split('/')[-1].lower()
                if i == 1 and len(sitemap_urls) > 1:
                    if 'page-sitemap' in filename:
                        print(f"   {i}. {sm} 🎯 (Hauptseiten-Priorität)")
                    else:
                        print(f"   {i}. {sm} ⭐ (Standard-Priorität)")
                else:
                    print(f"   {i}. {sm}")
        else:
            print(f"⚠️ Keine Sitemaps gefunden - verwende nur Homepage")
        
        all_locs: List[str] = []
        for i, sm in enumerate(sitemap_urls, 1):
            print(f"🔄 Analysiere Sitemap: {sm}")
            try:
                locs = iter_sitemap_locs(sm, 0, SITEMAP_MAX_DEPTH)
                if locs:
                    all_locs.extend(locs)
                    print(f"   ✅ {len(locs)} URLs erfolgreich extrahiert")
                    
                    # Nach erfolgreicher erster Sitemap die anderen ignorieren
                    remaining_count = len(sitemap_urls) - i
                    if remaining_count > 0:
                        print(f"   🎯 Erste Sitemap erfolgreich - ignoriere {remaining_count} weitere Sitemaps")
                        skipped_sitemaps = sitemap_urls[i:]
                        for j, skipped in enumerate(skipped_sitemaps):
                            filename = skipped.split('/')[-1]
                            # Zeige nur die ersten 3 übersprungenen Sitemaps
                            if j < 3:
                                print(f"      ⏭️ Übersprungen: {filename}")
                            elif j == 3 and len(skipped_sitemaps) > 3:
                                print(f"      ⏭️ ... und {len(skipped_sitemaps) - 3} weitere")
                    break
                else:
                    print(f"   ⚠️ Sitemap ist leer oder nicht lesbar - versuche nächste")
            except Exception as e:
                print(f"   ❌ Fehler beim Parsen: {str(e)[:100]} - versuche nächste")
        
        print(f"📄 Gesamt URLs aus allen Sitemaps: {len(all_locs)}")

        # Filtern auf relevante Seiten  
        print(f"🎯 Filtere URLs nach Relevanz-Kriterien...")
        print(f"   • Nur gleiche Domain wie {_domain(base_url)}")
        print(f"   • URLs mit Kontakt/Impressum/About-Pattern")
        print(f"   • Maximale Pfadtiefe begrenzt")
        
        important_urls = filter_urls(base_url, all_locs)
        
        if important_urls:
            print(f"📌 {len(important_urls)} wichtige URLs identifiziert:")
            for i, url in enumerate(important_urls, 1):
                path = url.replace(base_url, '') or '/'
                print(f"   {i}. {path}")
        else:
            print(f"⚠️ Keine relevanten URLs gefiltert - verwende nur Homepage")
        
        print(f"🔒 Robots.txt Compliance wird bei jedem Abruf geprüft")
        
        print(f"\n🔄 SCHRITT 3: Lade und analysiere {len(important_urls)} Seiten...")

        # Parallel laden und zusammenfassen
        from concurrent.futures import ThreadPoolExecutor, as_completed
        summaries: List[str] = []

        def process(u: str) -> Optional[str]:
            path = u.replace(base_url, '') or '/'
            print(f"   🔄 Lade {path}...")
            
            # Robots.txt Check
            if not robots_allowed(base_url, u):
                print(f"   🚫 {path}: Von robots.txt blockiert")
                return None
            
            text = fetch_url_text(base_url, u)
            if not text:
                print(f"   ❌ {path}: Konnte nicht geladen werden (Netzwerk/Parsing-Fehler)")
                return None
                
            print(f"   ✅ {path}: {len(text)} Zeichen Text extrahiert")
            
            # LLM Zusammenfassung
            print(f"   🤖 {path}: Erstelle KI-Zusammenfassung...")
            summary = summarize_text(text)
            print(f"   📝 {path}: Zusammenfassung fertig ({len(summary)} Zeichen)")
            
            return f"## Zusammenfassung von: {u}\n\n{summary}"

        print(f"⚡ Parallel-Verarbeitung mit {min(MAX_WORKERS, len(important_urls) or 1)} Threads...")
        
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(important_urls) or 1)) as ex:
            futures = [ex.submit(process, u) for u in important_urls]
            completed = 0
            for fut in as_completed(futures):
                completed += 1
                res = fut.result()
                if res:
                    summaries.append(res)
                print(f"   📊 Fortschritt: {completed}/{len(important_urls)} Seiten verarbeitet")

        print(f"\n📊 SCHRITT 4: Finale Auswertung...")
        print(f"✅ Erfolgreich analysierte Seiten: {len(summaries)}/{len(important_urls)}")
        
        if not summaries:
            print("❌ Keine verwertbaren Informationen extrahiert")
            final_summary_text = "Es konnten keine Informationen von der Website extrahiert werden."
        else:
            final_summary_text = "\n\n---\n\n".join(summaries)
            print(f"📄 Finaler Report: {len(final_summary_text)} Zeichen")
            
            # Qualitäts-Indikatoren
            if len(final_summary_text) > 2000:
                print("🎯 Hohe Datenqualität: Umfassende Informationen extrahiert")
            elif len(final_summary_text) > 500:
                print("✅ Gute Datenqualität: Basis-Informationen extrahiert")
            else:
                print("⚠️ Begrenzte Datenqualität: Wenige Informationen extrahiert")

        return AIMessage(content=final_summary_text)

    except Exception as e:
        return AIMessage(content=f"Fehler: {e}")







### DAS MUSS HIER STEHEN BLEIBEN ###
    # if not google_api_key:
    #     print("❌ Google Search API Key nicht gefunden")
    #     return None
    
    # print(f"🔍 Google Search für: '{query}'")
    # try:
    #     _rate_sleep()
    #     r = SESSION.get(
    #         "https://www.searchapi.io/api/v1/search",
    #         headers={
    #             "Accept": "application/json",
    #             "Authorization": f"Bearer {google_api_key}",
    #             "Accept-Encoding": "identity",  # Keine Komprimierung
    #         },
    #         params={
    #             "engine": "google",
    #             "q": query,
    #             "num": 10,
    #             "gl": "de",
    #             "hl": "de",
    #             "safe": "off",
    #             "lr": "lang_de",
    #             "device": "desktop",
    #         },
    #         timeout=(3, 10),
    #     )