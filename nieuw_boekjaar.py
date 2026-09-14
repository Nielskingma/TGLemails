#!/usr/bin/env python3
"""Zorgt dat een jaartabblad in het verhuur-bronbestand bestaat, en maakt het zo nodig aan.

Dupliceert het voorgaande jaar (alle formules, opmaak, dropdowns blijven behouden), werkt de
jaartal-verwijzingen in de bezettingsgraad-formules (rij 3) bij, en wist de ingevulde
boekingsgegevens (niet de formulekolommen) zodat het tabblad klaar is voor nieuwe boekingen.

Wordt zowel los gebruikt (CLI) als geïmporteerd door btw_import.py, dat dit automatisch
aanroept zodra het een boeking voor een nog niet bestaand jaar probeert te lezen.
"""
import sys
import warnings

warnings.filterwarnings("ignore")

BRON_SHEET_ID = "1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg"

# Kolommen met handmatig ingevulde gegevens (worden geleegd voor het nieuwe jaar).
# Q, T, V, W, X zijn formulekolommen en blijven staan.
INVUL_RANGES = ["A{s}:P{e}", "R{s}:S{e}", "U{s}:U{e}", "Y{s}:Z{e}"]

# Vast rijbereik van de boekingsdata op elk jaartabblad (zelfde voor alle jaren).
EERSTE_DATARIJ = 5
LAATSTE_DATARIJ = 235


def _bezettingsgraad_formules(jaar):
    """Canonieke bezettingsgraad-formules voor rij 3, direct met het juiste jaartal.

    Deze worden bij het aanmaken van een nieuw jaartabblad altijd opnieuw neergezet
    (niet afgeleid van wat er in het bronjaar toevallig al stond) — anders erft elk
    volgend jaar een fout in het bronjaar automatisch over (zoals 2027 had: verkeerd
    rijbereik en verkeerde noemer bij de platform-percentages, ontstaan doordat dat
    tabblad gedupliceerd was vóór de fix van de bezettingsgraad-formules).
    Alleen geschikt voor volledige kalenderjaren (deelt door 365); 2025 was een
    uitzondering (deeljaar) en is destijds eenmalig handmatig aangepast.
    """
    s, e = EERSTE_DATARIJ, LAATSTE_DATARIJ
    a = f"A{s}:A{e}"
    b = f"B{s}:B{e}"
    q = f"Q{s}:Q{e}"
    bezet = f'SUMPRODUCT(({a}<>"Eigen verblijf")*({a}<>"")*(YEAR({b})={jaar})*{q})'

    def aandeel(voorwaarde):
        return f'=TEXT(SUMPRODUCT({voorwaarde}*(YEAR({b})={jaar})*{q})/{bezet};"0%")'

    return {
        "H3": f"Bezettingsgraad {jaar}",
        "J3": f'=TEXT({bezet}/365;"0%")',
        "L3": aandeel(f'({a}="Airbnb")'),
        "N3": aandeel(f'({a}="Natuurhuisje")'),
        "P3": aandeel(f'({a}="Booking")'),
        "R3": aandeel(f'(({a}="Direct")+({a}="Voyando"))'),
    }


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

    # Bezettingsgraad-formules in rij 3 altijd met de canonieke, correcte versie
    # overschrijven (niet het jaartal vervangen in wat het bronjaar toevallig had staan).
    formules = _bezettingsgraad_formules(jaar)
    updates = [{"range": cel, "values": [[waarde]]} for cel, waarde in formules.items()]
    nieuw.batch_update(updates, value_input_option="USER_ENTERED")
    log(f"  Bezettingsgraad-formules in rij 3 neergezet voor {jaar} ({len(updates)} cellen).")

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
