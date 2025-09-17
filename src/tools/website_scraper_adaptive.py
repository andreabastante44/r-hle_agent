"""
Adaptive Website Scraper für verschiedene Website-Architekturen
Erweitert den bestehenden Scraper um Flexibilität für moderne Web-Technologien
"""

import os
import re
import time
import json
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests

# Import der bestehenden Funktionalität
try:
    from .website_scraper import (
        SESSION, _rate_sleep, norm_base_url, same_domain, 
        find_sitemaps, iter_sitemap_locs, extract_text, 
        robots_allowed, MAX_PAGES_TO_SUMMARIZE
    )
except ImportError:
    # Fallback für direkten Import
    pass


class WebsiteArchitectureDetector:
    """Erkennt verschiedene Website-Architekturen und wählt passende Scraping-Strategien"""
    
    def __init__(self):
        self.architecture_patterns = {
            'spa': [
                r'react', r'vue', r'angular', r'next\.js',
                r'#/', r'hashbang', r'app\.js', r'bundle\.js'
            ],
            'wordpress': [
                r'wp-content', r'wp-includes', r'/wordpress/',
                r'wp-json', r'xmlrpc\.php'
            ],
            'drupal': [
                r'/node/', r'/drupal/', r'drupal\.js',
                r'/modules/', r'/themes/'
            ],
            'shopify': [
                r'shopify', r'myshopify\.com', r'/cart\.js',
                r'shop\.js', r'/checkout'
            ]
        }
    
    def detect_architecture(self, base_url: str) -> Dict[str, any]:
        """Analysiert Website-Architektur und gibt Strategien zurück"""
        
        try:
            _rate_sleep()
            response = SESSION.get(base_url, timeout=(5, 15))
            response.raise_for_status()
            html = response.text.lower()
        except Exception:
            return {'type': 'unknown', 'strategies': ['basic_scraping']}
        
        detected_types = []
        confidence_scores = {}
        
        for arch_type, patterns in self.architecture_patterns.items():
            matches = sum(1 for pattern in patterns if re.search(pattern, html))
            if matches > 0:
                confidence = matches / len(patterns)
                detected_types.append(arch_type)
                confidence_scores[arch_type] = confidence
        
        # Bestimme primäre Architektur
        if detected_types:
            primary_type = max(detected_types, key=lambda x: confidence_scores[x])
        else:
            primary_type = 'traditional'
        
        return {
            'type': primary_type,
            'confidence': confidence_scores.get(primary_type, 0.5),
            'detected_types': detected_types,
            'strategies': self._get_strategies_for_type(primary_type),
            'has_sitemap': self._check_sitemap_availability(base_url),
            'language': self._detect_language(html)
        }
    
    def _get_strategies_for_type(self, arch_type: str) -> List[str]:
        """Gibt geeignete Scraping-Strategien für Architektur-Typ zurück"""
        
        strategy_map = {
            'traditional': ['sitemap_crawl', 'navigation_extraction', 'pattern_matching'],
            'spa': ['navigation_extraction', 'js_rendering', 'api_discovery'],
            'wordpress': ['sitemap_crawl', 'wp_api', 'navigation_extraction'],
            'drupal': ['navigation_extraction', 'drupal_api', 'pattern_matching'],
            'shopify': ['navigation_extraction', 'shopify_api'],
            'unknown': ['navigation_extraction', 'pattern_matching', 'google_site_search']
        }
        
        return strategy_map.get(arch_type, strategy_map['unknown'])
    
    def _check_sitemap_availability(self, base_url: str) -> bool:
        """Prüft ob Sitemaps verfügbar sind"""
        try:
            sitemaps = find_sitemaps(base_url)
            return len(sitemaps) > 0
        except Exception:
            return False
    
    def _detect_language(self, html: str) -> str:
        """Erkennt primäre Sprache der Website"""
        
        # HTML lang Attribut
        lang_match = re.search(r'<html[^>]+lang=["\']([a-z]{2})', html)
        if lang_match:
            return lang_match.group(1)
        
        # Keyword-basierte Erkennung
        german_keywords = ['impressum', 'datenschutz', 'über uns', 'kontakt']
        english_keywords = ['about us', 'contact', 'privacy', 'imprint']
        
        german_count = sum(1 for kw in german_keywords if kw in html)
        english_count = sum(1 for kw in english_keywords if kw in html)
        
        return 'de' if german_count > english_count else 'en'


