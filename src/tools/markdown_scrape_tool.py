import re
import html2text
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    sync_playwright = None
    class PlaywrightTimeoutError(Exception):
        pass


def _create_retrying_session() -> requests.Session:
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _fetch_html(url: str, max_bytes: int = 10 * 1024 * 1024, timeout: tuple = (10, 30)) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    session = _create_retrying_session()
    resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)

    if resp.status_code != 200:
        raise Exception(f"Failed to fetch the URL. Status code: {resp.status_code}")

    content_type = resp.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        raise Exception(f"Unsupported Content-Type: {content_type}")

    content_length = resp.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise Exception(f"Content too large (> {max_bytes} bytes)")
        except ValueError:
            pass

    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    text = resp.text

    if len(text.encode(resp.encoding or "utf-8", errors="ignore")) > max_bytes:
        raise Exception(f"Downloaded content exceeds size limit of {max_bytes} bytes")

    return text


def _render_with_playwright(url: str, max_time_s: int = 25) -> Optional[str]:
    if sync_playwright is None:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="de-DE",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.77 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                },
            )
            page = context.new_page()
            timeout_ms = max_time_s * 1000
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Versuche Cookie-/Consent-Dialoge zu schließen
            try:
                # Häufige Buttons/Labels in DACH
                selectors: List[str] = [
                    "button:has-text('Alle akzeptieren')",
                    "button:has-text('Akzeptieren')",
                    "button:has-text('Zustimmen')",
                    "button:has-text('Accept all')",
                    "button:has-text('I agree')",
                    "#onetrust-accept-btn-handler",
                    "button.ot-sdk-container",
                    "div[role='dialog'] button:has-text('OK')",
                    "button:has-text('Verstanden')",
                    "button:has-text('Einverstanden')",
                    "button:has-text('Alles akzeptieren')",
                    "#cmpbntyestxt",
                    ".cmplz-accept",
                    ".cmplz-btn.cmplz-accept",
                    ".borlabs-cookie-btn-accept-all",
                ]
                for sel in selectors:
                    try:
                        el = page.locator(sel)
                        if el.count() > 0:
                            el.first.click(timeout=1500)
                            page.wait_for_timeout(300)
                    except Exception:
                        pass
            except Exception:
                pass

            # Leichtes Scrollen, um Lazy-Load anzutriggern (mehrfach)
            try:
                for _ in range(4):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight/3)")
                    page.wait_for_timeout(500)
            except Exception:
                pass

            # Auf sichtbare Hauptinhalte warten (best-effort)
            try:
                main_selectors = [
                    "main", "article", "[role='main']", ".entry-content", ".post-content", ".page-content", "#content", ".content",
                    ".site-main", ".site-content", ".container", ".elementor", ".elementor-section", ".elementor-container", ".elementor-widget",
                    ".elementor-text-editor", ".elementor-heading-title", ".wp-block-post-content", ".wp-block-group", ".single-post", ".hentry", ".entry-title"
                ]
                for sel in main_selectors:
                    try:
                        page.wait_for_selector(sel, state="attached", timeout=2000)
                        break
                    except Exception:
                        continue
            except Exception:
                pass

            # Warte zusätzlich, bis ausreichend Text im Body steht
            try:
                for _ in range(12):
                    text_len = page.evaluate("(document.body && document.body.innerText) ? document.body.innerText.length : 0")
                    if text_len and text_len > 800:
                        break
                    page.wait_for_timeout(500)
            except Exception:
                pass

            # Zusätzlich kurz auf Netzwerkleerlauf warten
            try:
                page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass

            try:
                content = page.inner_html("body")
            except Exception:
                content = page.content()
            context.close()
            browser.close()
            return content
    except PlaywrightTimeoutError:
        return None
    except Exception:
        return None


def _remove_boilerplate_and_select_main(soup: BeautifulSoup) -> BeautifulSoup:
    # Remove obvious non-content elements
    for tag in [
        "script",
        "style",
        "noscript",
        "svg",
        "form",
        "input",
        "button",
        "iframe",
    ]:
        for el in soup.find_all(tag):
            el.decompose()

    for tag in ["header", "nav", "aside", "footer"]:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove elements by common boilerplate class/id keywords
    pattern = re.compile(
        r"cookie|consent|banner|popup|modal|newsletter|subscribe|share|advert|ads|tracking|breadcrumb|comment|sidebar|offcanvas",
        re.IGNORECASE,
    )
    for el in list(soup.find_all(True)):
        # Defensive: Robust gegen ungewöhnliche Tag-Strukturen ohne attrs-Dict
        try:
            attrs_dict = getattr(el, "attrs", None) or {}
            el_id = attrs_dict.get("id", "") or ""
            classes_val = attrs_dict.get("class", []) or []
            if isinstance(classes_val, str):
                classes_list: List[str] = [classes_val]
            else:
                classes_list = [str(c) for c in classes_val if c is not None]
            attrs = " ".join([str(el_id), " ".join(classes_list)]).strip()
        except Exception:
            attrs = ""

    
        if attrs and pattern.search(attrs):
            el.decompose()

    # Prefer main/article if available and substantial
    def text_len(node: Optional[BeautifulSoup]) -> int:
        if not node:
            return 0
        return len(re.sub(r"\s+", " ", node.get_text(" ", strip=True)))

    main = soup.find("main")
    if main and text_len(main) > 120:
        return main

    article = soup.find("article")
    if article and text_len(article) > 120:
        return article

    # Fallback: choose the densest section/div
    candidates: List = soup.find_all(["section", "div"])
    if not candidates:
        return soup

    best = max(candidates, key=text_len)
    if text_len(best) > 120:
        return best
    return soup


