#!/Users/nielskingma/projects/boekhouding-tgl/.venv/bin/python
"""
The Green Lodge — BTW Import v1
Vervangt BTWAangifte.gs volledig.
Verwerkt bonnetjes lokaal (pdfplumber → OCR → Claude fallback)
en schrijft UITGAAND + INKOMEND naar de BTW Google Sheet.
"""

import sys
import json
import re
import subprocess
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
import threading
import customtkinter as ctk

from nieuw_boekjaar import zorg_voor_boekjaar

# ── Constanten ────────────────────────────────────────────────────────────────

BTW_SHEET_ID  = "1sXOnJpfsvgcAdGU4Bp6uzVUCFL7vXdn1JqNWFhntTjw"
BRON_SHEET_ID = "1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg"

FOREST_DARK = "#2D4A1E"
FOREST_MED  = "#4A7C2F"
FOREST_PALE = "#EEF5E6"
CREAM       = "#FDFAF4"
CREAM_ALT   = "#F4F0E8"
LIGHT_GREY  = "#F5F5F5"
WHITE       = "#FFFFFF"

MAANDEN = ["januari","februari","maart","april","mei","juni",
           "juli","augustus","september","oktober","november","december"]

# Bekende leveranciers met vaste BTW-tarieven (sleutel: lowercase deelstring van leveranciersnaam)
BTW_TARIEVEN = {
    "odido":    0.21,
    "voyando":  0.21,
    "eneco":    0.21,
    "vattenfall": 0.21,
    "essent":   0.21,
    "dhl":      0.21,
    "postnl":   0.21,
    "vitens":   0.09,
    "evides":   0.09,
    "dunea":    0.09,
}

# ── Google Sheets verbinding ──────────────────────────────────────────────────

def get_gspread():
    import gspread
    return gspread.oauth()

# ── Kwartaal hulpfuncties ─────────────────────────────────────────────────────

def kwartaal_naam(datum_str: str) -> Optional[str]:
    """'DD-MM-YYYY' → 'Q1 2026'"""
    try:
        dag, maand, jaar = datum_str.split("-")
        kwartaal = (int(maand) - 1) // 3 + 1
        return f"Q{kwartaal} {jaar}"
    except Exception:
        return None

def kwartaal_van_datum(datum: datetime) -> tuple:
    return (datum.month - 1) // 3 + 1, datum.year

# ── Lokale tekstextractie ─────────────────────────────────────────────────────

def extraheer_tekst_pdf(path: Path) -> str:
    """Stap 1: pdfplumber — leest tekst direct uit digitale PDF."""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            tekst = "\n".join(p.extract_text() or "" for p in pdf.pages)
        return tekst.strip()
    except ImportError:
        return ""
    except Exception:
        return ""

def extraheer_tekst_ocr(path: Path) -> str:
    """Stap 2: pytesseract OCR — voor scans en afbeeldingen."""
    try:
        import pytesseract
        from PIL import Image
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(str(path))
                return "\n".join(
                    pytesseract.image_to_string(img, lang="nld+eng") for img in images
                )
            except Exception:
                return ""
        else:
            img = Image.open(str(path))
            return pytesseract.image_to_string(img, lang="nld+eng")
    except ImportError:
        return ""
    except Exception:
        return ""

def parse_bedrag(tekst: str) -> Optional[float]:
    """Haalt een bedrag uit tekst. Ondersteunt NL (1.234,56) en EN (1,234.56) notatie."""
    if not tekst:
        return None
    s = str(tekst).replace("€", "").replace(" ", "").strip()
    # NL: punt als duizendtallen, komma als decimaal
    m = re.search(r"(\d{1,3}(?:\.\d{3})*),(\d{2})(?!\d)", s)
    if m:
        return float(m.group(0).replace(".", "").replace(",", "."))
    # EN: komma als duizendtallen, punt als decimaal
    m = re.search(r"(\d{1,3}(?:,\d{3})*)\.(\d{2})(?!\d)", s)
    if m:
        return float(m.group(0).replace(",", ""))
    # Eenvoudig getal met komma
    m = re.search(r"(\d+),(\d{2})(?!\d)", s)
    if m:
        return float(m.group(0).replace(",", "."))
    # Eenvoudig getal met punt
    m = re.search(r"(\d+)\.(\d{2})(?!\d)", s)
    if m:
        return float(m.group(0))
    return None

def parse_datum(tekst: str) -> Optional[str]:
    """Haalt datum uit tekst. Geeft DD-MM-YYYY terug."""
    # DD-MM-YYYY of DD/MM/YYYY
    m = re.search(r"(\d{2})[-/](\d{2})[-/](\d{4})", tekst)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", tekst)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # DD maandnaam YYYY
    m = re.search(
        r"(\d{1,2})\s+(januari|februari|maart|april|mei|juni|juli|augustus"
        r"|september|oktober|november|december)\s+(\d{4})",
        tekst, re.IGNORECASE
    )
    if m:
        maand_nr = str(MAANDEN.index(m.group(2).lower()) + 1).zfill(2)
        return f"{str(m.group(1)).zfill(2)}-{maand_nr}-{m.group(3)}"
    return None

