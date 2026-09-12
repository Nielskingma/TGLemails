// ================================================================
// FIX voor "Exceeded maximum execution time" in updateSylviaPlanning
// Vervang in het Apps Script-project deze twee functies + het
// aangegeven blok in schrijfTabS door onderstaande versies.
// Gedrag is identiek, alleen minder Sheets-API-calls (batch i.p.v.
// cel-voor-cel / herhaald inlezen).
// ================================================================

/**
 * Pas opmaak toe op een datarij — nu gebatcht (1 range i.p.v. 9 losse cellen).
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

// ----------------------------------------------------------------
// In schrijfTabS: vervang stap 3 ("Voeg nieuwe rijen toe") door dit
// blok. Kernverschil: de bestaande check-in-kolom wordt ÉÉN keer
// gelezen (voor de loop) en daarna alleen nog in het geheugen
// bijgewerkt, in plaats van bij elke nieuwe boeking opnieuw
// getRange().getValues() aan te roepen.
// ----------------------------------------------------------------

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

// ----------------------------------------------------------------
// Stap 4 ("Herkleur alle rijen") vervangen door dit blok:
// één setBackgrounds()-call i.p.v. een losse setBackground() per rij.
// ----------------------------------------------------------------

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
