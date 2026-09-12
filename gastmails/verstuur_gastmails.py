#!/usr/bin/env python3
"""
Verstuurt automatische gastenmails voor Natuurhuisje-boekingen bij The Green Lodge.

Leest boekingen rechtstreeks (publiek, zonder inloggen) uit het bronbestand via de
gviz-CSV-export, en verstuurt drie mails op de juiste momenten t.o.v. een boeking:

  Mail 1 - welkomstinformatie   : 5 dagen vóór check-in, tussen 14:00-15:00 (Europe/Amsterdam)
  Mail 2 - hoe bevalt het       : 1 dag na check-in
  Mail 3 - vertrekinstructies   : de dag vóór uitchecken

Draait via GitHub Actions (elk uur); het script doet zelf niets buiten het venster
14:00-15:00 Amsterdamse tijd, dus DST wordt automatisch goed afgehandeld.

Na elke geslaagde gastmail krijgt kim@thegreenlodge.nl zelf een korte interne
notificatiemail (platte tekst) dat en aan wie de mail verstuurd is.

Vereist env vars: STRATO_EMAIL, STRATO_WACHTWOORD
"""
import csv
import io
import json
import os
import smtplib
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

BRONBESTAND_ID = "1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg"
AFZENDER_ADRES = "kim@thegreenlodge.nl"

# gid per jaartabblad - de gviz "sheet=<naam>"-variant verschuift/laat kop- en
# databronrijen wegvallen bij deze sheet (merges in rij 1-3), dus we gebruiken de
# directe export-URL met het echte gid. Voeg de gid van een nieuw jaar hier toe
# zodra nieuw_boekjaar.py dat tabblad heeft aangemaakt (te vinden via de URL-balk
# op dat tabblad in Google Sheets, na "gid=").
GID_PER_JAAR = {
    2025: 1927165059,
    2026: 1587699778,
    2027: 1356875464,
}

HIER = Path(__file__).parent
LOG_PAD = HIER / "verzonden_log.json"
LOGO_PAD = HIER / "logo.png"

MAILS = {
    "mail1": {
        "template": HIER / "templates" / "mail1_welkom.html",
        "onderwerp": "Bijna zover: praktische info voor je verblijf bij The Green Lodge",
        "afzender_naam": "Kim & Niels - The Green Lodge",
        "label": "Mail 1 (welkomstinformatie, 5 dagen voor aankomst)",
    },
    "mail2": {
        "template": HIER / "templates" / "mail2_hoebevalt.html",
        "onderwerp": "Hoe bevalt het bij The Green Lodge?",
        "afzender_naam": "Kim - The Green Lodge",
        "label": "Mail 2 (hoe bevalt het, 1 dag na aankomst)",
    },
    "mail3": {
        "template": HIER / "templates" / "mail3_vertrek.html",
        "onderwerp": "Bedankt voor je verblijf bij The Green Lodge",
        "afzender_naam": "Kim & Niels - The Green Lodge",
        "label": "Mail 3 (vertrekinstructies, dag voor uitchecken)",
    },
}


def haal_tabblad(jaar):
    """Haalt alle boekingsrijen van een jaartabblad op via de publieke CSV-export."""
    gid = GID_PER_JAAR.get(jaar)
    if gid is None:
        print(f"  tabblad {jaar}: geen gid bekend, overgeslagen")
        return []
    url = (
        f"https://docs.google.com/spreadsheets/d/{BRONBESTAND_ID}"
        f"/export?format=csv&gid={gid}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  tabblad {jaar}: niet opgehaald ({e}), overgeslagen")
        return []

    rijen = list(csv.reader(io.StringIO(data)))
    if len(rijen) < 5:
        return []
    headers = rijen[3]
    boekingen = []
    for rij in rijen[4:]:
        if not any(rij):
            continue
        if len(rij) < len(headers):
            rij = rij + [""] * (len(headers) - len(rij))
        boekingen.append(dict(zip(headers, rij)))
    return boekingen


def parse_datum(tekst):
    tekst = (tekst or "").strip()
    if not tekst:
        return None
    try:
        return datetime.strptime(tekst, "%d-%m-%Y").date()
    except ValueError:
        return None


def is_bevestigd(boeking):
    return "bevestig" in (boeking.get("Status") or "").strip().lower()


def sleutel(boeking, mailtype):
    return "|".join([
        boeking.get("Check-in datum", ""),
        boeking.get("Voornaam", ""),
        boeking.get("Achternaam", ""),
        mailtype,
    ])


def laad_log():
    if LOG_PAD.exists():
        return json.loads(LOG_PAD.read_text())
    return {}


def bewaar_log(log):
    LOG_PAD.write_text(json.dumps(log, indent=2, ensure_ascii=False, sort_keys=True))


def bepaal_te_versturen(boekingen, vandaag):
    """Geeft (boeking, mailtype)-paren terug die vandaag verstuurd moeten worden."""
    te_versturen = []
    for boeking in boekingen:
        if (boeking.get("Boekingsite") or "").strip().lower() != "natuurhuisje":
            continue
        if not is_bevestigd(boeking):
            continue
        checkin = parse_datum(boeking.get("Check-in datum"))
        checkout = parse_datum(boeking.get("Uitcheckdatum"))

        if checkin and checkin - timedelta(days=5) == vandaag:
            te_versturen.append((boeking, "mail1"))
        if checkin and checkin + timedelta(days=1) == vandaag:
            te_versturen.append((boeking, "mail2"))
        if checkout and checkout - timedelta(days=1) == vandaag:
            te_versturen.append((boeking, "mail3"))
    return te_versturen