def parse_tekst_naar_data(tekst: str) -> dict:
    """Probeert gestructureerde factuurdata te extraheren uit platte tekst."""
    data = {
        "datum": None, "omschrijving": None, "leverancier": None,
        "bedrag_ex_btw": None, "btw_bedrag": None,
        "totaalbedrag": None, "opmerkingen": None,
    }

    data["datum"] = parse_datum(tekst)
    data["opmerkingen"] = None

    # Leverancier: eerste niet-lege regel
    regels = [r.strip() for r in tekst.split("\n") if r.strip()]
    if regels:
        data["leverancier"] = regels[0][:60]
    # Omschrijving: tweede niet-lege regel, maximaal 3 woorden
    if len(regels) > 1:
        woorden = regels[1].split()[:3]
        data["omschrijving"] = " ".join(woorden)

    # Totaalbedrag
    for patroon in [
        r"(?:totaal|total|te betalen|amount due)[^\d€]*€?\s*(\d[\d.,]+)",
        r"(?:grand total)[^\d€]*€?\s*(\d[\d.,]+)",
    ]:
        m = re.search(patroon, tekst, re.IGNORECASE)
        if m:
            data["totaalbedrag"] = parse_bedrag(m.group(1))
            break

    # BTW bedrag
    for patroon in [
        r"(?:btw|vat|omzetbelasting)[^\d€]*€?\s*(\d[\d.,]+)",
        r"21\s*%[^\d€]*€?\s*(\d[\d.,]+)",
        r"9\s*%[^\d€]*€?\s*(\d[\d.,]+)",
    ]:
        m = re.search(patroon, tekst, re.IGNORECASE)
        if m:
            data["btw_bedrag"] = parse_bedrag(m.group(1))
            break

    # Bedrag exclusief BTW
    for patroon in [
        r"(?:excl\.?\s*btw|ex\.?\s*btw|netto|subtotaal|subtotal)[^\d€]*€?\s*(\d[\d.,]+)",
    ]:
        m = re.search(patroon, tekst, re.IGNORECASE)
        if m:
            data["bedrag_ex_btw"] = parse_bedrag(m.group(1))
            break

    # Bereken ontbrekende bedragen
    ex, btw, totaal = data["bedrag_ex_btw"], data["btw_bedrag"], data["totaalbedrag"]
    if ex is None and totaal and btw:
        data["bedrag_ex_btw"] = round(totaal - btw, 2)
    if totaal is None and ex and btw:
        data["totaalbedrag"] = round(ex + btw, 2)
    if btw is None and totaal and ex:
        data["btw_bedrag"] = round(totaal - ex, 2)

    return data

def scan_via_claude(path: Path) -> dict:
    """Stap 3: Claude als fallback."""
    prompt = (
        f"Lees het bestand op dit pad: {path}\n"
        "Extraheer de volgende gegevens:\n"
        "- datum: datum van het bonnetje in formaat DD-MM-YYYY\n"
        "- omschrijving: maximaal 3 woorden die beschrijven wat er gekocht is, bijv. 'verf', 'beddengoed', 'bloemen kopen'\n"
        "- leverancier: naam van het bedrijf of de winkel\n"
        "- bedrag_ex_btw: bedrag exclusief BTW als getal\n"
        "- btw_bedrag: BTW-bedrag als getal\n"
        "- totaalbedrag: totaalbedrag inclusief BTW als getal\n"
        "- opmerkingen: altijd null\n"
        "Gebruik null voor ontbrekende waarden. Geen valutasymbolen. "
        "Geef alleen pure JSON terug zonder uitleg."
    )
    result = subprocess.run(
        ["claude", "-p", prompt, "--add-dir", str(path.parent),
         "--allowedTools", "Read", "--output-format", "json"],
        capture_output=True, text=True,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"Geen output van Claude voor {path.name}")
    wrapper = json.loads(result.stdout.strip())
    raw = wrapper.get("result", "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(raw.strip())

def scan_bonnetje(path: Path, log, status=None) -> dict:
    """
    Gelaagde extractie: pdfplumber → OCR → Claude.
    Geeft altijd een dict terug. '_onvolledig' = True bij ontbrekende kritieke velden.
    """
    def st(tekst):
        if status:
            status(tekst)

    naam = path.name
    tekst = ""
    methode = ""

    # Stap 1: pdfplumber
    if path.suffix.lower() == ".pdf":
        st(f"{naam} — tekst uitlezen (PDF)…")
        tekst = extraheer_tekst_pdf(path)
        if tekst:
            methode = "pdfplumber"
            log(f"  ✓ PDF tekst: {len(tekst)} tekens gelezen")

    # Stap 2: OCR
    if not tekst:
        st(f"{naam} — scannen via OCR…")
        log("  → Geen digitale tekst, OCR starten…")
        tekst = extraheer_tekst_ocr(path)
        if tekst:
            methode = "ocr"
            log(f"  ✓ OCR: {len(tekst)} tekens herkend")
        else:
            log("  ✗ OCR levert niets op")

    # Parse lokale tekst
    if tekst:
        st(f"{naam} — gegevens herkennen…")
        data = parse_tekst_naar_data(tekst)
        kritiek = ["datum", "totaalbedrag"]
        if all(data.get(v) for v in kritiek):
            data["_methode"] = methode
            data["_onvolledig"] = any(
                not data.get(v) for v in ["bedrag_ex_btw", "btw_bedrag", "omschrijving", "leverancier"]
            )
            log(f"  ✓ Herkend: {data.get('datum')} | {data.get('leverancier')} | €{data.get('totaalbedrag')}")
            return data
        log(f"  ✗ Datum of totaal ontbreekt — Claude inschakelen")

    # Stap 3: Claude
    try:
        st(f"{naam} — Claude AI (fallback)…")
        log("  → Claude leest het bestand…")
        data = scan_via_claude(path)
        data["_methode"] = "claude"
        data["_onvolledig"] = any(not data.get(v) for v in ["datum", "totaalbedrag"])
        log(f"  ✓ Claude: {data.get('datum')} | {data.get('leverancier')} | €{data.get('totaalbedrag')}")
        return data
    except subprocess.TimeoutExpired:
        st(f"{naam} — timeout")
        log("  ✗ Claude timeout na 60s")
    except Exception as e:
        st(f"{naam} — mislukt")
        log(f"  ✗ Mislukt: {e}")

    return {
        "datum": None, "omschrijving": None, "leverancier": None,
        "bedrag_ex_btw": None, "btw_bedrag": None,
        "totaalbedrag": None, "opmerkingen": None,
        "_methode": "mislukt", "_onvolledig": True,
    }

# ── Verhuur bronbestand lezen ─────────────────────────────────────────────────

def parse_btw_override(opmerking: str) -> Optional[tuple]:
    """Leest BTW kwartaal override, bijv. 'btw q1 2026' → (1, 2026)."""
    if not opmerking:
        return None
    m = re.search(r"\bbtw\s+q(\d)(?:\s*[/]?\s*(\d{4}))?", str(opmerking), re.IGNORECASE)
    if m:
        q = int(m.group(1))
        jaar = int(m.group(2)) if m.group(2) else None
        if 1 <= q <= 4:
            return (q, jaar)
    return None

def parse_sheet_datum(waarde) -> Optional[datetime]:
    """Parst een datumwaarde uit een sheet-cel (string of datetime)."""
    if not waarde:
        return None
    if isinstance(waarde, datetime):
        return waarde
    s = str(waarde).strip()
    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def lees_btw_boekingen(gc, jaar: int, kwartaal: int, log=None) -> list:
    """Leest boekingen uit verhuur_bronbestand voor het opgegeven kwartaal.

    Tabbladen voor een jaar dat nog niet bestaat (bijv. de eerste keer dat een boeking
    voor een nieuw jaar wordt verwerkt) worden automatisch aangemaakt, zie nieuw_boekjaar.py.
    """
    bron = gc.open_by_key(BRON_SHEET_ID)
    boekingen = []

    for j in [jaar, jaar - 1]:
        sheet = zorg_voor_boekjaar(bron, j, log=log)
        if sheet is None:
            continue
        data = sheet.get_all_values()

        for i in range(4, len(data)):
            rij = data[i]
            if len(rij) < 24:
                continue

            site = str(rij[0]).lower()
            if not any(p in site for p in ["airbnb", "booking", "natuurhuisje"]):
                continue

            ci_datum = parse_sheet_datum(rij[1])
            if not ci_datum:
                continue

            status = str(rij[7]).lower()
            if status in ["geannuleerd", "reservering"]:
                continue

            try:
                totaal = float(str(rij[22]).replace(",", ".").replace("€", "").strip() or 0)
                btw    = float(str(rij[23]).replace(",", ".").replace("€", "").strip() or 0)
            except ValueError:
                totaal, btw = 0.0, 0.0

            opmerking = str(rij[25]) if len(rij) > 25 else ""
            override = parse_btw_override(opmerking)

            if override:
                b_kwartaal = override[0]
                b_jaar = override[1] or ci_datum.year
            else:
                b_kwartaal, b_jaar = kwartaal_van_datum(ci_datum)

            if b_jaar != jaar or b_kwartaal != kwartaal:
                continue

            boekingen.append({
                "datum":        ci_datum.strftime("%d-%m-%Y"),
                "site":         str(rij[0]),
                "gast":         str(rij[5]),
                "bedrag_ex_btw": round(totaal - btw, 2),
                "btw_bedrag":   round(btw, 2),
                "totaalbedrag": round(totaal, 2),
                "opmerking":    opmerking,
            })

    boekingen.sort(key=lambda b: datetime.strptime(b["datum"], "%d-%m-%Y"))
    return boekingen

# ── Sheet opmaak helpers ──────────────────────────────────────────────────────

def hex_naar_rgb(kleur: str) -> dict:
    h = kleur.lstrip("#")
    return {
        "red":   int(h[0:2], 16) / 255,
        "green": int(h[2:4], 16) / 255,
        "blue":  int(h[4:6], 16) / 255,
    }

def cel_fmt(bg: str, fg: str = "#000000", bold: bool = False, size: int = 10,
            italic: bool = False, align: str = "LEFT", valign: str = "MIDDLE") -> dict:
    return {
        "backgroundColor": hex_naar_rgb(bg),
        "textFormat": {
            "foregroundColor": hex_naar_rgb(fg),
            "bold": bold, "italic": italic,
            "fontSize": size, "fontFamily": "Arial",
        },
        "horizontalAlignment": align,
        "verticalAlignment": valign,
        "wrapStrategy": "WRAP",
    }

def getal_fmt() -> dict:
    return {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}, "horizontalAlignment": "RIGHT"}

