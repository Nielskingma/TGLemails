# boekhouding-tgl — WERKINSTRUCTIE

## Doel
BTW-administratie voor The Green Lodge: bonnetjes scannen, verwerken en per kwartaal bijhouden in Google Sheets.

## Huidige staat
Q1 2026: compleet, saldo geverifieerd tegen de ingediende PDF op 17 sep 2026: BTW-saldo
-€48,89 (teruggave) — zie "Opgeloste bugs (17 sep 2026)" hieronder, oudere -€51,49 in deze
instructie was onjuist.
Q2 2026: volledig verwerkt. BTW TE BETALEN = €573,00. Aangifte indienen vóór 31 jul 2026.
Q3 2026: 14 bonnetjes uit de map verwerkt (18 sep 2026), BTW TE BETALEN nu €2.246,72
(nog niet ingediend, kwartaal loopt door t/m 30 sep).

## Architectuur
bonnetjes (PDF/foto) → scan_receipt.py → Google Sheets (kwartaalblad)
map bewaken          → watch_bonnetjes.py → scan_receipt.py (automatisch)
nieuw kwartaal       → nieuw_kwartaal.py → kopie vorig kwartaalblad
BTW-import GUI       → btw_import.py → boekingen uit bronbestand + bonnetjes via OCR/Claude
nieuw boekjaar       → nieuw_boekjaar.py → kopie vorig jaartabblad in bronbestand
                        (gebeurt ook automatisch vanuit btw_import.py, zie hieronder)

Spreadsheet ID: 1sXOnJpfsvgcAdGU4Bp6uzVUCFL7vXdn1JqNWFhntTjw
Bronbestand ID: 1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg (verhuur_bronbestand, Google Sheets)

## Bestanden
| Bestand | Rol |
|---------|-----|
| scan_receipt.py | Scan één bonnetje naar Google Sheets |
| watch_bonnetjes.py | Bewaakt map, scant nieuwe bonnetjes automatisch |
| btw_import.py | GUI: boekingen bijwerken + bonnetjes importeren (OCR + Claude fallback) |
| nieuw_kwartaal.py | Maakt nieuw kwartaalblad op basis van vorig kwartaal |
| nieuw_boekjaar.py | `zorg_voor_boekjaar()` — zorgt dat een jaartabblad in het bronbestand bestaat; maakt het automatisch aan (dupliceren vorig jaar, jaartallen bijwerken, data leegmaken) als het ontbreekt. Ook los te gebruiken: `nieuw_boekjaar.py 2028` |
| auth_gspread.py | Eenmalige OAuth-authenticatie (opnieuw uitvoeren als token verloopt) |

## Python omgeving
Gebruik altijd de virtualenv (Python 3.12 + Tk 9.0, vereist voor GUI):
```
~/projects/boekhouding-tgl/.venv/bin/python <script.py>
```
Of direct via shebang (btw_import.py is uitvoerbaar):
```
~/projects/boekhouding-tgl/btw_import.py
```
uv beheer: `~/.local/bin/uv` — pakketten installeren via `.venv/bin/python -m pip install <pakket>`

## Starten
```
cd ~/projects/boekhouding-tgl
~/projects/boekhouding-tgl/btw_import.py   # GUI: boekingen bijwerken + bonnetjes importeren
.venv/bin/python watch_bonnetjes.py         # continue bewaking bonnetjes-inbox
.venv/bin/python scan_receipt.py            # handmatig één bonnetje
.venv/bin/python nieuw_kwartaal.py          # begin nieuw kwartaal
```

## Bonnetjes inbox
Automatisch verwerkt als je ze neerzet in de map van het **huidige kwartaal** in de
Administratie-structuur, bv. voor Q3 2026:
`~/pCloud Drive/01 Kim en Niels/The Green Lodge/Financieel/2026/Q3` (map heette tot 29 sep 2026 "Administratie")
`watch_bonnetjes.py` berekent dit pad zelf (`standaard_inbox()`) op basis van de datum van
vandaag, dus dit werkt vanzelf door voor Q4 2026, Q1 2027, enz. — je hoeft dit niet elk
kwartaal opnieuw te laten aanpassen. Los pad meegeven kan nog steeds: `watch_bonnetjes.py <pad>`.