class AdaptiveURLDiscovery:
    """Adaptive URL-Discovery für verschiedene Website-Strukturen"""
    
    def __init__(self, detector: WebsiteArchitectureDetector):
        self.detector = detector
        
        # Erweiterte Patterns basierend auf Sprache
        self.language_patterns = {
            'de': [
                r'kontakt(?:formular)?(?:/|\.html?|$)',
                r'(?:über|ueber)[-_\s]*uns(?:/|\.html?|$)', 
                r'impressum(?:/|\.html?|$)',
                r'team(?:/|\.html?|$)',
                r'(?:geschäfts)?(?:führung|fuehrung)(?:/|\.html?|$)',
                r'standorte?(?:/|\.html?|$)',
                r'anfahrt(?:/|\.html?|$)',
                r'unternehmen(?:/|\.html?|$)'
            ],
            'en': [
                r'contact(?:[-_\s]*us)?(?:/|\.html?|$)',
                r'about(?:[-_\s]*us)?(?:/|\.html?|$)',
                r'team(?:/|\.html?|$)', 
                r'management(?:/|\.html?|$)',
                r'staff(?:/|\.html?|$)',
                r'office(?:s)?(?:/|\.html?|$)',
                r'location(?:s)?(?:/|\.html?|$)',
                r'company(?:/|\.html?|$)'
            ]
        }
    
    def discover_urls(self, base_url: str) -> List[str]:
        """Multi-Strategie URL Discovery"""
        
        arch_info = self.detector.detect_architecture(base_url)
        strategies = arch_info['strategies']
        discovered_urls = []
        
        print(f"🏗️ Website-Architektur: {arch_info['type']} (Confidence: {arch_info['confidence']:.2f})")
        print(f"📋 Verwende Strategien: {', '.join(strategies)}")
        
        for strategy in strategies:
            try:
                urls = self._execute_strategy(strategy, base_url, arch_info)
                if urls:
                    discovered_urls.extend(urls)
                    print(f"✅ {strategy}: {len(urls)} URLs gefunden")
                    
                    # Bei ausreichend URLs stoppen
                    if len(discovered_urls) >= MAX_PAGES_TO_SUMMARIZE:
                        break
                else:
                    print(f"⚠️ {strategy}: Keine URLs gefunden")
                    
            except Exception as e:
                print(f"❌ {strategy} fehlgeschlagen: {e}")
                continue
        
        return self._deduplicate_and_filter(discovered_urls, base_url, arch_info['language'])
    
    def _execute_strategy(self, strategy: str, base_url: str, arch_info: Dict) -> List[str]:
        """Führt spezifische Discovery-Strategie aus"""
        
        if strategy == 'navigation_extraction':
            return self._extract_navigation_links(base_url)
        elif strategy == 'sitemap_crawl':
            return self._crawl_sitemaps(base_url)
        elif strategy == 'pattern_matching':
            return self._pattern_based_discovery(base_url, arch_info['language'])
        elif strategy == 'google_site_search':
            return self._google_site_search(base_url, arch_info['language'])
        else:
            return []
    
    def _extract_navigation_links(self, base_url: str) -> List[str]:
        """Extrahiert Links aus Website-Navigation"""
        
        try:
            _rate_sleep()
            response = SESSION.get(base_url, timeout=(5, 15))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception:
            return []
        
        # Navigation-Selektoren (vom einfachsten zum spezifischsten)
        nav_selectors = [
            'nav a[href]',                    # HTML5 nav element
            '.navigation a[href]',            # CSS class
            '.navbar a[href]',                # Bootstrap
            '.menu a[href]',                  # Generic menu
            '[role="navigation"] a[href]',    # ARIA role
            'header a[href]',                 # Header links
            '.main-menu a[href]'              # CMS-specific
        ]
        
        found_links = []
        relevance_keywords = {
            'de': ['kontakt', 'über', 'impressum', 'team', 'unternehmen'],
            'en': ['contact', 'about', 'team', 'company', 'management']
        }
        
        for selector in nav_selectors:
            links = soup.select(selector)
            if not links:
                continue
                
            for link in links:
                href = link.get('href')
                text = link.get_text().lower().strip()
                
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                
                # Relevanz-Check basierend auf Link-Text
                is_relevant = any(
                    keyword in text 
                    for lang_keywords in relevance_keywords.values() 
                    for keyword in lang_keywords
                )
                
                if is_relevant:
                    full_url = urljoin(base_url, href)
                    if same_domain(base_url, full_url):
                        found_links.append(full_url)
            
            # Wenn Navigation-Links gefunden wurden, stoppen
            if found_links:
                break
        
        return found_links
    
    def _crawl_sitemaps(self, base_url: str) -> List[str]:
        """Sitemap-basierte URL-Discovery (bestehende Funktionalität)"""
        try:
            sitemap_urls = find_sitemaps(base_url)
            all_urls = []
            
            for sitemap_url in sitemap_urls:
                urls = iter_sitemap_locs(sitemap_url)
                all_urls.extend(urls)
            
            return all_urls
        except Exception:
            return []
    
    def _pattern_based_discovery(self, base_url: str, language: str) -> List[str]:
        """Pattern-basierte URL-Konstruktion"""
        
        patterns = self.language_patterns.get(language, self.language_patterns['en'])
        constructed_urls = []
        
        for pattern in patterns:
            # Vereinfachte URL-Konstruktion
            simple_path = re.sub(r'[^\w\-].*', '', pattern.replace(r'(?:', '').replace(r')', ''))
            if simple_path:
                test_url = urljoin(base_url + '/', simple_path)
                constructed_urls.append(test_url)
        
        # Teste URLs auf Existenz
        existing_urls = []
        for url in constructed_urls[:10]:  # Limitiere Tests
            try:
                _rate_sleep()
                response = SESSION.head(url, timeout=(3, 10))
                if response.status_code == 200:
                    existing_urls.append(url)
            except Exception:
                continue
        
        return existing_urls
    
    def _google_site_search(self, base_url: str, language: str) -> List[str]:
        """Google Site-Search als Fallback"""
        # Hier würde die Google Search API Integration kommen
        # Ähnlich wie in select_company_homepage_from_brave
        return []
    
    def _deduplicate_and_filter(self, urls: List[str], base_url: str, language: str) -> List[str]:
        """Entfernt Duplikate und filtert nach Relevanz"""
        
        seen = set()
        filtered_urls = [base_url]  # Homepage immer dabei
        seen.add(base_url)
        
        patterns = self.language_patterns.get(language, self.language_patterns['en'])
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        
        for url in urls:
            if url in seen or not same_domain(base_url, url):
                continue
            
            path = urlparse(url).path.lower()
            
            # Relevanz-Check
            if any(pattern.search(path) for pattern in compiled_patterns):
                filtered_urls.append(url)
                seen.add(url)
                
                if len(filtered_urls) >= MAX_PAGES_TO_SUMMARIZE:
                    break
        
        return filtered_urls