def req_format(ws, rij: int, kol: int, nrijen: int, nkols: int, fmt: dict,
               fields: str = "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)") -> dict:
    return {"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": rij-1, "endRowIndex": rij-1+nrijen,
                  "startColumnIndex": kol-1, "endColumnIndex": kol-1+nkols},
        "cell": {"userEnteredFormat": fmt},
        "fields": fields,
    }}

def req_getal(ws, rij: int, kol: int, nrijen: int = 1, nkols: int = 1) -> dict:
    return {"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": rij-1, "endRowIndex": rij-1+nrijen,
                  "startColumnIndex": kol-1, "endColumnIndex": kol-1+nkols},
        "cell": {"userEnteredFormat": getal_fmt()},
        "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
    }}

def req_merge(ws, rij: int, kol: int, nrijen: int, nkols: int) -> dict:
    return {"mergeCells": {
        "range": {"sheetId": ws.id, "startRowIndex": rij-1, "endRowIndex": rij-1+nrijen,
                  "startColumnIndex": kol-1, "endColumnIndex": kol-1+nkols},
        "mergeType": "MERGE_ALL",
    }}

def req_hoogte(ws, rij: int, hoogte: int) -> dict:
    return {"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": rij-1, "endIndex": rij},
        "properties": {"pixelSize": hoogte}, "fields": "pixelSize",
    }}

def req_breedte(ws, kol: int, breedte: int) -> dict:
    return {"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": kol-1, "endIndex": kol},
        "properties": {"pixelSize": breedte}, "fields": "pixelSize",
    }}

def req_freeze(ws, rijen: int) -> dict:
    return {"updateSheetProperties": {
        "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": rijen}},
        "fields": "gridProperties.frozenRowCount",
    }}

def batch(ws, reqs: list):
    if reqs:
        ws.spreadsheet.batch_update({"requests": reqs})

# ── Nieuw kwartaalblad aanmaken ───────────────────────────────────────────────

