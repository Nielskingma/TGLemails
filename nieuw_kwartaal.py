#!/usr/bin/env python3
"""Maak een nieuw kwartaalblad aan op basis van het vorige kwartaal."""
import sys
import warnings
warnings.filterwarnings("ignore")

SPREADSHEET_ID = "1sXOnJpfsvgcAdGU4Bp6uzVUCFL7vXdn1JqNWFhntTjw"
BRONBLAD = "Q1 2026"

KWARTALEN = ["Q1", "Q2", "Q3", "Q4"]


def volgende_kwartaal(naam: str) -> str:
    """Geeft het volgende kwartaal terug, bijv. 'Q1 2026' → 'Q2 2026'."""
    parts = naam.split()
    if len(parts) != 2:
        return ""
    kw, jaar = parts
    jaar = int(jaar)
    idx = KWARTALEN.index(kw)
    if idx == 3:
        return f"Q1 {jaar + 1}"
    return f"{KWARTALEN[idx + 1]} {jaar}"


def maak_nieuw_kwartaal(nieuw_naam: str) -> None:
    import gspread
    gc = gspread.oauth()
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Controleer of het blad al bestaat
    bestaande = [ws.title for ws in sh.worksheets()]
    if nieuw_naam in bestaande:
        print(f"Tabblad '{nieuw_naam}' bestaat al.")
        return

    # Zoek het bronblad
    bron = sh.worksheet(BRONBLAD)

    # Dupliceer het bronblad
    nieuw = sh.duplicate_sheet(
        source_sheet_id=bron.id,
        new_sheet_name=nieuw_naam,
    )

    # Update de titel in rij 1
    nieuw.update("A1", [[f"THE GREEN LODGE - BTW AANGIFTE {nieuw_naam}"]])

    # Leeg rij 2 (gegenereerd op datum)
    nieuw.update("A2", [[""]])

    # Zoek dynamisch de datarijen op basis van structuurrijen
    kolom_a = nieuw.col_values(1)

    # Zoek "TOTAAL UITGAAND" en "INKOMEND" om de uitgaand-datarijen te bepalen
    totaal_uitgaand_rij = None
    inkomend_header_rij = None
    totaal_inkomend_rij = None

    for i, v in enumerate(kolom_a, 1):
        v_upper = str(v).upper()
        if "TOTAAL UITGAAND" in v_upper:
            totaal_uitgaand_rij = i
        elif "INKOMEND (KOSTEN" in v_upper:
            inkomend_header_rij = i
        elif "TOTAAL INKOMEND" in v_upper:
            totaal_inkomend_rij = i

    # Wis uitgaand-data (rijen tussen header rij 5 en TOTAAL UITGAAND)
    if totaal_uitgaand_rij and totaal_uitgaand_rij > 6:
        leeg = [[""] * 7 for _ in range(totaal_uitgaand_rij - 6)]
        nieuw.update(f"A6:G{totaal_uitgaand_rij - 1}", leeg)

    # Wis inkomend-data (rijen tussen kolomhoeders en TOTAAL INKOMEND)
    if inkomend_header_rij and totaal_inkomend_rij:
        data_start = inkomend_header_rij + 2  # +1 voor kolomhoeder, +1 voor eerste datarij
        if totaal_inkomend_rij > data_start:
            leeg = [[""] * 7 for _ in range(totaal_inkomend_rij - data_start)]
            nieuw.update(f"A{data_start}:G{totaal_inkomend_rij - 1}", leeg)

    print(f"Tabblad '{nieuw_naam}' aangemaakt op basis van '{BRONBLAD}'.")


def main():
    if len(sys.argv) == 2:
        nieuw_naam = sys.argv[1]
    else:
        # Stel automatisch het volgende kwartaal voor
        import gspread
        gc = gspread.oauth()
        sh = gc.open_by_key(SPREADSHEET_ID)
        bladen = [ws.title for ws in sh.worksheets()]
        kwartaalbladen = [t for t in bladen if t[:2] in KWARTALEN]
        voorstel = volgende_kwartaal(kwartaalbladen[-1]) if kwartaalbladen else "Q1 2026"

        antwoord = input(f"Naam nieuw tabblad [{voorstel}]: ").strip()
        nieuw_naam = antwoord if antwoord else voorstel

    maak_nieuw_kwartaal(nieuw_naam)


if __name__ == "__main__":
    main()