## Kwartaal afsluiten (checklist)
1. Boekingen bijwerken: open btw_import.py → "Werk boekingen bij"
2. Bonnetjes Q verwerken: zet PDFs/foto's in inbox of gebruik btw_import.py → "Importeer bonnetjes"
3. Spreadsheet controleren: datums, BTW-bedragen, categorieën
4. BTW-aangifte indienen op belastingdienst.nl (deadline: laatste dag van de maand na kwartaal)
5. Nieuw kwartaalblad aanmaken: `python3 nieuw_kwartaal.py`

## Google OAuth authenticatie
Token ligt in `~/.config/gspread/authorized_user.json`.
Verloopt dit (fout: `invalid_grant`), voer dan uit:
```
python3 ~/projects/boekhouding-tgl/auth_gspread.py
```
Volg de stappen: URL openen → inloggen → localhost-redirect mislukt (OK) → URL uit adresbalk kopiëren en plakken.

## Bekende problemen / valkuilen
- `gspread.oauth()` werkt niet interactief in Claude Code terminal — gebruik auth_gspread.py
- GUI werkt alleen met de .venv Python (3.12 + Tk 9.0). Python 3.9 system Tk crasht of toont zwart scherm
- Log-output wordt live weggeschreven naar btw_import_session.log (Claude kan dit uitlezen)
- Google Sheets formule-scheidingsteken is puntkomma (;) niet komma — Nederlandse locale

## Boekjaar-tabbladen (bronbestand)
Elk jaar heeft een eigen tabblad in het bronbestand (verhuur_bronbestand), met een vaste
structuur: rij 1-4 header/instellingen, rij 5-227 boekingsdata met per-rij formules
(nachten, schoonmaakkosten, toeristenbelasting, BTW-berekening). Sinds augustus 2026 hoeft
dit tabblad niet meer handmatig aangemaakt te worden: `lees_btw_boekingen()` in
`btw_import.py` roept `zorg_voor_boekjaar()` aan, die een ontbrekend jaartabblad automatisch
dupliceert uit het voorgaande jaar, de jaartal-verwijzingen in rij 3 bijwerkt en de
boekingsdata leegt (formules blijven staan). Dit gebeurt vanzelf de eerste keer dat een
boeking voor een nieuw jaar verwerkt wordt — je hoeft er niet meer aan te denken.

## Gastenmails The Green Lodge (Natuurhuisje-boekingen)
Losse automatisering, apart van bovenstaande scripts: drie e-mails naar de gast rond
zijn verblijf, alleen voor boekingen met Boekingsite = Natuurhuisje (andere platforms
geven geen bruikbaar gastadres).

- **Repo**: github.com/Nielskingma/TGLemails (los van dit lokale project, wel dezelfde
  boekhouding-tgl-map als basis gebruikt — dus dit hele project staat ook in die repo)
- **Draait**: GitHub Actions, elk uur; het script (`gastmails/verstuur_gastmails.py`)
  doet zelf niets buiten 14:00-15:00 Amsterdamse tijd (DST-veilig via zoneinfo)
- **Data**: leest het bronbestand rechtstreeks en publiek via de CSV-export-URL (zelfde
  aanpak als TGLtado, geen Google-login nodig). Gid per jaartabblad staat hardcoded in
  `GID_PER_JAAR` in het script — **voeg de gid van een nieuw jaar toe zodra
  `nieuw_boekjaar.py` dat tabblad heeft aangemaakt**, anders wordt dat jaar overgeslagen
- **Nieuwe kolom in bronbestand**: "E-mailadres gast" (2025: kolom Z, 2026/2027: kolom
  AA) — Natuurhuisje geeft geen API/gastadres via de iCal-sync, dus dit vul je zelf
  handmatig in vanuit de Natuurhuisje-portal per boeking. Zonder adres wordt die mail
  overgeslagen (met logregel), niets anders breekt
- **Verzendmoment per mail**:
  1. Welkomstinformatie — 5 dagen vóór check-in
  2. "Hoe bevalt het" — 1 dag na check-in
  3. Vertrekinstructies — de dag vóór uitchecken
- **Verzenden**: SMTP via Strato (`smtp.strato.de:465`) als kim@thegreenlodge.nl.
  Secrets in de GitHub-repo: `STRATO_EMAIL`, `STRATO_WACHTWOORD` (mailbox-wachtwoord,
  zelfde als Strato-webmail-login)
- **Voorkomt dubbel versturen**: `gastmails/verzonden_log.json`, bijgehouden per
  boeking+mailtype, wordt door de GitHub Action zelf teruggecommit na een succesvolle run