def maak_kwartaal_tab(sh, tab_naam: str, jaar: int, kwartaal: int, gc, log):
    """Maakt volledig nieuw kwartaalblad aan — equivalent van maakBtwTab in BTWAangifte.gs."""
    log(f"  Aanmaken tabblad '{tab_naam}'…")

    try:
        sh.del_worksheet(sh.worksheet(tab_naam))
    except Exception:
        pass

    ws = sh.add_worksheet(title=tab_naam, rows=120, cols=7)
    reqs = []

    # Kolombreedte
    for kol, br in enumerate([120, 120, 150, 130, 100, 130, 200], 1):
        reqs.append(req_breedte(ws, kol, br))

    # Rij 1: Titel
    reqs += [req_hoogte(ws, 1, 45), req_merge(ws, 1, 1, 1, 7),
             req_format(ws, 1, 1, 1, 7, cel_fmt(FOREST_DARK, WHITE, bold=True, size=15, align="CENTER"))]

    # Rij 2: Gegenereerd op
    reqs += [req_hoogte(ws, 2, 20), req_merge(ws, 2, 1, 1, 7),
             req_format(ws, 2, 1, 1, 7, cel_fmt(FOREST_PALE, FOREST_DARK, italic=True, size=9, align="CENTER"))]

    # Rij 4: UITGAAND header
    reqs += [req_hoogte(ws, 4, 30), req_merge(ws, 4, 1, 1, 7),
             req_format(ws, 4, 1, 1, 7, cel_fmt(FOREST_MED, WHITE, bold=True, size=12))]

    # Rij 5: Kolomhoofden UITGAAND
    reqs += [req_hoogte(ws, 5, 25),
             req_format(ws, 5, 1, 1, 7, cel_fmt(FOREST_DARK, WHITE, bold=True, size=10, align="CENTER"))]

    batch(ws, reqs)
    reqs = []

    # Waarden rij 1-2 en headers
    nu = datetime.now()
    vand = f"{nu.day} {MAANDEN[nu.month-1]} {nu.year} om {nu.strftime('%H:%M')}"
    ws.update([[f"THE GREEN LODGE - BTW AANGIFTE {tab_naam}"]], "A1")
    ws.update([[f"Gegenereerd op {vand}"]], "A2")
    ws.update([["UITGAAND (OMZET UIT BOEKINGEN)"]], "A4")
    ws.update([["Datum","Platform","Gast","Bedrag excl. BTW","BTW","Totaal incl. BTW","Opmerkingen"]], "A5")

    # UITGAAND boekingen
    boekingen = lees_btw_boekingen(gc, jaar, kwartaal, log=log)
    rij = 6
    data_start = rij

    if not boekingen:
        ws.update([["Geen boekingen in dit kwartaal."]], f"A{rij}")
        reqs += [req_merge(ws, rij, 1, 1, 7),
                 req_format(ws, rij, 1, 1, 7, cel_fmt(WHITE, "#888888", italic=True, align="CENTER"))]
        rij += 1
    else:
        rijen_data = []
        for i, b in enumerate(boekingen):
            bg = CREAM if i % 2 == 0 else CREAM_ALT
            rijen_data.append([b["datum"],b["site"],b["gast"],b["bedrag_ex_btw"],b["btw_bedrag"],b["totaalbedrag"],b["opmerking"]])
            reqs.append(req_format(ws, rij+i, 1, 1, 7, cel_fmt(bg, "#000000")))
            reqs.append(req_getal(ws, rij+i, 4, 1, 3))
        ws.update(rijen_data, f"A{rij}")
        rij += len(boekingen)

    # TOTAAL UITGAAND
    tot_uit = rij
    reqs += [req_hoogte(ws, rij, 30), req_merge(ws, rij, 1, 1, 3),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_PALE, FOREST_DARK, bold=True))]
    ws.update([["TOTAAL UITGAAND","",""]], f"A{rij}")
    if boekingen:
        for kol, ltr in [(4,"D"),(5,"E"),(6,"F")]:
            ws.update_cell(rij, kol, f"=SUM({ltr}{data_start}:{ltr}{rij-1})")
            reqs.append(req_getal(ws, rij, kol))
    batch(ws, reqs)
    reqs = []
    rij += 2

    # INKOMEND header
    in_header = rij
    reqs += [req_hoogte(ws, rij, 30), req_merge(ws, rij, 1, 1, 7),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_MED, WHITE, bold=True, size=12))]
    ws.update([["INKOMEND (KOSTEN / BONNETJES)"]], f"A{rij}")
    rij += 1

    # Kolomhoofden INKOMEND
    reqs += [req_hoogte(ws, rij, 25),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_DARK, WHITE, bold=True, size=10, align="CENTER"))]
    ws.update([["Datum","Omschrijving","Leverancier","Bedrag excl. BTW","BTW","Totaal incl. BTW","Opmerkingen"]], f"A{rij}")
    rij += 1

    # 20 lege datarijen voor bonnetjes
    in_data_start = rij
    for i in range(20):
        bg = LIGHT_GREY if i % 2 == 0 else WHITE
        reqs.append(req_format(ws, rij+i, 1, 1, 7, cel_fmt(bg, "#000000")))
        reqs.append(req_getal(ws, rij+i, 4, 1, 3))
    rij += 20

    # TOTAAL INKOMEND
    tot_in = rij
    reqs += [req_hoogte(ws, rij, 30), req_merge(ws, rij, 1, 1, 3),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_PALE, FOREST_DARK, bold=True))]
    ws.update([["TOTAAL INKOMEND","",""]], f"A{rij}")
    for kol, ltr in [(4,"D"),(5,"E"),(6,"F")]:
        ws.update_cell(rij, kol, f"=SUM({ltr}{in_data_start}:{ltr}{rij-1})")
        reqs.append(req_getal(ws, rij, kol))
    batch(ws, reqs)
    reqs = []
    rij += 2

    # SAMENVATTING BTW header
    reqs += [req_hoogte(ws, rij, 30), req_merge(ws, rij, 1, 1, 7),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_MED, WHITE, bold=True, size=12))]
    ws.update([["SAMENVATTING BTW"]], f"A{rij}")
    rij += 1

    # BTW af te dragen
    reqs += [req_merge(ws, rij, 1, 1, 3),
             req_format(ws, rij, 1, 1, 7, cel_fmt(CREAM, "#000000", bold=True))]
    ws.update([["BTW af te dragen (uitgaand)","",""]], f"A{rij}")
    ws.update_cell(rij, 4, f"=E{tot_uit}")
    reqs.append(req_getal(ws, rij, 4))
    afdragen_rij = rij
    rij += 1

    # BTW te vorderen
    reqs += [req_merge(ws, rij, 1, 1, 3),
             req_format(ws, rij, 1, 1, 7, cel_fmt(CREAM, "#000000", bold=True))]
    ws.update([["BTW te vorderen (inkomend)","",""]], f"A{rij}")
    ws.update_cell(rij, 4, f"=E{tot_in}")
    reqs.append(req_getal(ws, rij, 4))
    vorderen_rij = rij
    rij += 1

    # BTW TE BETALEN
    reqs += [req_hoogte(ws, rij, 35), req_merge(ws, rij, 1, 1, 3),
             req_format(ws, rij, 1, 1, 7, cel_fmt(FOREST_DARK, WHITE, bold=True, size=12))]
    ws.update([["BTW TE BETALEN","",""]], f"A{rij}")
    ws.update_cell(rij, 4, f"=ROUNDDOWN(D{afdragen_rij}-D{vorderen_rij};0)")
    reqs.append(req_getal(ws, rij, 4))

    reqs.append(req_freeze(ws, 2))
    batch(ws, reqs)

    log(f"  ✅ '{tab_naam}' aangemaakt — {len(boekingen)} boeking(en) in UITGAAND.")
    return ws

