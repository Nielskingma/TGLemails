#!/usr/bin/env python3
"""Zorgt dat een jaartabblad in het verhuur-bronbestand bestaat, en maakt het zo nodig aan.

Dupliceert het voorgaande jaar (alle formules, opmaak, dropdowns blijven behouden), werkt de
jaartal-verwijzingen in de bezettingsgraad-formules (rij 3) bij, en wist de ingevulde
boekingsgegevens (niet de formulekolommen) zodat het tabblad klaar is voor nieuwe boekingen.

Wordt zowel los gebruikt (CLI) als geïmporteerd door btw_import.py, dat dit automatisch
aanroept zodra het een boeking voor een nog niet bestaand jaar probeert te lezen.
"""
import re
import sys
import warnings

warnings.filterwarnings("ignore")

BRON_SHEET_ID = "1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg"

# Kolommen met handmatig ingevulde gegevens (worden geleegd voor het nieuwe jaar).
# Q, T, V, W, X zijn formulekolommen en blijven staan.
INVUL_RANGES = ["A{s}:P{e}", "R{s}:S{e}", "U{s}:U{e}", "Y{s}:Z{e}"]

# Cellen in rij 3 met een hardgecodeerd jaartal (label + 5 bezettingsgraad-formules).
JAAR_CELLEN = ["H3", "J3", "L3", "N3", "P3", "R3"]


def _stil(*_args, **_kwargs) -> None:
    pass


def zorg_voor_boekjaar(sh, jaar, log=None):
    """Geeft het tabblad voor `jaar` terug; maakt het aan (op basis van jaar-1) als het ontbreekt.

    `sh` is een geopende gspread Spreadsheet (het bronbestand). `jaar` mag int of str zijn.
    Geeft None terug als het tabblad ontbreekt én er geen bronjaar (jaar-1) is om van te dupliceren.
    """
    log = log or _stil
    jaar = str(jaar)
    bronjaar = str(int(jaar) - 1)

    bestaande = {ws.title: ws for ws in sh.worksheets()}
    if jaar in bestaande:
        return bestaande[jaar]

    if bronjaar not in bestaande:
        log(f"  ⚠ Tabblad '{jaar}' ontbreekt en bronjaar '{bronjaar}' is er ook niet — kan niet automatisch aanmaken.")
        return None

    log(f"  Tabblad '{jaar}' ontbreekt nog — automatisch aanmaken op basis van '{bronjaar}'…")
    bron = bestaande[bronjaar]

    nieuw = sh.duplicate_sheet(
        source_sheet_id=bron.id,
        new_sheet_name=jaar,
        insert_sheet_index=bron.index + 1,
    )
    log(f"  Tabblad '{jaar}' aangemaakt op basis van '{bronjaar}'.")

    # Jaartal-verwijzingen in rij 3 bijwerken (label + bezettingsgraad-formules)
    huidige = nieuw.batch_get(JAAR_CELLEN, value_render_option="FORMULA")
    updates = []
    for cel, waarde in zip(JAAR_CELLEN, huidige):
        tekst = waarde[0][0] if waarde and waarde[0] else ""
        bijgewerkt = re.sub(re.escape(bronjaar), jaar, tekst)
        if bijgewerkt != tekst:
            updates.append({"range": cel, "values": [[bijgewerkt]]})
    if updates:
        nieuw.batch_update(updates, value_input_option="USER_ENTERED")
        log(f"  Jaartal-verwijzingen in rij 3 bijgewerkt ({len(updates)} cellen).")

    # Laatst gebruikte rij bepalen (op basis van kolom A) om alleen echte boekingsdata te wissen
    kolom_a = bron.col_values(1)
    laatste_rij = len(kolom_a)
    eerste_datarij = 5

    if laatste_rij >= eerste_datarij:
        bereiken = [s.format(s=eerste_datarij, e=laatste_rij) for s in INVUL_RANGES]
        nieuw.batch_clear(bereiken)
        log(f"  Boekingsgegevens gewist (rij {eerste_datarij} t/m {laatste_rij}), formules blijven staan.")

        # Duplicate_sheet neemt ook opmaak over — bijv. doorgestreept/grijs van
        # verstreken boekingen in het bronjaar. Reset dat, anders lijken lege
        # rijen (en boekingen die er straks in komen) al "verstreken".
        volledig_bereik = f"A{eerste_datarij}:Z{laatste_rij}"
        nieuw.format(volledig_bereik, {
            "textFormat": {
                "strikethrough": False,
                "foregroundColor": {"red": 0, "green": 0, "blue": 0},
            },
        })
        log(f"  Opmaak (doorstrepen/grijze tekst) gereset voor rij {eerste_datarij} t/m {laatste_rij}.")
    else:
        log("  Geen bestaande boekingsdata gevonden om te wissen.")

    return nieuw


def main():
    import gspread

    if len(sys.argv) == 2:
        jaar = sys.argv[1]
    else:
        print("Gebruik: nieuw_boekjaar.py <jaar>")
        print("Voorbeeld: nieuw_boekjaar.py 2027")
        sys.exit(1)

    gc = gspread.oauth()
    sh = gc.open_by_key(BRON_SHEET_ID)

    bestaande = [ws.title for ws in sh.worksheets()]
    if jaar in bestaande:
        print(f"Tabblad '{jaar}' bestaat al.")
        return

    resultaat = zorg_voor_boekjaar(sh, jaar, log=print)
    if resultaat is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
