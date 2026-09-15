"""La master delle tessere NTAG 424, e il posto dove sta.

Sta in un file suo dentro `.storage`, separato dallo stato del modulo, e le
ragioni sono due:

- lo stato del modulo lo legge il pannello, che vive nel browser. La master
  non deve arrivarci mai, nemmeno per sbaglio in un campo aggiunto domani: in
  un file che il pannello non legge, non c'è modo che succeda;
- il file si scrive con i permessi del solo proprietario (`private`).

La master nasce alla prima programmazione di una tessera (SPEC.md §15): fino
ad allora non esiste, e nessuna tessera può risultare `forte` — che è
esattamente quello che deve succedere. Va nei backup di Home Assistant, per
scelta: perdere la master vorrebbe dire perdere tutte le tessere forti.
"""

from __future__ import annotations

import logging
import re
import secrets

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
        # Il file c'è ma non si legge. Allora non se ne crea uno nuovo sopra:
        # le tessere programmate con quella vecchia smetterebbero di aprire.
        self.illeggibile = False

    async def async_load(self) -> None:
        dati = await self._store.async_load() or {}
        grezza = dati.get("master")
        self.master = None
        self.illeggibile = False
        if grezza is None:
            return
        if isinstance(grezza, str) and _ESADECIMALE_32.fullmatch(grezza):
            self.master = bytes.fromhex(grezza)
            return
        self.illeggibile = True
        # Non si riparte con una master nuova: le tessere programmate con
        # quella vecchia smetterebbero di aprire senza un perché visibile.
        # Meglio dirlo forte e restare senza tessere `forte` finché qualcuno
        # non guarda il file.
        _LOGGER.error(
            "La master NTAG 424 in .storage/%s è illeggibile: nessuna tessera "
            "risulterà forte finché non viene sistemata",
            STORAGE_KEY,
        )

    async def async_master(self) -> bytes:
        """La master, creata la prima volta che serve.

        Casuale dal generatore del sistema operativo, sedici byte, salvata
        prima di essere usata: una tessera programmata con una master che poi
        non si è riusciti a salvare sarebbe una tessera persa.
        """
        if self.master is not None:
            return self.master
        if self.illeggibile:
            raise ValueError(
                "La master NTAG 424 esistente è illeggibile: non ne creo una "
                "nuova sopra. Controlla il file in .storage"
            )
        nuova = secrets.token_bytes(16)
        await self._store.async_save({"master": nuova.hex()})
        self.master = nuova
        _LOGGER.warning(
            "Creata la master NTAG 424 dell'impianto (in .storage/%s, compresa "
            "nei backup)",
            STORAGE_KEY,
        )
        return nuova