# ── Bonnetjes schrijven naar INKOMEND ────────────────────────────────────────

def zoek_structuurrijen(ws) -> dict:
    """Zoekt de rijnummers van structuurrijen in een kwartaalblad."""
    kolom_a = ws.col_values(1)
    rijen = {"inkomend_header": None, "totaal_inkomend": None, "samenvatting": None}
    for i, v in enumerate(kolom_a, 1):
        v_upper = str(v).upper()
        if "INKOMEND (KOSTEN" in v_upper:
            rijen["inkomend_header"] = i
        elif "TOTAAL INKOMEND" in v_upper:
            rijen["totaal_inkomend"] = i
        elif "SAMENVATTING BTW" in v_upper:
            rijen["samenvatting"] = i
    return rijen

def schrijf_bonnetjes(sh, tab_naam: str, bonnetjes: list, log):
    """Schrijft gescande bonnetjes naar de INKOMEND sectie."""
    try:
        ws = sh.worksheet(tab_naam)
    except Exception:
        log(f"  ⚠️ Tabblad '{tab_naam}' niet gevonden.")
        return

    structuur = zoek_structuurrijen(ws)
    if not structuur["inkomend_header"] or not structuur["totaal_inkomend"]:
        log(f"  ⚠️ Structuur niet herkend in '{tab_naam}'.")
        return

    in_header     = structuur["inkomend_header"]
    totaal_in_rij = structuur["totaal_inkomend"]
    samenvatting  = structuur["samenvatting"]
    data_start    = in_header + 2  # header + kolomhoofdrij

    # Zoek eerste lege rij onder data_start
    kolom_a = ws.col_values(1)
    volgende_rij = totaal_in_rij  # default: direct boven totaal
    for i in range(data_start - 1, totaal_in_rij - 1):
        if i >= len(kolom_a) or not str(kolom_a[i]).strip():
            volgende_rij = i + 1
            break

    # Lees bestaande rijen en filter duplicaten vóór rij-invoeging
    bestaande = ws.get(f"A{data_start}:G{totaal_in_rij - 1}") or []

    def als_float(waarde) -> Optional[float]:
        try:
            return round(float(str(waarde).replace("€","").replace(",",".").strip()), 2)
        except (ValueError, TypeError):
            return None

    def is_duplicaat(b) -> bool:
        datum  = str(b.get("datum") or "").strip()
        totaal = als_float(b.get("totaalbedrag"))
        lev    = str(b.get("leverancier") or "").strip().lower()
        for r in bestaande:
            r = (r + [""] * 7)[:7]
            r_datum  = str(r[0]).strip()
            r_totaal = als_float(r[5])
            r_lev    = str(r[2]).strip().lower()
            if r_datum == datum and r_totaal == totaal:
                if r_lev == lev:
                    return True
                # Zelfde datum+bedrag maar andere leverancier: waarschijnlijk zelfde transactie
                log(f"  ⚠️ Mogelijke dup: {datum} €{totaal} — '{b.get('leverancier')}' vs '{r[2]}' (beide opgeslagen)")
        return False

    nieuw = []
    for b in bonnetjes:
        if is_duplicaat(b):
            naam = Path(b.get("_bestand", "")).name
            log(f"  ⏭️ {naam} — al aanwezig, overgeslagen")
        else:
            nieuw.append(b)
    bonnetjes = nieuw
    if not bonnetjes:
        log(f"  Alle bonnetjes waren al aanwezig in '{tab_naam}'.")
        return

    # Voeg rijen in als er niet genoeg ruimte is (na filtering)
    tekort = (volgende_rij + len(bonnetjes)) - totaal_in_rij
    if tekort > 0:
        log(f"  → {tekort} extra rij(en) invoegen…")
        reqs = [{"insertDimension": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": totaal_in_rij - 1,
                      "endIndex": totaal_in_rij - 1 + tekort},
            "inheritFromBefore": True,
        }}]
        batch(ws, reqs)

        # Herlaad structuurrijen na invoeging
        structuur = zoek_structuurrijen(ws)
        totaal_in_rij = structuur["totaal_inkomend"]

    def btw_lookup(b) -> tuple:
        """Geeft (excl, btw, totaal) terug — vult ontbrekende BTW aan via BTW_TARIEVEN."""
        excl  = als_float(b.get("bedrag_ex_btw"))
        btw   = als_float(b.get("btw_bedrag"))
        tot   = als_float(b.get("totaalbedrag"))
        if tot and not btw:
            lev_lower = str(b.get("leverancier") or "").lower()
            for sleutel, tarief in BTW_TARIEVEN.items():
                if sleutel in lev_lower:
                    btw  = round(tot * tarief / (1 + tarief), 2)
                    excl = round(tot - btw, 2)
                    break
        return excl or "", btw or "", tot or ""

    # Schrijf bonnetjes
    reqs = []
    for i, b in enumerate(bonnetjes):
        rij = volgende_rij + i
        onvolledig = b.get("_onvolledig", False)
        fg = "#FF0000" if onvolledig else "#000000"
        bg_idx = rij - data_start
        bg = CREAM if bg_idx % 2 == 0 else CREAM_ALT

        excl, btw, tot = btw_lookup(b)
        ws.update([[
            b.get("datum") or "",
            b.get("omschrijving") or "",
            b.get("leverancier") or "",
            excl, btw, tot,
            Path(b.get("_bestand", "")).name if onvolledig else (b.get("opmerkingen") or ""),
        ]], f"A{rij}")

        reqs.append(req_format(ws, rij, 1, 1, 7, cel_fmt(bg, fg)))
        reqs.append(req_getal(ws, rij, 4, 1, 3))

        naam = Path(b.get("_bestand", "")).name
        if onvolledig:
            log(f"  ⚠️ {naam} — onvolledig (rode tekst), methode: {b.get('_methode','?')}")
        else:
            log(f"  ✅ {naam} — OK via {b.get('_methode','?')}")

    if reqs:
        batch(ws, reqs)

    # Formule altijd bijwerken zodat bereik klopt na invoeging van rijen
    structuur = zoek_structuurrijen(ws)
    totaal_in_rij = structuur["totaal_inkomend"]
    reqs = []
    for kol, ltr in [(4, "D"), (5, "E"), (6, "F")]:
        ws.update_cell(totaal_in_rij, kol, f"=SUM({ltr}{data_start}:{ltr}{totaal_in_rij-1})")
        reqs.append(req_getal(ws, totaal_in_rij, kol))
    if reqs:
        batch(ws, reqs)

    log(f"  {len(bonnetjes)} bonnetje(s) toegevoegd aan '{tab_naam}'.")

