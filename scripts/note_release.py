#!/usr/bin/env python3
"""Estrae dal CHANGELOG la sezione di una versione, per il corpo della release.

Senza questo, le note della release sono quelle generate da GitHub: con un
repo a un solo autore e senza pull request si riducono al link «Full
Changelog», che dice cosa confrontare ma non cosa è cambiato. Il CHANGELOG lo
sa già — va solo portato dove la gente lo legge.

Uso:
    python scripts/note_release.py 0.8.3 > NOTE.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/whiskas85/ha-access-module"

# Oltre questa lunghezza il corpo si taglia a un confine di sezione: una
# release lunga quanto un capitolo non la legge nessuno, e il file completo è
# a un clic.
LIMITE = 6000


def sezione(testo: str, versione: str) -> str | None:
    """Il blocco `## [versione] - data` fino alla versione successiva."""
    inizio = re.search(
        rf"^## \[{re.escape(versione)}\][^\n]*$", testo, re.MULTILINE
    )
    if not inizio:
        return None
    resto = testo[inizio.end() :]
    fine = re.search(r"^## \[", resto, re.MULTILINE)
    return (resto[: fine.start()] if fine else resto).strip()


def taglia(corpo: str) -> str:
    """Tronca a un confine di categoria, non a metà frase."""
    if len(corpo) <= LIMITE:
        return corpo
    tagliato = corpo[:LIMITE]
    ultimo = tagliato.rfind("\n### ")
    if ultimo > 0:
        tagliato = tagliato[:ultimo]
    return tagliato.rstrip() + "\n\n*(continua nel CHANGELOG)*"


def main() -> int:
    if len(sys.argv) < 2:
        print("Serve la versione, es. 0.8.3", file=sys.stderr)
        return 2
    versione = sys.argv[1].lstrip("v")

    testo = CHANGELOG.read_text(encoding="utf-8")
    corpo = sezione(testo, versione)

    if not corpo:
        # Non si fa fallire un rilascio per una sezione mancante: meglio una
        # release con poche note che nessuna release.
        print(f"Nessuna voce di CHANGELOG per la {versione}.")
        print(f"\n[CHANGELOG completo]({REPO}/blob/main/CHANGELOG.md)")
        return 0

    print(taglia(corpo))
    print(f"\n---\n\n[CHANGELOG completo]({REPO}/blob/main/CHANGELOG.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