- **Logo**: `gastmails/logo.png`, wordt inline (CID) meegestuurd, niet extern gehost
- **Templates**: `gastmails/templates/mail1_welkom.html`, `mail2_hoebevalt.html`,
  `mail3_vertrek.html` — platte HTML met inline styles (e-mailclient-vriendelijk),
  `{{voornaam}}` als enige wisselend veld
- Werkend getest 12 sep 2026: handmatige workflow_dispatch-run gaf correct
  "Geen verzenduur (…) stop." buiten het 14u-venster

## Aanverwante automatisering (Google Apps Script, buiten dit Python-project)
Naast dit Python-project draaien drie Apps Script-automatiseringen die ook op het
bronbestand werken:

| Script | Waar | Doel |
|--------|------|------|
| `syncICalNaarBronbestand` | Apps Script gebonden aan bronbestand (Uitbreidingen → Apps Script) | Haalt Airbnb/Booking/Natuurhuisje/Voyando iCal-feeds op, zet nieuwe boekingen automatisch in het juiste jaartabblad, detecteert conflicten/annuleringen (tabblad "⚠️ Conflicten") |
| `CalendarSync` | Zelfde Apps Script-project, apart bestand | Zet boekingen uit het bronbestand in Google Agenda "🌿 The Green Lodge" |
| `updateSylviaPlanning` | Los Apps Script-project "Rapportages en connecties" (`script.google.com/d/1PQZ5fPrm-3G-4Xw2woJuVcHbmeNSAXMEee5k_M9_9xfv2ni2f7b39T7T`) | Genereert schoonmaakplanning voor Sylvia in Google Sheet "The Green Lodge schoonmaak" (`1H5hrge9xzZyEVP6rlewXDXS5g--wk4k7oFX2TYMloLw`): tabblad "🗓️ Komende 8 weken" (rollend venster) en "📅 Heel [jaar]" (huidig jaar; vanaf 1 oktober ook alvast volgend jaar) |

Er is nog geen lokale mirror (clasp) van deze Apps Script-projecten — code moet handmatig
gekopieerd worden vanuit script.google.com als die bekeken/aangepast moet worden. Losse
kopieën die zo zijn opgehaald staan in `apps-script/` in dit project.

### updateSylviaPlanning — timeout-bug is opgelost (v6, incrementele sync)
Trigger `updateSylviaPlanning` liep in aug 2026 vast op "Exceeded maximum execution time"
door O(n)-sheet-reads per nieuwe rij en cel-voor-cel opmaak-calls. Het huidige script
(opgehaald 11 sep 2026, lokale kopie `apps-script/schoonmaaksync_naar_sylvia.gs`) is
inmiddels doorontwikkeld tot **v6 — incrementele sync**: `schrijfTabS` leest de bestaande
kolom één keer in, bepaalt per boeking update/verwijderen/toevoegen op basis van een
sleutel (check-in-datum + gastnaam), en batcht de opmaak per rij. De oudere losse
`sylvia_planning_fix.gs` is hiermee achterhaald.

### 11 sep 2026 — hottub exact overnemen, doorstrepen bij Sylvia betaald, €-bug gefixt
Drie aanpassingen doorgevoerd in `schoonmaaksync_naar_sylvia.gs`, geüpload naar
script.google.com en door gebruiker getest — **werkt**:
- `hottubStrS()`: kolom Hottub? uit het bronbestand komt nu exact (letterlijk) in de
  schoonmaakplanning, i.p.v. altijd afgekapt tot Ja/Nee. Uitzondering: tekst met
  "nog betalen" erin wordt ingekort tot alleen "Ja".
- `sylviaBetaald`-vlag (bronbestand-kolom "Sylvia betaald?", index 20) → als die op
  "Ja" staat, wordt het bedrag in de Schoonmaak-kolom doorgestreept. Gebeurt als aparte
  gebatchte pas over de hele kolom ná elke sync (niet cel-voor-cel), dus ook ongewijzigde
  rijen krijgen de juiste doorstreping zonder het timeout-risico van weleer terug te halen.
- `schoonmaakStrS()`: normaliseert het schoonmaakbedrag altijd naar `€<bedrag>` — loste een
  bug op waarbij de "Komende 8 weken"-tab bedragen soms met en soms zonder €-teken toonde,
  veroorzaakt door inconsistente celinhoud in het bronbestand (getal vs. handmatige tekst
  als "€ 30" of kale "0").

