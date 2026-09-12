// ================================================================
// The Green Lodge – Sylvia Schoonmaakplanning v6 (incremental sync)
// ================================================================
// Los Apps Script-project "Rapportages en connecties"
// (script.google.com/d/1PQZ5fPrm-3G-4Xw2woJuVcHbmeNSAXMEee5k_M9_9xfv2ni2f7b39T7T)
// Schrijft naar Google Sheet "The Green Lodge schoonmaak"
// (1H5hrge9xzZyEVP6rlewXDXS5g--wk4k7oFX2TYMloLw)
// Handmatig opgehaalde kopie — 11 sep 2026. Geen clasp-mirror.

const SYLVIA_SHEET_ID = "1H5hrge9xzZyEVP6rlewXDXS5g--wk4k7oFX2TYMloLw";

const FOREST_DARK  = "#2D4A1E";
const FOREST_MED   = "#4A7C2F";
const FOREST_PALE  = "#EEF5E6";
const CREAM        = "#FDFAF4";
const CREAM_ALT    = "#F4F0E8";
const ROOD         = "#C00000";
const WHITE        = "#FFFFFF";

const MAANDEN_S = ["januari","februari","maart","april","mei","juni",
                   "juli","augustus","september","oktober","november","december"];
const DAGEN_S   = ["zondag","maandag","dinsdag","woensdag","donderdag","vrijdag","zaterdag"];
const BRONBESTAND_ID_S = "1IxShqefOAGqCuS68HSQSRANofcYnIIS87ylOM10qjrg";

function relevantJarenS() {
  const jaar = new Date().getFullYear();
  return [String(jaar - 1), String(jaar), String(jaar + 1)];
}

function dagNaamS(datum) {
  if (!datum || !(datum instanceof Date) || isNaN(datum.getTime())) return "";
  return DAGEN_S[datum.getDay()].charAt(0).toUpperCase() + DAGEN_S[datum.getDay()].slice(1);
}

function datumNLS(datum) {
  if (!datum || !(datum instanceof Date) || isNaN(datum.getTime())) return "—";
  return `${dagNaamS(datum)} ${datum.getDate()} ${MAANDEN_S[datum.getMonth()]} ${datum.getFullYear()}`;
}

function combineerDatumTijdS(datum, tijdWaarde, standaardUur) {
  if (!datum || !(datum instanceof Date)) return null;
  try {
    const d = new Date(datum);
    if (isNaN(d.getTime())) return null;
    if (tijdWaarde instanceof Date) {
      const tz = Session.getScriptTimeZone();
      const tijdStr = Utilities.formatDate(tijdWaarde, tz, "HH:mm");
      const parts = tijdStr.split(":");
      d.setHours(parseInt(parts[0]) || standaardUur, parseInt(parts[1]) || 0, 0, 0);
    } else if (tijdWaarde && String(tijdWaarde).includes(":")) {
      const parts = String(tijdWaarde).split(":");
      d.setHours(parseInt(parts[0]) || standaardUur, parseInt(parts[1]) || 0, 0, 0);
    } else {
      d.setHours(standaardUur, 0, 0, 0);
    }
    return d;
  } catch(e) { return null; }
}

function kamersStrS(egel, vogel, eekhoorn) {
  const parts = [];
  if (egel && String(egel) !== "Niet" && String(egel) !== "0") parts.push(`🦔 Egel (${egel})`);
  if (vogel && String(vogel) !== "Niet" && String(vogel) !== "0") parts.push(`🐦 Vogel (${vogel})`);
  if (eekhoorn && String(eekhoorn) !== "Niet" && String(eekhoorn) !== "0") parts.push(`🐿️ Eekhoorn (${eekhoorn})`);
  return parts.join("\n") || "—";
}

function personenStrS(volw, kind, baby, honden) {
  const parts = [];
  if (Number(volw || 0) > 0) parts.push(`👤 ${volw} volw.`);
  if (Number(kind || 0) > 0) parts.push(`👧 ${kind} kind`);
  if (Number(baby || 0) > 0) parts.push(`👶 ${baby} baby`);
  if (honden !== undefined && String(honden) !== "0" && String(honden) !== "" && String(honden).toLowerCase() !== "nee")
    parts.push(`🐕 ${honden} hond`);
  return parts.join("\n") || "—";
}

/**
 * Hottub-kolom exact overnemen uit het bronbestand, met één uitzondering:
 * "... nog betalen" wordt ingekort tot alleen "Ja".
 */
function hottubStrS(raw) {
  const tekst = String(raw || "").trim();
  if (tekst.toLowerCase().indexOf("nog betalen") !== -1) return "Ja";
  return tekst;
}

