#!/usr/bin/env python3
"""Bewaakt een map en scant automatisch nieuwe bonnetjes naar Google Sheets."""
import sys
import time
import subprocess
import json
from pathlib import Path

ONDERSTEUNDE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
VERWERKT_LOG = Path.home() / ".config" / "bonnetjes_verwerkt.json"


def laad_verwerkt() -> set:
    if VERWERKT_LOG.exists():
        return set(json.loads(VERWERKT_LOG.read_text()))
    return set()


def sla_verwerkt_op(verwerkt: set) -> None:
    VERWERKT_LOG.write_text(json.dumps(list(verwerkt)))


def verwerk_bestand(pad: Path) -> None:
    print(f"Nieuw bestand gevonden: {pad.name} — scannen…")
    result = subprocess.run(
        [sys.executable, str(Path.home() / "scan_receipt.py"), str(pad)],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"Fout bij verwerken van {pad.name}")


def bewaar_map(map_pad: Path) -> None:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    verwerkt = laad_verwerkt()

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            self._verwerk(event.src_path)

        def on_moved(self, event):
            self._verwerk(event.dest_path)

        def _verwerk(self, pad_str: str):
            pad = Path(pad_str)
            if pad.suffix.lower() not in ONDERSTEUNDE_TYPES:
                return
            if str(pad) in verwerkt:
                return
            # Wacht even zodat het bestand volledig gekopieerd is
            time.sleep(2)
            if not pad.exists():
                return
            verwerk_bestand(pad)
            verwerkt.add(str(pad))
            sla_verwerkt_op(verwerkt)

    observer = Observer()
    observer.schedule(Handler(), str(map_pad), recursive=False)
    observer.start()
    print(f"Bewaking gestart op: {map_pad}")
    print("Druk op Ctrl+C om te stoppen.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main():
    if len(sys.argv) == 2:
        map_pad = Path(sys.argv[1])
    else:
        map_pad = Path.home() / "pCloud Drive" / "The Green Lodge" / "Administratie" / "Bonnetjes inbox"
        map_pad.mkdir(parents=True, exist_ok=True)
        print(f"Geen map opgegeven, standaard inbox: {map_pad}")

    if not map_pad.exists():
        print(f"Map bestaat niet: {map_pad}", file=sys.stderr)
        sys.exit(1)

    bewaar_map(map_pad)


if __name__ == "__main__":
    main()