Bekende eigenaardigheden:
- Airbnb's iCal-feed geeft vaak geen gastnaam/aantal personen mee (privacy) — blijft dan
  bewust leeg in het bronbestand tot je het zelf aanvult. Diagnose-logregel: "Kon geen
  gastnaam uit Airbnb-event halen" met de ruwe SUMMARY/DESCRIPTION.
- BTW-tarief in `syncICalNaarBronbestand` staat vast op 21% (bevestigd correct, aug 2026) —
  oudere handmatige 2026-boekingen hebben nog een gemengd 9%/21%-tarief uit een eerdere
  periode, dat is geen fout.
- Google Sheets-formules in het bronbestand gebruiken puntkomma (;) als argumentscheiding
  (Nederlandse locale), niet komma — komma's in bv. `DATE(...)`/`MINIFS(...)` geven `#ERROR!`.

### 11 sep 2026 — koprijen bronbestand: vastzetten kolom A-F + bezettingsgraad-aandeel
Rechtstreeks via de Sheets API aangepast (gspread, herauthenticatie nodig — token was
verlopen, `auth_gspread.py` opnieuw gedraaid), op alle jaartabbladen (2025/2026/2027):
- **Kolom A t/m F vastgezet** (`frozenColumnCount=6`). De koprij-samenvoegingen (rij 1
  titelbanner A:Y, rij 2 kleurenlegenda A:H) kruisten de F/G-grens en gaven eerst de fout
  "kolommen die slechts een deel van een samengevoegde cel bevatten" — opgeknipt in een
  links- (A:F) en rechterdeel (G:einde), tekst blijft ongewijzigd staan in de oorspronkelijke
  (linker) cel. Generieke, niet-destructieve versie van deze fix staat ook als Apps Script
  klaar in `apps-script/bronbestand_fix_header_freeze.gs` (nog te plakken/draaien is niet
  meer nodig, is al rechtstreeks toegepast) — leest per tabblad de daadwerkelijke
  samenvoegingen uit i.p.v. een vaste structuur aan te nemen, want tabbladen zijn qua
  koprij-opmaak uit elkaar gaan lopen (zie hieronder).
- **Bezettingsgraad-blok** (rij 3, tabblad-specifiek al aanwezig sinds 2026, nu ook op 2025):
  het bestaande per-platform-percentage (Airbnb/Natuurhuisje/Booking+Voyando/Direct) toonde
  **aandeel van het hele kalenderjaar** (nachten/365) — dat is nu vervangen door **aandeel
  binnen de bezetting** (nachten via dat platform / totaal bezette nachten dat jaar; telt op
  tot 100%). Voor 2025 (deels jaar, eerste boeking pas 25 jul) is de bezettingsgraad zelf ook
  aangepast: nachten / dagen-sinds-eerste-boekening-t/m-31-dec, niet nachten/365 → 75% i.p.v.
  een kunstmatig laag getal. 2026 blijft nachten/365 (volledig jaar). Rij 1-titel van 2026
  stond per ongeluk op "Kinderen" (losse tikfout, onbekend sinds wanneer) — hersteld naar
  "🌿 THE GREEN LODGE — BOEKINGEN 2026" naar analogie van 2025.
- **Ontdekt tijdens dit werk**: tabblad 2026 had de rij-3-samenvoeging F:I al eerder handmatig
  opgeknipt (nodig om het bezettingsgraad-blok kwijt te kunnen) — tabblad 2025 nog niet
  (opgeknipt tijdens deze sessie). Jaartabbladen zijn dus niet meer 1-op-1 identiek in
  koprij-structuur; hou daar rekening mee bij toekomstige structurele wijzigingen (niet
  blind aannemen dat wat in het ene jaar werkt, ook in het andere jaar hetzelfde uitpakt).

## Opgeloste bugs (juli 2026)
- Regex parse_btw_override was te breed → aangescherpt naar \bbtw\s+q(\d)
- Datum-sortering was op tekst i.p.v. datetime
- TOTAAL INKOMEND formule te smal na rij-invoeging → wordt nu altijd opnieuw ingesteld
- Bedragen werden als tekst geschreven → nu via als_float() als getal
- Dedup miste zelfde transactie via andere leverancier → waarschuwing toegevoegd
- BTW_TARIEVEN mapping: auto-invul bij bekende leveranciers (Odido 21%, Vitens 9%, etc.)
- BTW TE BETALEN miste ROUNDDOWN → nu =ROUNDDOWN(...;0) bij aanmaak sheet