def bouw_email(mailtype, boeking, wachtwoord_niet_nodig=None):
    info = MAILS[mailtype]
    html = info["template"].read_text(encoding="utf-8")
    voornaam = (boeking.get("Voornaam") or "").strip() or "gast"
    html = html.replace("{{voornaam}}", voornaam)

    gast_adres = (boeking.get("E-mailadres gast") or "").strip()

    msg = MIMEMultipart("related")
    msg["Subject"] = info["onderwerp"]
    msg["From"] = f'{info["afzender_naam"]} <{AFZENDER_ADRES}>'
    msg["To"] = gast_adres

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    with open(LOGO_PAD, "rb") as f:
        logo = MIMEImage(f.read())
    logo.add_header("Content-ID", "<logo_green_lodge>")
    logo.add_header("Content-Disposition", "inline", filename="logo.png")
    msg.attach(logo)

    return msg, gast_adres


def bouw_notificatie(mailtype, boeking, gast_adres):
    info = MAILS[mailtype]
    naam = f"{boeking.get('Voornaam','')} {boeking.get('Achternaam','')}".strip()
    checkin = boeking.get("Check-in datum", "")

    tekst = (
        f"{info['label']} is zojuist verstuurd.\n\n"
        f"Gast: {naam}\n"
        f"E-mailadres: {gast_adres}\n"
        f"Check-in: {checkin}\n"
        f"Onderwerp: {info['onderwerp']}\n"
    )

    msg = MIMEText(tekst, "plain", "utf-8")
    msg["Subject"] = f"Gastmail verstuurd: {info['label']} - {naam}"
    msg["From"] = f"Gastmails The Green Lodge <{AFZENDER_ADRES}>"
    msg["To"] = AFZENDER_ADRES
    return msg


def verstuur(msg, gast_adres, email, wachtwoord):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.strato.de", 465, context=context) as server:
        server.login(email, wachtwoord)
        server.sendmail(email, [gast_adres], msg.as_string())


def stuur_testmails(test_adres, email, wachtwoord):
    """Stuurt alle drie de mails (+ notificatie) naar test_adres, los van datum/uur/log."""
    testboeking = {
        "Voornaam": "Test",
        "Achternaam": "Persoon",
        "Check-in datum": "01-01-2030",
    }
    for mailtype in ("mail1", "mail2", "mail3"):
        msg, _ = bouw_email(mailtype, {**testboeking, "E-mailadres gast": test_adres})
        verstuur(msg, test_adres, email, wachtwoord)
        print(f"  testmail {mailtype} verstuurd aan {test_adres}")

        notificatie = bouw_notificatie(mailtype, testboeking, test_adres)
        verstuur(notificatie, AFZENDER_ADRES, email, wachtwoord)
        print(f"  testnotificatie {mailtype} verstuurd aan {AFZENDER_ADRES}")


def main():
    email = os.environ.get("STRATO_EMAIL")
    wachtwoord = os.environ.get("STRATO_WACHTWOORD")
    if not email or not wachtwoord:
        print("STRATO_EMAIL of STRATO_WACHTWOORD ontbreekt, stop.", file=sys.stderr)
        sys.exit(1)

    test_adres = os.environ.get("TEST_ADRES", "").strip()
    if test_adres:
        print(f"Testmodus: alle drie mails + notificaties naar {test_adres}")
        stuur_testmails(test_adres, email, wachtwoord)
        return

    nu_nl = datetime.now(ZoneInfo("Europe/Amsterdam"))
    if nu_nl.hour != 14:
        print(f"Geen verzenduur ({nu_nl.strftime('%H:%M')} Amsterdamse tijd), stop.")
        return

    vandaag = nu_nl.date()
    log = laad_log()
    gewijzigd = False

    boekingen = []
    for jaar in (vandaag.year - 1, vandaag.year, vandaag.year + 1):
        boekingen += haal_tabblad(jaar)

    te_versturen = bepaal_te_versturen(boekingen, vandaag)
    print(f"{len(te_versturen)} mail(s) te beoordelen voor {vandaag.isoformat()}")

    for boeking, mailtype in te_versturen:
        key = sleutel(boeking, mailtype)
        naam = f"{boeking.get('Voornaam','')} {boeking.get('Achternaam','')}".strip()

        if key in log:
            continue

        gast_adres = (boeking.get("E-mailadres gast") or "").strip()
        if not gast_adres:
            print(f"  {mailtype} voor {naam}: geen e-mailadres gast bekend, overgeslagen")
            continue

        msg, gast_adres = bouw_email(mailtype, boeking)
        try:
            verstuur(msg, gast_adres, email, wachtwoord)
            print(f"  {mailtype} verstuurd aan {naam} <{gast_adres}>")
            log[key] = datetime.now(ZoneInfo("Europe/Amsterdam")).isoformat()
            gewijzigd = True
        except Exception as e:
            print(f"  {mailtype} voor {naam} MISLUKT: {e}", file=sys.stderr)
            continue

        try:
            notificatie = bouw_notificatie(mailtype, boeking, gast_adres)
            verstuur(notificatie, AFZENDER_ADRES, email, wachtwoord)
        except Exception as e:
            print(f"  notificatie naar Kim voor {naam} mislukt: {e}", file=sys.stderr)

    if gewijzigd:
        bewaar_log(log)


if __name__ == "__main__":
    main()