/**
 * Normaliseert het schoonmaakbedrag naar een vast "€<bedrag>"-formaat,
 * ongeacht of het bronbestand een getal, "€ 30" of kale tekst "0" bevat.
 */
function schoonmaakStrS(raw) {
  if (raw === "" || raw === null || raw === undefined) return "";
  let bedrag;
  if (typeof raw === "number") {
    bedrag = raw;
  } else {
    const opgeschoond = String(raw).replace(/[€\s]/g, "").replace(",", ".");
    bedrag = parseFloat(opgeschoond);
    if (isNaN(bedrag)) return String(raw); // onherkenbare tekst: onveranderd laten staan
  }
  const heeftCenten = Math.round(bedrag * 100) % 100 !== 0;
  const bedragStr = heeftCenten ? bedrag.toFixed(2).replace(".", ",") : String(Math.round(bedrag));
  return `€${bedragStr}`;
}

// Unieke naam om conflict met CalendarSync.leesBoekingen te vermijden
function leesBoekingenSylvia(tabNaam) {
  const bron = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.openById(BRONBESTAND_ID_S);
  const sheet = bron.getSheetByName(tabNaam);
  if (!sheet) return [];

  const data = sheet.getDataRange().getValues();
  const boekingen = [];
  const tz = Session.getScriptTimeZone();

  for (let i = 4; i < data.length; i++) {
    const rij = data[i];
    const ciDatum = rij[1] instanceof Date && !isNaN(rij[1]) ? rij[1] : null;
    const coDatum = rij[3] instanceof Date && !isNaN(rij[3]) ? rij[3] : null;
    if (!ciDatum || !coDatum) continue;
    const status = String(rij[7] || "").toLowerCase();
    if (status === "reservering") continue;
    if (status === "geannuleerd") continue;

    const ciTijd = rij[2] instanceof Date
      ? Utilities.formatDate(rij[2], tz, "HH:mm")
      : String(rij[2] || "15:00");
    const coTijd = rij[4] instanceof Date
      ? Utilities.formatDate(rij[4], tz, "HH:mm")
      : String(rij[4] || "11:00");

    const ci = combineerDatumTijdS(ciDatum, ciTijd, 15);
    const co = combineerDatumTijdS(coDatum, coTijd, 11);
    if (!ci || !co) continue;

    boekingen.push({
      check_in: ci,
      check_out: co,
      ci_tijd: ciTijd,
      co_tijd: coTijd,
      naam: String(rij[5] || ""),
      volw: rij[8] || 0,
      kind: rij[9] || 0,
      baby: rij[10] || 0,
      honden: rij[11],
      egel: rij[12] || "Niet",
      vogel: rij[13] || "Niet",
      eekhoorn: rij[14] || "Niet",
      hottub: hottubStrS(rij[15]),
      nachten: rij[16] || 0,
      schoonmaak: schoonmaakStrS(rij[19]),
      sylviaBetaald: String(rij[20] || "").trim().toLowerCase() === "ja",
      opmerkingen: String(rij[24] || ""),
    });
  }
  return boekingen;
}

/**
 * Genereer een unieke sleutel per boeking op basis van check-in datum + gastnaam.
 */
function boekingSleutel(b) {
  const ciIso = b.check_in instanceof Date
    ? Utilities.formatDate(b.check_in, Session.getScriptTimeZone(), "yyyy-MM-dd")
    : String(b.check_in);
  return ciIso + "|" + String(b.naam).trim().toLowerCase();
}

/**
 * Dezelfde sleutel als boekingSleutel(), maar afgeleid uit wat er al in de
 * Check-in- en Gast-kolom van de sheet staat (formaat: "Dagnaam DD maand YYYY\n...").
 */
function sleutelUitCiTekst(ciTekst, gastNaam) {
  const datumMatch = String(ciTekst || "").match(/(\d{1,2})\s+(\w+)\s+(\d{4})/);
  if (!datumMatch) return null;
  const maandIdx = MAANDEN_S.indexOf(datumMatch[2].toLowerCase());
  if (maandIdx < 0) return null;
  const isoDate = datumMatch[3] + "-" + String(maandIdx + 1).padStart(2, "0") + "-" + String(datumMatch[1]).padStart(2, "0");
  return isoDate + "|" + String(gastNaam || "").trim().toLowerCase();
}

/**
 * Maak de rijwaarden-array voor een boeking (9 kolommen).
 */
