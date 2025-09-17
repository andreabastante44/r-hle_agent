#!/usr/bin/env python3
"""
Test-Script für das WLW-Scrape-Tool
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from tools.wlw_scrape_tool import wlw_scrape_tool
import json

def test_wlw_tool():
    """Testet das WLW-Scrape-Tool mit verschiedenen Suchanfragen"""
    
    # Test-Daten (basierend auf dem Terminal-Output)
    test_queries = [
        "AWStec Abrasiv-Wasserstrahlschneidtechnik AND 28876",  # Beispiel-Query
    ]
    print("=== WLW-Scrape-Tool Test ===\n")
    
    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: Query = '{query}'")
        print("-" * 50)
        
        try:
            result = wlw_scrape_tool(query)
            
            print(f"Ergebnis-Typ: {type(result)}")
            print(f"Ergebnis-Inhalt:")
            
            if isinstance(result, dict):
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(str(result))
                
        except Exception as e:
            print(f"Fehler beim Test: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    test_wlw_tool()