def adaptive_company_website_scraper(query: str) -> str:
    """
    Adaptive Version des Website-Scrapers für verschiedene Architekturen
    """
    
    print(f"🚀 ADAPTIVE SCRAPER - Query: '{query}'")
    
    # Bestehende Homepage-Ermittlung verwenden
    try:
        from .website_scraper import select_company_homepage_from_brave
        base_url = select_company_homepage_from_brave(query)
    except ImportError:
        print("❌ Basis-Scraper nicht verfügbar")
        return "Fehler beim Laden des Basis-Scrapers"
    
    if not base_url:
        print("❌ Keine Homepage gefunden!")
        return "Es konnte keine Unternehmens-Homepage ermittelt werden."
    
    print(f"✅ Homepage gefunden: {base_url}")
    
    # Adaptive Analyse
    detector = WebsiteArchitectureDetector()
    url_discovery = AdaptiveURLDiscovery(detector)
    
    important_urls = url_discovery.discover_urls(base_url)
    
    if not important_urls:
        print("⚠️ Keine relevanten URLs gefunden - verwende nur Homepage")
        important_urls = [base_url]
    
    print(f"\n📊 Analyse von {len(important_urls)} URLs:")
    for i, url in enumerate(important_urls, 1):
        path = url.replace(base_url, '') or '/'
        print(f"   {i}. {path}")
    
    # Rest der Verarbeitung wie im Original-Scraper
    # (Text-Extraktion, LLM-Zusammenfassung, etc.)
    
    return f"Adaptive Analyse von {len(important_urls)} Seiten abgeschlossen."


if __name__ == "__main__":
    # Test der adaptiven Funktionalität
    test_query = "ACME GmbH München"
    result = adaptive_company_website_scraper(test_query)
    print(result) 