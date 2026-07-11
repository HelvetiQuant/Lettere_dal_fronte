"""Riprende tutte le importazioni in background:
1. Fondi M-7 (processing interrotto)
2. CWGC (474K/1.76M)
3. Linker (entita + collegamenti)
"""
import sys
import traceback

def run_fondi():
    """Riprende estrazione fondi - M-7 era interrotto a pag 11/109"""
    print("=== FONDI: ripresa estrazione ===")
    try:
        from fondi import extract_all, clear_stop_request
        clear_stop_request()
        extract_all(resume=True, engine="auto", parallel=2)
        print("FONDI: completato")
    except Exception as e:
        print(f"FONDI errore: {e}")
        traceback.print_exc()

def run_cwgc():
    """Riprende scraping CWGC"""
    print("\n=== CWGC: ripresa scraping ===")
    try:
        from caduti_cwgc import scrape_all
        scrape_all(resume=True)
        print("CWGC: completato")
    except Exception as e:
        print(f"CWGC errore: {e}")
        traceback.print_exc()

def run_linker():
    """Riesegue linker per entita/collegamenti su tutte le tabelle"""
    print("\n=== LINKER: estrazione entita + collegamenti ===")
    try:
        from linker import build_links
        build_links(resume=True)
        print("LINKER: completato")
    except Exception as e:
        print(f"LINKER errore: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # 1. Fondi (veloce - solo M-7 da finire)
    run_fondi()
    # 2. CWGC (lungo - resume da dove era arrivato)
    run_cwgc()
    # 3. Linker (medio - resume)
    run_linker()
    print("\n=== TUTTE LE IMPORTAZIONI COMPLETATE ===")
