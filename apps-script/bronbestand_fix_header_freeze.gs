// ================================================================
// The Green Lodge – eenmalige fix: koprijen splitsen bij kolom F/G
// zodat "Vastzetten t/m kolom F" niet meer botst met samengevoegde cellen.
// ================================================================
// Plakken in het Apps Script-project gebonden aan het bronbestand
// (Uitbreidingen → Apps Script vanuit verhuur_bronbestand zelf — zelfde project
// als syncICalNaarBronbestand/CalendarSync). Eenmalig draaien via
// fixHeaderVoorVastzettenTotF() in de functie-kiezer, daarna mag deze functie
// weer weg. Nieuwe jaartabbladen erven de aanpassing automatisch mee omdat
// zorg_voor_boekjaar()/nieuw_boekjaar.py het tabblad dupliceert.
//
// Generiek opgezet omdat tabbladen inmiddels verschillende samenvoegingen
// hebben: tabblad 2026 had de F:I-samenvoeging al eerder handmatig opgeknipt
// (voor het bezettingsgraad-blok in rij 3), tabblad 2025 nog niet. Deze fix
// leest daarom per tabblad de echte samenvoegingen uit en knipt alléén die
// welke de grens tussen kolom F en G doorkruisen — er wordt nooit een
// celwaarde verplaatst of gewist, alleen de samenvoeging zelf opgeknipt.

function fixHeaderVoorVastzettenTotF() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.getSheets()
    .filter(sheet => /^\d{4}$/.test(sheet.getName()))
    .forEach(splitsMergesOpFG);
}

function splitsMergesOpFG(sheet) {
  const bereiken = sheet.getRange(1, 1, 3, sheet.getLastColumn()).getMergedRanges();
  bereiken.forEach(bereik => {
    const rij = bereik.getRow();
    const startKolom = bereik.getColumn();
    const eindKolom = bereik.getLastColumn();
    if (startKolom > 6 || eindKolom < 7) return; // kruist de F/G-grens niet, met rust laten

    bereik.breakApart();
    const linkerBreedte = 6 - startKolom + 1;
    const rechterBreedte = eindKolom - 7 + 1;
    if (linkerBreedte > 1) sheet.getRange(rij, startKolom, 1, linkerBreedte).merge();
    if (rechterBreedte > 1) sheet.getRange(rij, 7, 1, rechterBreedte).merge();
  });
  sheet.setFrozenColumns(6);
}