function boekingNaarRij(b) {
  const ci = b.check_in;
  const co = b.check_out;
  const ciStr = ci ? `${datumNLS(ci)}\n🕒 ${b.ci_tijd} uur` : "—";
  const coStr = co ? `${datumNLS(co)}\n🕙 ${b.co_tijd} uur` : "—";
  return [
    ciStr,
    coStr,
    b.naam,
    b.nachten,
    personenStrS(b.volw, b.kind, b.baby, b.honden),
    kamersStrS(b.egel, b.vogel, b.eekhoorn),
    b.hottub,
    b.schoonmaak,
    b.opmerkingen
  ];
}

/**
 * Initialiseer een nieuwe tab met headers en opmaak.
 */
function initTabHeaders(tab, titel, subtitel) {
  tab.setRowHeight(1, 40);
  const titelRange = tab.getRange("A1:I1");
  titelRange.merge();
  titelRange.setValue(`🌿 THE GREEN LODGE — ${titel}`);
  titelRange.setBackground(FOREST_DARK).setFontColor(WHITE).setFontSize(15)
    .setFontWeight("bold").setFontFamily("Arial")
    .setHorizontalAlignment("center").setVerticalAlignment("middle");

  tab.setRowHeight(2, 18);
  const subRange = tab.getRange("A2:I2");
  subRange.merge();
  subRange.setValue(subtitel);
  subRange.setBackground(FOREST_PALE).setFontColor(FOREST_DARK).setFontSize(9)
    .setFontStyle("italic").setFontFamily("Arial")
    .setHorizontalAlignment("center").setVerticalAlignment("middle");

  tab.setRowHeight(3, 30);
  const hdrs = ["Check-in","Check-out","Gast","Nachten","Personen","Kamers","Hottub","Schoonmaak","Opmerkingen"];
  const breedte = [160, 160, 100, 60, 120, 130, 120, 90, 280];
  for (let c = 0; c < hdrs.length; c++) {
    const cel = tab.getRange(3, c + 1);
    cel.setValue(hdrs[c]);
    cel.setBackground(FOREST_MED).setFontColor(WHITE).setFontWeight("bold")
      .setFontSize(10).setFontFamily("Arial")
      .setHorizontalAlignment("center").setVerticalAlignment("middle").setWrap(true)
      .setBorder(true,true,true,true,false,false,"#9BBF7A",SpreadsheetApp.BorderStyle.SOLID);
    tab.setColumnWidth(c + 1, breedte[c]);
  }
  tab.setFrozenRows(3);
}

/**
 * Pas opmaak toe op een datarij.
 */
function formateerRij(tab, rij) {
  tab.setRowHeight(rij, 70);
  const bg = (rij - 4) % 2 === 0 ? CREAM : CREAM_ALT;
  const range = tab.getRange(rij, 1, 1, 9);

  range.setBackground(bg).setFontSize(10).setFontFamily("Arial")
    .setVerticalAlignment("middle").setWrap(true)
    .setBorder(true, true, true, true, false, false, "#9BBF7A", SpreadsheetApp.BorderStyle.SOLID);

  range.setFontColors([[FOREST_DARK, ROOD, "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000"]]);
  range.setFontWeights([["bold", "bold", "normal", "normal", "normal", "normal", "normal", "normal", "normal"]]);

  tab.getRange(rij, 4).setHorizontalAlignment("center"); // Nachten
  tab.getRange(rij, 8).setHorizontalAlignment("center"); // Schoonmaak
}


/**
 * Incrementele sync: vergelijk bestaande rijen met nieuwe boekingen.
 * Alleen wijzigingen doorvoeren, niet alles weghalen en opnieuw vullen.
 */
