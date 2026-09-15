#!/usr/bin/env python3
"""Prepara il nodo `rfid-ingresso` per essere compilato in CI.

Due cose, e solo in CI — lo script modifica i file e non va lanciato in una
copia di lavoro da cui poi si fa commit:

- **il componente `ntag424` si prende dalla cartella, non da GitHub.** Il nodo
  vero lo scarica da `main`; in CI si vuole compilare quello di *questo*
  commit, che su `main` magari non c'è ancora. Una CI che compila il
  componente vecchio è una CI verde che non ha provato niente;
- **un `secrets.yaml` finto**, perché il nodo ne pretende uno e quello vero
  non sta nel repository.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

NODO = Path(__file__).resolve().parent.parent / "esphome" / "rfid-ingresso.yaml"
SEGRETI = NODO.parent / "secrets.yaml"

DA_GITHUB = """\
  - source:
      type: git
      url: https://github.com/whiskas85/ha-access-module
      ref: main
      path: esphome/custom_components
"""
DALLA_CARTELLA = """\
  - source:
      type: local
      path: custom_components
"""


def main() -> int:
    testo = NODO.read_text(encoding="utf-8")
    if testo.count(DA_GITHUB) != 1:
        # Meglio fallire che compilare in silenzio il componente sbagliato.
        print(
            "Il blocco external_components del nodo è cambiato: "
            "aggiorna scripts/prepara_firmware_ci.py"
        )
        return 1
    NODO.write_text(testo.replace(DA_GITHUB, DALLA_CARTELLA), encoding="utf-8")

    chiave_api = base64.b64encode(bytes(32)).decode()
    SEGRETI.write_text(
        f'api_key: "{chiave_api}"\n'
        'ota_password: "solo-per-la-ci"\n'
        'ap_password: "solo-per-la-ci"\n'
        'web_username: "ci"\n'
        'web_password: "solo-per-la-ci"\n'
        'wifi_ssid: "ci"\n'
        'wifi_password: "solo-per-la-ci"\n',
        encoding="utf-8",
    )
    print("Nodo pronto: componente dalla cartella, segreti finti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
