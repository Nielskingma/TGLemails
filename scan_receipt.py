#!/usr/bin/env python3
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional

SPREADSHEET_ID = "1sXOnJpfsvgcAdGU4Bp6uzVUCFL7vXdn1JqNWFhntTjw"
DATA_START_ROW = 26


def kwartaal_naam(datum_str: str) -> str:
    """Geeft de sheetnaam terug op basis van datum DD-MM-YYYY, bijv. 'Q1 2026'."""
    try:
        dag, maand, jaar = datum_str.split("-")
        kwartaal = (int(maand) - 1) // 3 + 1
        return f"Q{kwartaal} {jaar}"
    except Exception:
        return None

JSON_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "datum":        {"type": ["string", "null"]},
        "omschrijving": {"type": ["string", "null"]},
        "leverancier":  {"type": ["string", "null"]},
        "bedrag_ex_btw":{"type": ["number", "null"]},
        "btw_bedrag":   {"type": ["number", "null"]},
        "totaalbedrag": {"type": ["number", "null"]},
        "opmerkingen":  {"type": ["string", "null"]},
    },
    "required": ["datum", "omschrijving", "leverancier", "bedrag_ex_btw", "btw_bedrag", "totaalbedrag", "opmerkingen"],
})


def scan_bonnetje(file_path: str) -> dict:
    path = Path(file_path).resolve()
    if not path.exists():
        print(f"Fout: bestand '{file_path}' niet gevonden.", file=sys.stderr)
        sys.exit(1)

    prompt = (
        f"Lees het bestand op dit pad: {path}\n"
        "Extraheer de volgende gegevens:\n"
        "- datum: datum van het bonnetje in formaat DD-MM-YYYY\n"
        "- omschrijving: korte omschrijving van wat er gekocht/betaald is\n"
        "- leverancier: naam van het bedrijf of de winkel\n"
        "- bedrag_ex_btw: bedrag exclusief BTW als getal\n"
        "- btw_bedrag: BTW-bedrag als getal\n"
        "- totaalbedrag: totaalbedrag inclusief BTW als getal\n"
        "- opmerkingen: eventuele bijzonderheden, anders null\n"
        "Gebruik null voor ontbrekende waarden. Geen valutasymbolen in bedragen."
    )

    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--add-dir", str(path.parent),
            "--allowedTools", "Read",
            "--output-format", "json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"Geen output van Claude voor {path.name}")

    wrapper = json.loads(result.stdout.strip())
    raw = wrapper.get("result", "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    data = json.loads(raw.strip())

    # Bereken ontbrekende bedragen
    ex = data.get("bedrag_ex_btw")
    btw = data.get("btw_bedrag")
    totaal = data.get("totaalbedrag")
    if ex is None and totaal and btw:
        data["bedrag_ex_btw"] = round(totaal - btw, 2)
    if totaal is None and ex and btw:
        data["totaalbedrag"] = round(ex + btw, 2)

    return data


def schrijf_naar_sheet(bonnetjes: list) -> None:
    try:
        import gspread
    except ImportError:
        print("gspread niet geïnstalleerd. Installeer met: pip3 install gspread", file=sys.stderr)
        return

    try:
        gc = gspread.oauth()
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"Fout bij verbinding met Google Sheets: {e}", file=sys.stderr)
        return

    # Groepeer bonnetjes per kwartaalblad
    per_kwartaal: dict = {}
    onbekend = []
    for b in bonnetjes:
        naam = kwartaal_naam(b.get("datum") or "")
        if naam:
            per_kwartaal.setdefault(naam, []).append(b)
        else:
            onbekend.append(b)

    if onbekend:
        print(f"Let op: {len(onbekend)} bonnetje(s) zonder datum overgeslagen.", file=sys.stderr)

    bestaande_bladen = [ws.title for ws in sh.worksheets()]

    for sheet_naam, groep in per_kwartaal.items():
        if sheet_naam not in bestaande_bladen:
            print(f"Tabblad '{sheet_naam}' bestaat niet, wordt aangemaakt…")
            kwartaalbladen = sorted([t for t in bestaande_bladen if len(t.split()) == 2 and t.split()[0].startswith("Q")])
            bronblad = kwartaalbladen[-1] if kwartaalbladen else None
            if not bronblad:
                print(f"Geen bronblad gevonden om '{sheet_naam}' van te maken.", file=sys.stderr)
                continue
            bron_ws = sh.worksheet(bronblad)
            nieuw_ws = sh.duplicate_sheet(source_sheet_id=bron_ws.id, new_sheet_name=sheet_naam)
            nieuw_ws.update("A1", [[f"THE GREEN LODGE - BTW AANGIFTE {sheet_naam}"]])
            nieuw_ws.update("A2", [[""]])
            ka = nieuw_ws.col_values(1)
            totaal_uit = next((i for i, v in enumerate(ka, 1) if "TOTAAL UITGAAND" in str(v).upper()), None)
            inkomend_h = next((i for i, v in enumerate(ka, 1) if "INKOMEND (KOSTEN" in str(v).upper()), None)
            totaal_ink = next((i for i, v in enumerate(ka, 1) if "TOTAAL INKOMEND" in str(v).upper()), None)
            if totaal_uit and totaal_uit > 6:
                nieuw_ws.update(f"A6:G{totaal_uit - 1}", [[""] * 7] * (totaal_uit - 6))
            if inkomend_h and totaal_ink and totaal_ink > inkomend_h + 2:
                ds = inkomend_h + 2
                nieuw_ws.update(f"A{ds}:G{totaal_ink - 1}", [[""] * 7] * (totaal_ink - ds))
            bestaande_bladen.append(sheet_naam)
            ws = nieuw_ws
            print(f"Tabblad '{sheet_naam}' aangemaakt.")
        else:
            ws = sh.worksheet(sheet_naam)
        kolom_a = ws.col_values(1)

        # Zoek de totaalrij
        totaal_rij = None
        for i, v in enumerate(kolom_a, 1):
            if "TOTAAL INKOMEND" in str(v).upper():
                totaal_rij = i
                break

        # Zoek eerste lege rij vanaf DATA_START_ROW
        volgende_rij = DATA_START_ROW
        for i in range(DATA_START_ROW - 1, len(kolom_a)):
            if not kolom_a[i].strip():
                volgende_rij = i + 1
                break
        else:
            volgende_rij = max(len(kolom_a) + 1, DATA_START_ROW)

        rijen = [[
            b.get("datum") or "",
            b.get("omschrijving") or "",
            b.get("leverancier") or "",
            b.get("bedrag_ex_btw") or "",
            b.get("btw_bedrag") or "",
            b.get("totaalbedrag") or "",
            b.get("opmerkingen") or "",
        ] for b in groep]

        # Voeg rijen in als er niet genoeg ruimte is voor de totaalrij
        if totaal_rij and volgende_rij + len(rijen) > totaal_rij:
            tekort = (volgende_rij + len(rijen)) - totaal_rij
            for _ in range(tekort):
                ws.insert_rows([], row=totaal_rij, value_input_option="USER_ENTERED", inherit_from_before=True)
            print(f"{tekort} rij(en) ingevoegd boven 'TOTAAL INKOMEND' in '{sheet_naam}'.")

        ws.update(rijen, f"A{volgende_rij}")
        print(f"{len(rijen)} rij(en) toegevoegd aan '{sheet_naam}' vanaf rij {volgende_rij}.")

        # SUM-formules in totaalrij
        if totaal_rij:
            ws.update(
                [[
                    f"=SUM(D{DATA_START_ROW}:D{totaal_rij - 1})",
                    f"=SUM(E{DATA_START_ROW}:E{totaal_rij - 1})",
                    f"=SUM(F{DATA_START_ROW}:F{totaal_rij - 1})",
                ]],
                f"D{totaal_rij}",
                value_input_option="USER_ENTERED",
            )

        # Bedragkolommen opmaken als euro's
        einde_rij = totaal_rij or (volgende_rij + len(rijen) - 1)
        ws.format(f"D{DATA_START_ROW}:F{einde_rij}", {"numberFormat": {"type": "CURRENCY", "pattern": "€#,##0.00"}})