## Open punt (sinds 14 sep 2026)
2028-tabblad nog niet getest: `nieuw_boekjaar.py` is gefixt zodat de bezettingsgraad-
formules (rij 3) bij een nieuw jaar altijd de canonieke, correcte versie krijgen i.p.v.
het jaartal te vervangen in wat het bronjaar toevallig had staan (2027 had hierdoor een
bug — zie hieronder). Zodra het 2028-tabblad automatisch wordt aangemaakt (eerste
boeking voor 2028, via `zorg_voor_boekjaar()` in `btw_import.py`), even H3:R3 controleren
op dat tabblad — moet er hetzelfde uitzien als 2027 nu (Airbnb/Natuurhuisje/Booking/Direct
tellen op tot 100%).

## Opgeloste bugs (18 sep 2026, vervolg — bonnetjes-scan flakiness)
- `scan_receipt.py` gebruikte een **hardcoded DATA_START_ROW=26** voor alle kwartaaltabbladen.
  Q3 2026 heeft door minder UITGAAND-boekingen een andere layout (INKOMEND-data begint al op
  rij 24 i.p.v. 26) — nu leest de code de echte positie van de "INKOMEND (KOSTEN"-header uit
  het tabblad zelf i.p.v. een vaste rij aan te nemen (`data_start_row` in `schrijf_naar_sheet`).
- De `claude -p ...`-subprocessaanroep in `scan_bonnetje()` gebruikte `--allowedTools Read`,
  maar sommige PDF's (waarschijnlijk lastiger te parsen bestanden) hebben meer nodig — Claude
  vraagt dan in platte tekst om toestemming, wat de JSON-parser laat crashen met "Overgeslagen:
  Expecting value…". Nu `--allowedTools "Read,Bash"`. Dit loste het merendeel op, maar bleek
  ook daarna nog **inherent flaky** (dezelfde aanroep op hetzelfde bestand slaagt de ene keer
  wel, de andere keer niet) — bij hardnekkige mislukkingen is meerdere keren opnieuw proberen
  de enige remedie, of het bestand zelf uitlezen i.p.v. via het script.
- Bij het verwerken van de 15 bonnetjes uit de Q3-map bleek er één (**"Invoice 2282B2B" van
  The Good Roll, 26-3-2026, €102,98/€21,63/€124,61**) al bestaand in Q1 2026 te staan (rij 78)
  — een duplicaat, dus bewust NIET nogmaals in Q3 geboekt. Bestand staat nog wel fysiek in de
  Q3-map; kan daar blijven liggen of verwijderd worden, telt niet mee.
- Eén bonnetje (DHL-verzendlabel, factuur 21979592) bleek gedateerd 02-05-2026 (Q2, al
  ingediend) — net als de eerdere Veneberg-bon meegeteld in Q3 i.p.v. een suppletie op Q2.

## Opgeloste bugs (18 sep 2026)
- `watch_bonnetjes.py` riep bij het verwerken van een gevonden bestand `~/scan_receipt.py`
  aan (Path.home()) i.p.v. het script in de projectmap — dat bestand bestaat niet op die
  plek, dus elk gedetecteerd bonnetje gaf stilzwijgend "Fout bij verwerken van ...". Nu
  `Path(__file__).parent / "scan_receipt.py"`, werkt ongeacht vanuit welke map je het start.
- De hardcoded standaard-inbox (`~/pCloud Drive/The Green Lodge/Administratie/Bonnetjes
  inbox`) bestond niet meer sinds de pCloud-herstructurering (bestandsorganisatie-project,
  23 aug 2026) — "The Green Lodge" zit sindsdien onder "01 Kim en Niels/". In de praktijk
  gebruikt de bewoner sowieso geen aparte "Bonnetjes inbox"-map maar zet bonnetjes direct in
  de kwartaalmap (`Administratie/{jaar}/Q{n}/`, Q1 heeft ook een "Verwerkt"-submap voor al
  ingevoerde bonnetjes). `watch_bonnetjes.py` berekent de standaardmap nu dynamisch als de
  kwartaalmap van vandaag (`standaard_inbox()`) — zie hierboven bij "Bonnetjes inbox".
- **Let op, nog niet gedaan**: er lagen bij het maken van deze fix al 14 bonnetjes
  ongesorteerd in `Administratie/2026/Q3/` (van vóór het starten van de watcher) — de
  watcher reageert alleen op NIEUWE bestanden vanaf het moment dat je 'm start, dus die 14
  moeten nog los verwerkt worden via `btw_import.py` → "Importeer bonnetjes" (bestandskiezer)
  of `scan_receipt.py <bestand>` per stuk.