# ── Sorteer INKOMEND op datum ─────────────────────────────────────────────────

def sorteer_inkomend(sh, tab_naam: str, log):
    """Sorteert de INKOMEND sectie op datum (oudste bovenaan, nieuwste onderaan)."""
    try:
        ws = sh.worksheet(tab_naam)
    except Exception:
        return

    structuur = zoek_structuurrijen(ws)
    if not structuur["inkomend_header"] or not structuur["totaal_inkomend"]:
        return

    data_start    = structuur["inkomend_header"] + 2
    totaal_in_rij = structuur["totaal_inkomend"]

    if totaal_in_rij <= data_start:
        return

    # Lees alle datarijen
    rijen = ws.get(f"A{data_start}:G{totaal_in_rij - 1}")
    if not rijen:
        return

    # Filter lege rijen en sorteer op datum (kolom A = DD-MM-YYYY)
    def datum_sort_key(rij):
        datum = str(rij[0]).strip() if rij else ""
        try:
            return datetime.strptime(datum, "%d-%m-%Y")
        except ValueError:
            return datetime.max  # lege/ongeldige datums naar het einde

    gevuld = [r for r in rijen if any(str(c).strip() for c in r)]
    leeg   = [r for r in rijen if not any(str(c).strip() for c in r)]
    gevuld.sort(key=datum_sort_key)

    gesorteerd = gevuld + leeg

    # Schrijf terug
    # Zorg dat alle rijen 7 kolommen hebben
    genorm = [(r + [""] * 7)[:7] for r in gesorteerd]
    ws.update(genorm, f"A{data_start}")

    # Herkleur zebra-stripes
    reqs = []
    for i, _ in enumerate(gesorteerd):
        rij = data_start + i
        bg = CREAM if i % 2 == 0 else CREAM_ALT
        reqs.append(req_format(ws, rij, 1, 1, 7, cel_fmt(bg, "#000000")))
        reqs.append(req_getal(ws, rij, 4, 1, 3))
    if reqs:
        batch(ws, reqs)

    log(f"  ✅ INKOMEND gesorteerd op datum in '{tab_naam}'.")

# ── Vernieuw UITGAAND ─────────────────────────────────────────────────────────