def kies_bestanden() -> list:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)
    paden = filedialog.askopenfilenames(
        title="Selecteer één of meerdere bonnetjes",
        filetypes=[
            ("Afbeeldingen & PDF", "*.jpg *.jpeg *.png *.webp *.pdf"),
            ("Alle bestanden", "*.*"),
        ],
    )
    root.destroy()
    return list(paden)


def main():
    if len(sys.argv) >= 2:
        bestanden = sys.argv[1:]
    else:
        bestanden = kies_bestanden()
        if not bestanden:
            print("Geen bestand geselecteerd.", file=sys.stderr)
            sys.exit(1)

    resultaten = []
    mislukt = []
    for pad in bestanden:
        print(f"Verwerken: {Path(pad).name}…")
        try:
            result = scan_bonnetje(pad)
            resultaten.append({"bestand": pad, **result})
        except Exception as e:
            print(f"  Overgeslagen: {e}", file=sys.stderr)
            mislukt.append(pad)

    if mislukt:
        print(f"\n{len(mislukt)} bestand(en) mislukt:", file=sys.stderr)
        for p in mislukt:
            print(f"  - {Path(p).name}", file=sys.stderr)

    if not resultaten:
        print("Geen bonnetjes succesvol verwerkt.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(resultaten if len(resultaten) > 1 else resultaten[0], ensure_ascii=False, indent=2))
    schrijf_naar_sheet(resultaten)


if __name__ == "__main__":
    main()