## Opgeloste bugs (17 sep 2026)
- Tabblad "Q1 2026" van de BTW-spreadsheet (1sXOnJpfsvgcAdGU4Bp6uzVUCFL7vXdn1JqNWFhntTjw)
  gecontroleerd tegen de destijds opgeslagen aangifte-PDF (pCloud, `01 Kim en Niels/The
  Green Lodge/Administratie/2026/Q1/The Green Lodge BTW - Q1 2026.pdf`) — PDF is bepalend
  omdat die daadwerkelijk is ingediend. Drie problemen gevonden en hersteld:
  - INKOMEND-sectie (rijen 26-81): zo goed als alle bedragcellen in kolom D/E/F stonden als
    tekst ("€ 102,98" als string) i.p.v. als getal, waardoor de TOTAAL-SOM-formule ze niet
    meetelde. Alle 56 rijen omgezet naar echte getallen met currency-opmaak; waarden zelf
    kwamen (op één rij na) al overeen met de PDF.
  - UITGAAND-rij Diek (Natuurhuisje) was ná het indienen aangepast (273,22/57,38/330,60
    i.p.v. het ingediende 285,62/59,98/345,60) — teruggezet naar de PDF-waarden.
  - Extra bonnetje "sleutel service, Veneberg" (02-02-2026, €8,26/€1,74/€10,00) stond wél in
    de sheet maar niet in de ingediende PDF — kennelijk pas later toegevoegd. Uit Q1
    gehaald en in plaats daarvan toegevoegd aan tabblad "Q3 2026" (rij 24) zodat de BTW
    alsnog een keer wordt afgetrokken, in het eerstvolgende nog-niet-ingediende kwartaal.
  - Bijkomend gefixt: SUM-formules voor TOTAAL INKOMEND (kolom D/F) liepen één rij te kort.
  - Resultaat Q1 (nu identiek aan de PDF): BTW af te dragen €1.291,27, BTW te vorderen
    €1.340,16, BTW TE BETALEN -€48,89.

## Opgeloste bugs (14 sep 2026)
- Bezettingsgraad-formules 2027 (rij 3, bronbestand) waren fout: verkeerd rijbereik
  (`A8:A230` i.p.v. `A5:A235`, waardoor de eerste 3 boekingen van 2027 niet meetelden) en
  verkeerde noemer bij de platform-percentages (deelden door 365 i.p.v. door totaal bezette
  nachten, dus Airbnb/Natuurhuisje/Booking/Direct telden niet op tot 100%). Rechtstreeks in
  de sheet gecorrigeerd naar hetzelfde patroon als 2026. 2025 en 2026 gecontroleerd: correct.
- Grondoorzaak gefixt in `nieuw_boekjaar.py`: `zorg_voor_boekjaar()` verving voorheen alleen
  het jaartal in de gedupliceerde rij-3-formules van het bronjaar — een fout in het bronjaar
  (zoals hierboven bij 2027) erfde zo automatisch door naar elk volgend jaar. Nu wordt rij 3
  altijd met de canonieke, geverifieerd-correcte formule herschreven (functie
  `_bezettingsgraad_formules()`), ongeacht wat er in het bronjaar stond.

## Opgeloste bugs (augustus 2026)
- `nieuw_boekjaar.py`: dupliceerde alleen waarden, niet opmaak → doorgestreepte/grijze
  "verstreken"-opmaak van het bronjaar bleef op lege rijen van het nieuwe jaar staan.
  Nu wordt opmaak (doorstrepen, tekstkleur) ook gereset bij aanmaak.
- Drie Apps Script-bestanden (`syncICalNaarBronbestand`, `CalendarSync`,
  `updateSylviaPlanning`) lazen jaartabbladen hardcoded (["2025","2026"]) → braken vanzelf
  bij 2027. Nu dynamisch: vorig/huidig/volgend jaar.
- `syncICalNaarBronbestand` → `voegRijToe`: nieuwe boekingen belandden onderaan het
  tabblad (rij 80+) i.p.v. bovenaan, omdat lege rijen werden overgeslagen i.p.v. herkend
  als invoegpositie. Nu hergebruikt de code de eerste lege rij direct.
- `updateSylviaPlanning`: toont vanaf 1 oktober ook alvast het "Heel [volgend jaar]"-tabblad.