def vernieuw_uitgaand(sh, gc, jaar: int, kwartaal: int, log):
    """Ververst alleen de UITGAAND sectie van een bestaand kwartaalblad."""
    tab_naam = f"Q{kwartaal} {jaar}"
    log(f"Vernieuwen UITGAAND voor {tab_naam}…")

    try:
        ws = sh.worksheet(tab_naam)
    except Exception:
        log(f"⚠️ Tab '{tab_naam}' bestaat niet.")
        return

    log(f"  Structuur lezen…")
    kolom_a = ws.col_values(1)
    header_rij = None
    totaal_rij = None

    for i, v in enumerate(kolom_a, 1):
        if str(v).strip() == "Datum" and header_rij is None and i < 10:
            header_rij = i
        if "TOTAAL UITGAAND" in str(v).upper():
            totaal_rij = i
            break

    if not header_rij or not totaal_rij:
        log(f"⚠️ Structuur niet herkend in '{tab_naam}'.")
        return

    log(f"  Boekingen ophalen uit bronbestand…")
    data_start      = header_rij + 1
    bestaande_rijen = totaal_rij - data_start
    boekingen       = lees_btw_boekingen(gc, jaar, kwartaal, log=log)
    log(f"  {len(boekingen)} boeking(en) gevonden voor Q{kwartaal} {jaar}.")
    verschil        = len(boekingen) - bestaande_rijen

    reqs = []
    if verschil > 0:
        reqs.append({"insertDimension": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": totaal_rij - 1, "endIndex": totaal_rij - 1 + verschil},
            "inheritFromBefore": True,
        }})
        totaal_rij += verschil
    elif verschil < 0:
        reqs.append({"deleteDimension": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": data_start - 1, "endIndex": data_start - 1 + (-verschil)},
        }})
        totaal_rij += verschil

    if reqs:
        batch(ws, reqs)
        reqs = []

    if bestaande_rijen > 0:
        ws.batch_clear([f"A{data_start}:G{totaal_rij-1}"])

    if boekingen:
        log(f"  Schrijven naar spreadsheet…")
        rijen_data = []
        for i, b in enumerate(boekingen):
            bg = CREAM if i % 2 == 0 else CREAM_ALT
            rijen_data.append([b["datum"],b["site"],b["gast"],b["bedrag_ex_btw"],b["btw_bedrag"],b["totaalbedrag"],b["opmerking"]])
            reqs.append(req_format(ws, data_start+i, 1, 1, 7, cel_fmt(bg, "#000000")))
            reqs.append(req_getal(ws, data_start+i, 4, 1, 3))
        ws.update(rijen_data, f"A{data_start}")

    for kol, ltr in [(4,"D"),(5,"E"),(6,"F")]:
        ws.update_cell(totaal_rij, kol, f"=SUM({ltr}{data_start}:{ltr}{totaal_rij-1})")
        reqs.append(req_getal(ws, totaal_rij, kol))

    if reqs:
        batch(ws, reqs)

    log(f"✅ UITGAAND vernieuwd — {len(boekingen)} boeking(en).")

