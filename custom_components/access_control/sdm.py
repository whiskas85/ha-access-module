"""Dal link letto alla porta a un verdetto: che cosa dimostra questa lettura.

Il lettore riferisce il link che la tessera ha prodotto, senza interpretarlo.
Qui si estrae il messaggio, lo si prova contro le chiavi e si dice che cosa ne
è uscito. Niente Home Assistant, come `ntag424.py`: è la parte che decide se
una tessera vale `forte`, e deve potersi provare senza avviare niente.

**I cinque esiti, e perché sono cinque e non due.** «Valida o no» non basta a
chi guarda il registro, e nemmeno al motore di decisione:

- `assente` — la lettura porta solo l'UID. Una MIFARE Classic, un telefono,
  un'NTAG 424 senza SDM. È la lettura di sempre, cioè debole.
- `non_valido` — c'è un messaggio, ma nessuna chiave lo verifica. Una tessera
  configurata male, o qualcuno che ne imita una.
- `fabbrica` — la firma torna, ma con le chiavi di fabbrica, tutte a zero.
  Dimostra che la tessera funziona; non dimostra niente sulla sua
  autenticità, perché quelle chiavi le conosce chiunque. Resta debole.
- `replay` — firma giusta, chiavi dell'impianto, ma contatore già visto: è
  un messaggio catturato e riprodotto. Si nega.
- `valido` — firma giusta con le chiavi dell'impianto e contatore mai visto.
  È l'unico esito che vale `forte`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs

from .ntag424 import (
    BLOCCO,
    chiave_file,
    chiave_meta,
    decifra_picc,
    e_nuova,
    verifica,
)

ESITO_ASSENTE = "assente"
ESITO_NON_VALIDO = "non_valido"
ESITO_FABBRICA = "fabbrica"
ESITO_REPLAY = "replay"
ESITO_VALIDO = "valido"

_CHIAVI_DI_FABBRICA = bytes(BLOCCO)

# Il nodo non manda più di 200 byte di messaggio. Un link più lungo non viene
# da lui — o viene da un firmware che non è il nostro — e non si analizza.
_MASSIMO_LINK = 256

_PICC = re.compile(r"[0-9A-Fa-f]{32}")
_CMAC = re.compile(r"[0-9A-Fa-f]{16}")


@dataclass(frozen=True)
class Verifica:
    """Che cosa ha dimostrato una lettura."""

    esito: str
    contatore: int | None = None

    @property
    def forte(self) -> bool:
        return self.esito == ESITO_VALIDO


def estrai(link: str) -> tuple[bytes, bytes] | None:
    """I dati cifrati e la firma dentro il link, o None se non ci sono.

    Esigente di proposito: un solo `picc_data` di 32 cifre esadecimali e un
    solo `cmac` di 16. Due campi con lo stesso nome sono un link costruito a
    mano per vedere quale dei due viene letto: non si sceglie, si scarta.
    """
    if not isinstance(link, str) or not link or len(link) > _MASSIMO_LINK:
        return None
    _, trovato, query = link.partition("?")
    if not trovato:
        return None
    try:
        campi = parse_qs(query, strict_parsing=True, max_num_fields=8)
    except ValueError:
        return None

    picc = campi.get("picc_data") or []
    cmac = campi.get("cmac") or []
    if len(picc) != 1 or len(cmac) != 1:
        return None
    if not _PICC.fullmatch(picc[0]) or not _CMAC.fullmatch(cmac[0]):
        return None
    return bytes.fromhex(picc[0]), bytes.fromhex(cmac[0])


def _prova(
    chiave_cifratura: bytes,
    chiave_firma_di,
    picc: bytes,
    mac: bytes,
    uid: bytes,
) -> int | None:
    """Il contatore, se il messaggio si verifica con queste chiavi.

    La firma si prova solo sull'UID **letto in anticollisione**, non su quello
    decifrato: il messaggio deve venire dalla tessera che si è presentata, non
    da un'altra di cui qualcuno ha registrato una lettura.
    """
    try:
        lettura = decifra_picc(chiave_cifratura, picc)
    except ValueError:
        return None
    if lettura.uid != uid:
        return None
    if not verifica(chiave_firma_di(uid), lettura, mac):
        return None
    return lettura.contatore


def verifica_lettura(
    link: str,
    uid: bytes,
    master: bytes | None,
    ultimo_contatore: int | None,
) -> Verifica:
    """Il verdetto su una lettura.

    `master` può mancare: finché non esiste, nessuna tessera può risultare
    `valido`, e le NTAG 424 si possono comunque provare con le chiavi di
    fabbrica. `ultimo_contatore` è l'ultimo visto per questa tessera con le
    chiavi dell'impianto, None se non ce n'è mai stato uno.
    """
    parti = estrai(link)
    if parti is None:
        return Verifica(ESITO_ASSENTE)
    picc, mac = parti

    if master is not None:
        contatore = _prova(
            chiave_meta(master),
            lambda u: chiave_file(master, u),
            picc,
            mac,
            uid,
        )
        if contatore is not None:
            if not e_nuova(contatore, ultimo_contatore):
                return Verifica(ESITO_REPLAY, contatore)
            return Verifica(ESITO_VALIDO, contatore)

    contatore = _prova(
        _CHIAVI_DI_FABBRICA,
        lambda _u: _CHIAVI_DI_FABBRICA,
        picc,
        mac,
        uid,
    )
    if contatore is not None:
        # Nessun controllo del contatore: con chiavi che conosce chiunque un
        # messaggio «nuovo» si fabbrica a piacere, e dire «non ripetuto»
        # sarebbe dare un'informazione che non vale niente.
        return Verifica(ESITO_FABBRICA, contatore)

    return Verifica(ESITO_NON_VALIDO)