def _collect_section_html_from_heading(heading) -> str:
    level = int(heading.name[1]) if heading.name and heading.name.startswith("h") else 6
    html_parts: List[str] = [str(heading)]
    for sib in heading.next_siblings:
        if getattr(sib, "name", None) and re.match(r"h[1-6]", sib.name or ""):
            sib_level = int(sib.name[1])
            if sib_level <= level:
                break
        html_parts.append(str(sib))
    return "".join(html_parts)


def _extract_main_content(root: BeautifulSoup) -> str:
    """
    Extrahiert den Hauptinhalt einer Website basierend auf allgemeinen Strukturmustern.
    Funktioniert für alle Arten von Websites, nicht nur Unternehmensseiten.
    """
    # Zuerst versuchen wir strukturelle HTML-Elemente zu finden
    main_content_selectors = [
        "main",
        "article", 
        "[role='main']",
        ".main-content",
        "#main-content",
        ".content",
        "#content",
        ".post-content",
        ".entry-content",
        ".page-content",
        ".site-main", 
        ".site-content", 
        ".container",
        ".elementor", 
        ".elementor-section", 
        ".elementor-container", 
        ".elementor-widget",
        ".elementor-text-editor", 
        ".elementor-heading-title",
        ".wp-block-post-content", 
        ".wp-block-group", 
        ".single-post", 
        ".hentry", 
        ".entry-title"
    ]
    
    for selector in main_content_selectors:
        main_element = root.select_one(selector)
        if main_element and len(main_element.get_text(strip=True)) > 120:
            return str(main_element)
    
    # Fallback: Sammle alle Überschriften und deren nachfolgende Inhalte
    headings = root.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if headings:
        sections = []
        for heading in headings:
            section_html = _collect_section_html_from_heading(heading)
            # Nur Sektionen mit substantiellem Inhalt hinzufügen
            if len(re.sub(r'\s+', ' ', BeautifulSoup(section_html, 'html.parser').get_text(strip=True))) > 30:
                sections.append(section_html)
        
        if sections:
            return "\n".join(sections)
    
    # Letzter Fallback: Verwende das gesamte bereinigte Element
    return str(root)


def scrape_website_to_markdown(url: str) -> str:
    try:
        html_text = _fetch_html(url)
    except Exception as e:
        raise

    soup = BeautifulSoup(html_text, "html.parser")

    # Heuristik: Wenn sehr wenig Text oder Hinweise auf JS, Playwright-Fallback versuchen
    def _node_text_len(n) -> int:
        return len(re.sub(r"\s+", " ", n.get_text(" ", strip=True))) if n else 0

    main_candidate = _remove_boilerplate_and_select_main(soup)
    low_text = _node_text_len(main_candidate) < 200
    js_hint = "javascript" in soup.get_text(" ", strip=True).lower()

    if (low_text or js_hint):
        rendered = _render_with_playwright(url)
        if rendered:
            soup = BeautifulSoup(rendered, "html.parser")
            main_candidate = _remove_boilerplate_and_select_main(soup)

    # Domain-spezifische Auswahl für convensis.com
    domain = (urlparse(url).netloc or "").lower()
    if "convensis.com" in domain:
        extended_selectors = [
            "main", "article", "[role='main']", ".entry-content", ".post-content", ".page-content", "#content", ".content",
            ".site-main", ".site-content", "div#primary", "div#content", ".container", 
            ".elementor", ".elementor-section", ".elementor-container", ".elementor-widget", "body",
            ".elementor-text-editor", ".elementor-heading-title", ".wp-block-post-content", ".wp-block-group", ".single-post", ".hentry", ".entry-title"
        ]
        parts: List[str] = []
        for sel in extended_selectors:
            try:
                for el in soup.select(sel):
                    if el and len(el.get_text(strip=True)) > 10:
                        parts.append(str(el))
            except Exception:
                continue
        if parts:
            relevant_html = "\n".join(parts)
        else:
            relevant_html = _extract_main_content(main_candidate)
    else:
        relevant_html = _extract_main_content(main_candidate)

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False  # Tabellen oft wichtig (Preise, Leistungs übersichten)
    h.body_width = 0  # Keine Hardwraps, bessere LLM-Eingabe

    markdown_content = h.handle(relevant_html)

    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    markdown_content = re.sub(r"[ \t]+\n", "\n", markdown_content)
    markdown_content = markdown_content.strip()

    # Aggressiver Fallback für convensis.com, wenn Ergebnis zu kurz ist
    if "convensis.com" in domain and len(markdown_content) < 300:
        try:
            # Versuche den gesamten Body zu nehmen
            body = soup.select_one("body")
            if body and len(body.get_text(strip=True)) > 10:
                md2 = h.handle(str(body)).strip()
                if len(md2) > len(markdown_content):
                    markdown_content = md2
        except Exception:
            pass
        if len(markdown_content) < 300:
            # Baue Text aus Überschriften, Absätzen und Listen zusammen
            try:
                elems = soup.select("h1, h2, h3, h4, p, li, a")
                text_chunks: List[str] = []
                for e in elems:
                    t = e.get_text(" ", strip=True)
                    if len(t) > 0:
                        text_chunks.append(t)
                joined = "\n".join(text_chunks).strip()
                if len(joined) > len(markdown_content):
                    markdown_content = joined
            except Exception:
                pass

    # Fallbacks, falls nach Konvertierung nichts übrig bleibt
    if not markdown_content:
        try:
            markdown_content = h.handle(str(main_candidate))
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content).strip()
        except Exception:
            markdown_content = ""
    if not markdown_content:
        try:
            markdown_content = h.handle(str(soup))
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content).strip()
        except Exception:
            markdown_content = ""
    if not markdown_content:
        try:
            plain = soup.get_text("\n", strip=True)
            markdown_content = plain.strip()
        except Exception:
            markdown_content = ""

    return markdown_content