function schrijfTabS(sylviaSheet, tabNaam, boekingen, titel, subtitel) {
  let tab = sylviaSheet.getSheetByName(tabNaam);
  const isNieuw = !tab;

  // Maak tab aan als die nog niet bestaat
  if (isNieuw) {
    tab = sylviaSheet.insertSheet(tabNaam);
    initTabHeaders(tab, titel, subtitel);
  }

  // Update subtitel (bijgewerkt-datum)
  if (!isNieuw) {
    const subRange = tab.getRange("A2:I2");
    subRange.setValue(subtitel);
  }

  // Onaangetaste opzoekmap (blijft heel, ook straks nog nodig voor stap 5 doorstrepen)
  const boekingPerSleutel = {};
  for (let i = 0; i < boekingen.length; i++) {
    boekingPerSleutel[boekingSleutel(boekingen[i])] = boekingen[i];
  }
  // Werkkopie die tijdens de vergelijking hieronder leegloopt
  const nieuweMap = Object.assign({}, boekingPerSleutel);

  // Lees bestaande data-rijen (vanaf rij 4)
  const laatsteRij = tab.getLastRow();
  const bestaandeSleutels = {};
  const bestaandeRijen = {}; // sleutel -> rijnummer

  if (!isNieuw && laatsteRij >= 4) {
    const bestaandeData = tab.getRange(4, 1, laatsteRij - 3, 9).getValues();
    for (let i = 0; i < bestaandeData.length; i++) {
      const rijNr = i + 4;
      const ciTekst = String(bestaandeData[i][0] || "");
      const gastNaam = String(bestaandeData[i][2] || "");
      const sleutel = sleutelUitCiTekst(ciTekst, gastNaam);
      if (sleutel) {
        bestaandeSleutels[sleutel] = bestaandeData[i];
        bestaandeRijen[sleutel] = rijNr;
      }
    }
  }

  // Bepaal wat er moet gebeuren
  const teVerwijderen = []; // rijnummers
  const teUpdaten = [];     // {rij, waarden}
  const toeTeVoegen = [];   // boekingen

  // Check bestaande rijen: updaten of verwijderen
  for (const sleutel in bestaandeRijen) {
    if (nieuweMap[sleutel]) {
      // Vergelijk of data gewijzigd is
      const nieuweWaarden = boekingNaarRij(nieuweMap[sleutel]);
      const bestaand = bestaandeSleutels[sleutel];
      let gewijzigd = false;
      for (let c = 0; c < 9; c++) {
        if (String(nieuweWaarden[c]) !== String(bestaand[c])) {
          gewijzigd = true;
          break;
        }
      }
      if (gewijzigd) {
        teUpdaten.push({ rij: bestaandeRijen[sleutel], waarden: nieuweWaarden, boeking: nieuweMap[sleutel] });
      }
      delete nieuweMap[sleutel]; // verwerkt
    } else {
      teVerwijderen.push(bestaandeRijen[sleutel]);
    }
  }

  // Resterende nieuwe boekingen moeten toegevoegd worden
  for (const sleutel in nieuweMap) {
    toeTeVoegen.push(nieuweMap[sleutel]);
  }
  // Sorteer nieuwe boekingen op check-in datum
  toeTeVoegen.sort((a, b) => a.check_in - b.check_in);

  // 1. Verwijder rijen (van onder naar boven om rijnummers intact te houden)
  teVerwijderen.sort((a, b) => b - a);
  for (const rijNr of teVerwijderen) {
    tab.deleteRow(rijNr);
  }

  // 2. Update gewijzigde rijen (pas rijnummer aan voor verwijderde rijen)
  for (const update of teUpdaten) {
    let rijNr = update.rij;
    // Corrigeer rijnummer voor verwijderde rijen erboven
    for (const verwijderd of teVerwijderen) {
      if (verwijderd < update.rij) rijNr--;
    }
    const range = tab.getRange(rijNr, 1, 1, 9);
    range.setValues([update.waarden]);
    formateerRij(tab, rijNr, rijNr);
  }

  // 3. Voeg nieuwe rijen toe
  if (toeTeVoegen.length > 0) {
    let bestaandeCiTeksten = [];
    const startLaatste = tab.getLastRow();
    if (startLaatste >= 4) {
      bestaandeCiTeksten = tab.getRange(4, 1, startLaatste - 3, 1).getValues().map(r => String(r[0] || ""));
    }

    for (const boeking of toeTeVoegen) {
      const waarden = boekingNaarRij(boeking);
      const nieuweSleutel = boekingSleutel(boeking);
      const nieuweCiIso = nieuweSleutel.split("|")[0];

      let invoegIndex = bestaandeCiTeksten.length; // standaard: onderaan
      for (let i = 0; i < bestaandeCiTeksten.length; i++) {
        const datumMatch = bestaandeCiTeksten[i].match(/(\d{1,2})\s+(\w+)\s+(\d{4})/);
        if (datumMatch) {
          const dag = datumMatch[1];
          const maandNaam = datumMatch[2].toLowerCase();
          const jaar = datumMatch[3];
          const maandIdx = MAANDEN_S.indexOf(maandNaam);
          if (maandIdx >= 0) {
            const isoDate = jaar + "-" + String(maandIdx + 1).padStart(2, "0") + "-" + String(dag).padStart(2, "0");
            if (isoDate > nieuweCiIso) { invoegIndex = i; break; }
          }
        }
      }

      const invoegRij = invoegIndex + 4;
      if (invoegRij <= tab.getLastRow()) {
        tab.insertRowBefore(invoegRij);
      }
      tab.getRange(invoegRij, 1, 1, 9).setValues([waarden]);
      formateerRij(tab, invoegRij);

      // Bijwerken in-memory lijst zodat volgende iteratie niet opnieuw hoeft te lezen
      bestaandeCiTeksten.splice(invoegIndex, 0, waarden[0]);
    }
  }

  // 4. Herkleur alle rijen (zebra-striping kan verschoven zijn)
  const eindRij = tab.getLastRow();
  if (eindRij >= 4) {
    const aantalRijen = eindRij - 3;
    const kleuren = [];
    for (let i = 0; i < aantalRijen; i++) {
      const bg = i % 2 === 0 ? CREAM : CREAM_ALT;
      kleuren.push(new Array(9).fill(bg));
    }
    tab.getRange(4, 1, aantalRijen, 9).setBackgrounds(kleuren);
  }

  // 5. Doorstrepen schoonmaakbedrag waar Sylvia al betaald is (hele kolom in 1 batch-call,
  //    dus ook rijen waar verder niets veranderd is krijgen de juiste doorstreping)
  if (eindRij >= 4) {
    const aantalRijen = eindRij - 3;
    const ciEnGast = tab.getRange(4, 1, aantalRijen, 3).getValues();
    const fontLines = ciEnGast.map(rij => {
      const sleutel = sleutelUitCiTekst(String(rij[0] || ""), String(rij[2] || ""));
      const boeking = sleutel ? boekingPerSleutel[sleutel] : null;
      return [boeking && boeking.sylviaBetaald ? "line-through" : "none"];
    });
    tab.getRange(4, 8, aantalRijen, 1).setFontLines(fontLines);
  }

  // 6. Als er geen boekingen meer zijn, toon melding
  if (eindRij < 4) {
    const leeg = tab.getRange("A4:I4");
    leeg.merge();
    leeg.setValue("Geen boekingen in deze periode.");
    leeg.setFontStyle("italic").setFontColor("#888888").setHorizontalAlignment("center");
  }
}

