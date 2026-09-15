"""La master delle tessere NTAG 424, e il posto dove sta.

Sta in un file suo dentro `.storage`, separato dallo stato del modulo, e le
ragioni sono due:

- lo stato del modulo lo legge il pannello, che vive nel browser. La master
  non deve arrivarci mai, nemmeno per sbaglio in un campo aggiunto domani: in
  un file che il pannello non legge, non c'è modo che succeda;
- il file si scrive con i permessi del solo proprietario (`private`).

Qui la master si **legge** e basta. La crea la programmazione delle tessere
(SPEC.md §15), che arriva dopo: fino ad allora non esiste, e nessuna tessera
può risultare `forte` — che è esattamente quello che deve succedere.
"""

from __future__ import annotations

import logging
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.ntag424"
STORAGE_VERSION = 1

_ESADECIMALE_32 = re.compile(r"[0-9a-f]{32}")


class ChiaviNtag424:
    """Custodisce la master, se c'è."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True
        )
        self.master: bytes | None = None

    async def async_load(self) -> None:
        dati = await self._store.async_load() or {}
        grezza = dati.get("master")
        self.master = None
        if grezza is None:
            return
        if isinstance(grezza, str) and _ESADECIMALE_32.fullmatch(grezza):
            self.master = bytes.fromhex(grezza)
            return
        # Non si riparte con una master nuova: le tessere programmate con
        # quella vecchia smetterebbero di aprire senza un perché visibile.
        # Meglio dirlo forte e restare senza tessere `forte` finché qualcuno
        # non guarda il file.
        _LOGGER.error(
            "La master NTAG 424 in .storage/%s è illeggibile: nessuna tessera "
            "risulterà forte finché non viene sistemata",
            STORAGE_KEY,
        )
