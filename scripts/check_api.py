#!/usr/bin/env python3
"""Verifica che gli attributi usati su store/coordinator/evaluator esistano.

Perché serve: rinominare `is_armed` in `is_open` non rompe né ruff né il
compilatore, perché `store` e `coordinator` sono oggetti non tipizzati e
`coordinator.is_armed` è un accesso ad attributo lecito fino a runtime. Il
risultato è un AttributeError dentro la vista HTTP, che diventa un 500, che
dal pannello si vede come «Impossibile leggere lo stato» — senza nessun
indizio su cosa sia stato rinominato.

Questo controllo legge le classi con `ast` (senza importare Home Assistant) e
confronta gli attributi usati con quelli definiti. Gira in CI insieme a ruff.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "access_control"

# variabile usata nel codice  ->  classe che ci sta dentro
SORGENTI = {
    "store": ("store.py", "AccessStore"),
    "coordinator": ("coordinator.py", "AccessCoordinator"),
    "evaluator": ("evaluator.py", "AccessEvaluator"),
}


def membri(percorso: Path, classe: str) -> set[str]:
    """Attributi e metodi definiti da una classe, inclusi quelli di __init__."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    trovati: set[str] = set()
    for nodo in ast.walk(albero):
        if not (isinstance(nodo, ast.ClassDef) and nodo.name == classe):
            continue
        for corpo in nodo.body:
            if isinstance(corpo, ast.FunctionDef | ast.AsyncFunctionDef):
                trovati.add(corpo.name)
        # `self.x = ...` dentro qualunque metodo
        for sotto in ast.walk(nodo):
            if (
                isinstance(sotto, ast.Attribute)
                and isinstance(sotto.value, ast.Name)
                and sotto.value.id == "self"
                and isinstance(sotto.ctx, ast.Store)
            ):
                trovati.add(sotto.attr)
    return trovati


def usi(percorso: Path) -> list[tuple[int, str, str]]:
    """Accessi `<nome>.<attr>` e `self.<nome>.<attr>` per i nomi che seguiamo."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    fuori: list[tuple[int, str, str]] = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.Attribute):
            continue
        base = nodo.value
        nome = None
        if isinstance(base, ast.Name) and base.id in SORGENTI:
            nome = base.id
        elif (
            isinstance(base, ast.Attribute)
            and base.attr in SORGENTI
            and isinstance(base.value, ast.Name)
            and base.value.id == "self"
        ):
            nome = base.attr
        if nome:
            fuori.append((nodo.lineno, nome, node_attr(nodo)))
    return fuori


def node_attr(nodo: ast.Attribute) -> str:
    return nodo.attr


def main() -> int:
    definiti = {
        nome: membri(BASE / file, classe)
        for nome, (file, classe) in SORGENTI.items()
    }

    problemi: list[str] = []
    for percorso in sorted(BASE.glob("*.py")):
        for riga, nome, attr in usi(percorso):
            if attr.startswith("__"):
                continue
            if attr not in definiti[nome]:
                problemi.append(
                    f"{percorso.name}:{riga}  {nome}.{attr}  "
                    f"— non esiste su {SORGENTI[nome][1]}"
                )

    if problemi:
        print("Attributi inesistenti:\n")
        for p in problemi:
            print(f"  {p}")
        print(
            f"\n{len(problemi)} problemi. Di solito è un rinomino "
            "che ha lasciato indietro un chiamante."
        )
        return 1

    for nome, (_, classe) in SORGENTI.items():
        print(f"  OK  {classe}: {len(definiti[nome])} membri, tutti gli usi validi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