function updateSylviaPlanning() {
  const nu    = new Date();
  const grens = new Date(nu.getTime() + 8 * 7 * 24 * 60 * 60 * 1000);

  const alle = relevantJarenS()
    .flatMap(jaar => leesBoekingenSylvia(jaar))
    .filter(b => b.check_in)
    .sort((a, b) => a.check_in - b.check_in);

  const binnenkort = alle.filter(b => b.check_out >= nu && b.check_in <= grens);
  const huidigJaar = alle.filter(b => b.check_in.getFullYear() === nu.getFullYear());

  const sylviaSheet = SpreadsheetApp.openById(SYLVIA_SHEET_ID);
  const vandaag = `${nu.getDate()} ${MAANDEN_S[nu.getMonth()]} ${nu.getFullYear()} om ${String(nu.getHours()).padStart(2,"0")}:${String(nu.getMinutes()).padStart(2,"0")}`;

  schrijfTabS(sylviaSheet, "🗓️ Komende 8 weken", binnenkort,
    "SCHOONMAAKPLANNING — KOMENDE 8 WEKEN",
    `Bijgewerkt op ${vandaag} • ${binnenkort.length} boekingen`);

  schrijfTabS(sylviaSheet, `📅 Heel ${nu.getFullYear()}`, huidigJaar,
    `SCHOONMAAKPLANNING — VOLLEDIG JAAR ${nu.getFullYear()}`,
    `Bijgewerkt op ${vandaag} • ${huidigJaar.length} boekingen`);

  // Vanaf 1 oktober alvast het volgende jaar tonen (nu.getMonth() is 0-based: 9 = oktober)
  if (nu.getMonth() >= 9) {
    const volgendJaar = nu.getFullYear() + 1;
    const boekingenVolgendJaar = alle.filter(b => b.check_in.getFullYear() === volgendJaar);
    schrijfTabS(sylviaSheet, `📅 Heel ${volgendJaar}`, boekingenVolgendJaar,
      `SCHOONMAAKPLANNING — VOLLEDIG JAAR ${volgendJaar}`,
      `Bijgewerkt op ${vandaag} • ${boekingenVolgendJaar.length} boekingen`);
  }

  const legeTab = sylviaSheet.getSheetByName("Blad1");
  if (legeTab && sylviaSheet.getSheets().length > 1) sylviaSheet.deleteSheet(legeTab);

  SpreadsheetApp.flush();
  Logger.log(`✅ Sylvia planning bijgewerkt: ${binnenkort.length} binnenkort, ${huidigJaar.length} heel jaar`);
}