# ── GUI ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self._q = queue.Queue()
        self._bezig = False

        GROEN = "#3A7A28"
        self._logbestand = Path(__file__).parent / "btw_import_session.log"
        self._logbestand.write_text("")  # leegmaken bij start

        root.title("The Green Lodge — BTW Import")
        root.geometry("700x560")
        root.resizable(True, True)
        root.lift()
        root.after(200, lambda: root.focus_force())

        # ── Header ──
        header = ctk.CTkFrame(root, fg_color="#152310", corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="THE GREEN LODGE",
                     font=ctk.CTkFont("Arial", 15, "bold"),
                     text_color="#FFFFFF").pack(pady=(12, 2))
        ctk.CTkLabel(header, text="BTW Import & Bonnetjes Scanner",
                     font=ctk.CTkFont("Arial", 10),
                     text_color="#C8F0A0").pack(pady=(0, 12))

        # ── Knoppen ──
        knop_frame = ctk.CTkFrame(root, fg_color="transparent")
        knop_frame.pack(pady=18)
        self.knop_import = ctk.CTkButton(
            knop_frame, text="Importeer bonnetjes",
            command=self.kies_en_importeer,
            fg_color=GROEN, hover_color="#4A9A35",
            font=ctk.CTkFont("Arial", 12, "bold"),
            width=185, height=44)
        self.knop_import.pack(side="left", padx=10)

        self.knop_boekingen = ctk.CTkButton(
            knop_frame, text="Werk boekingen bij",
            command=self.start_vernieuw,
            fg_color=GROEN, hover_color="#4A9A35",
            font=ctk.CTkFont("Arial", 12, "bold"),
            width=185, height=44)
        self.knop_boekingen.pack(side="left", padx=10)

        # ── Status + voortgang ──
        vf = ctk.CTkFrame(root, fg_color="transparent")
        vf.pack(fill="x", padx=24, pady=(0, 6))

        self._status_label = ctk.CTkLabel(
            vf, text=" ",
            font=ctk.CTkFont("Arial", 10, "bold"),
            text_color="#C8F0A0", anchor="w")
        self._status_label.pack(fill="x", pady=(0, 3))

        self.voortgang = ctk.CTkProgressBar(
            vf, fg_color="#1A3010", progress_color=GROEN, height=12)
        self.voortgang.set(0)
        self.voortgang.pack(fill="x")
        self._voortgang_max = 1

        # ── Log venster ──
        ctk.CTkLabel(root, text="Logboek",
                     font=ctk.CTkFont("Arial", 9, "bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=26, pady=(8, 0))
        self.log_vak = ctk.CTkTextbox(
            root,
            fg_color="#0C1A08",
            text_color="#B8F090",
            font=ctk.CTkFont("Courier New", 10),
            wrap="word",
            border_width=1,
            border_color="#3A7A28",
            scrollbar_button_color="#3A7A28")
        self.log_vak.pack(fill="both", expand=True, padx=24, pady=(2, 16))

        self._poll_queue()
        self._schrijf_log("Klaar — kies een actie.")

    def _poll_queue(self):
        """Verwerkt berichten uit de queue op de hoofdthread."""
        try:
            while True:
                msg = self._q.get_nowait()
                soort = msg.get("soort")
                if soort == "log":
                    self.log_vak.insert("end", msg["tekst"] + "\n")
                    self.log_vak.yview_moveto(1.0)
                elif soort == "status":
                    self._status_label.configure(text=msg["tekst"])
                elif soort == "voortgang":
                    kwargs = msg["kwargs"]
                    if "maximum" in kwargs:
                        self._voortgang_max = max(kwargs["maximum"], 1)
                        self.voortgang.set(0)
                    elif "value" in kwargs:
                        self.voortgang.set(kwargs["value"] / self._voortgang_max)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _schrijf_log(self, tekst: str):
        """Schrijft direct naar log (alleen vanuit hoofdthread)."""
        self.log_vak.insert("end", tekst + "\n")
        self.log_vak.yview_moveto(1.0)
        with self._logbestand.open("a") as f:
            f.write(tekst + "\n")

    def log(self, tekst: str):
        self._q.put({"soort": "log", "tekst": tekst})
        with self._logbestand.open("a") as f:
            f.write(tekst + "\n")

    def status(self, tekst: str):
        self._q.put({"soort": "status", "tekst": tekst})

    def set_voortgang(self, waarde: int):
        self._q.put({"soort": "voortgang", "kwargs": {"value": waarde}})

    def verbind(self):
        try:
            gc = get_gspread()
            sh = gc.open_by_key(BTW_SHEET_ID)
            return gc, sh
        except Exception as e:
            self.log(f"❌ Verbinding mislukt: {e}")
            return None, None

    def kies_en_importeer(self):
        """Bestandsselectie op hoofdthread, verwerking in achtergrondthread."""
        bestanden = filedialog.askopenfilenames(
            title="Selecteer bonnetjes",
            filetypes=[
                ("Afbeeldingen & PDF", "*.jpg *.jpeg *.png *.webp *.pdf"),
                ("Alle bestanden", "*.*"),
            ],
        )
        if not bestanden:
            return
        threading.Thread(target=self.importeer_bonnetjes, args=(bestanden,), daemon=True).start()

    def importeer_bonnetjes(self, bestanden):
        if not bestanden:
            return

        totaal = len(bestanden)
        self.log(f"\n{'─' * 50}")
        self.log(f"Geselecteerd: {totaal} bestand(en)")
        self._q.put({"soort": "voortgang", "kwargs": {"maximum": totaal}})

        self.status("Verbinden met Google Sheets…")
        gc, sh = self.verbind()
        if not sh:
            self.status("Verbinding mislukt")
            return

        self.log("✅ Verbonden met Google Sheets")
        per_kwartaal = {}

        for i, pad in enumerate(bestanden, 1):
            path = Path(pad)
            self.status(f"Scannen {i}/{totaal}: {path.name}")
            self.log(f"\n[{i}/{totaal}] {path.name}")
            try:
                data = scan_bonnetje(path, self.log, self.status)
                data["_bestand"] = pad
                kwnaam = kwartaal_naam(data.get("datum") or "")
                if kwnaam:
                    per_kwartaal.setdefault(kwnaam, []).append(data)
                else:
                    data["_onvolledig"] = True
                    per_kwartaal.setdefault("onbekend", []).append(data)
                    self.log("  ⚠️ Datum onbekend — kwartaal niet te bepalen")
            except Exception as e:
                self.log(f"  ❌ Overgeslagen: {e}")
            self.set_voortgang(i)

        for kwnaam, bonnetjes in per_kwartaal.items():
            if kwnaam == "onbekend":
                self.log(f"\n⚠️ {len(bonnetjes)} bonnetje(s) zonder datum overgeslagen.")
                continue

            self.status(f"Schrijven naar {kwnaam}…")
            self.log(f"\nSchrijven naar '{kwnaam}'…")
            parts = kwnaam.split()
            q    = int(parts[0][1])
            jaar = int(parts[1])

            try:
                sh.worksheet(kwnaam)
            except Exception:
                self.status(f"Aanmaken tabblad {kwnaam}…")
                maak_kwartaal_tab(sh, kwnaam, jaar, q, gc, self.log)

            schrijf_bonnetjes(sh, kwnaam, bonnetjes, self.log)
            self.status(f"Sorteren op datum in {kwnaam}…")
            sorteer_inkomend(sh, kwnaam, self.log)

        self.status("Klaar")
        self.log(f"\n✅ Klaar.")

    def start_vernieuw(self):
        threading.Thread(target=self.vernieuw_uitgaand, daemon=True).start()

    def vernieuw_uitgaand(self):
        nu = datetime.now()
        q  = (nu.month - 1) // 3 + 1

        self.log(f"\n{'─' * 50}")
        self.log(f"Vernieuwen UITGAAND — Q{q} {nu.year}")
        self.status(f"Verbinden…")

        gc, sh = self.verbind()
        if not sh:
            self.status("Verbinding mislukt")
            return

        self.status(f"Vernieuwen UITGAAND Q{q} {nu.year}…")
        vernieuw_uitgaand(sh, gc, nu.year, q, self.log)
        self.status("Klaar")


def _forceer_licht_mode():
    """Forceert light-mode via ctypes (werkt zonder PyObjC)."""
    try:
        import ctypes, ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p

        def msg(receiver, sel, *args):
            types = [ctypes.c_void_p, ctypes.c_void_p] + [type(a) for a in args]
            objc.objc_msgSend.argtypes = types
            objc.objc_msgSend.restype = ctypes.c_void_p
            return objc.objc_msgSend(receiver, sel, *args)

        NSString    = objc.objc_getClass(b'NSString')
        NSApp_cls   = objc.objc_getClass(b'NSApplication')
        NSApp_cls2  = objc.objc_getClass(b'NSAppearance')

        utf8_       = objc.sel_registerName(b'stringWithUTF8String:')
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        objc.objc_msgSend.restype  = ctypes.c_void_p
        aqua_str = objc.objc_msgSend(NSString, utf8_, b'NSAppearanceNameAqua')

        named_ = objc.sel_registerName(b'appearanceNamed:')
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        appearance = objc.objc_msgSend(NSApp_cls2, named_, aqua_str)

        shared_ = objc.sel_registerName(b'sharedApplication')
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        app = objc.objc_msgSend(NSApp_cls, shared_)

        set_ = objc.sel_registerName(b'setAppearance:')
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        objc.objc_msgSend(app, set_, appearance)
    except Exception:
        pass


def main():
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        root = ctk.CTk()
        App(root)
        root.mainloop()
    except Exception as e:
        import traceback
        print("\n❌ Opstartfout:\n", traceback.format_exc(), file=sys.stderr)
        input("Druk Enter om te sluiten…")


if __name__ == "__main__":
    main()
