"""Programmazione di una NTAG 424 DNA: chiavi dell'impianto e messaggio SDM.

Niente Home Assistant: la sequenza riceve una funzione `invia`, che manda un
comando alla tessera e ne restituisce la risposta, e non sa altro. È ciò che
permette di provarla per intero contro una tessera simulata, e ciò che tiene
il lettore fuori dalla crittografia: lui passa byte, qui si decide cosa
significano (SPEC.md §15, scelta «B»).

**Cosa passa dal lettore, e cosa no.** Passano la sfida dell'autenticazione e
i comandi cifrati con le chiavi di sessione. Non passano mai né la master né
una chiave in chiaro: le chiavi nuove viaggiano dentro ChangeKey, cifrate con
una chiave di sessione che nasce dalla sfida e che il lettore non può
ricavare. Un lettore manomesso che registrasse tutto non ne caverebbe niente.

**L'ordine dei passi non è indifferente.**

1. Il link si scrive per primo, in chiaro, finché la scrittura è libera: le
   impostazioni del passo 3 la chiudono.
2. Autenticazione con la chiave 0 — di fabbrica, o già nostra.
3. Impostazioni SDM: messaggio cifrato con la chiave 1, firmato con la 2,
   scrittura del file riservata alla chiave 0.
4. Chiavi 1-4, poi **la 0 per ultima**: finché resta quella di fabbrica, una
   programmazione interrotta si riprende da capo.
5. Prova: si legge il link come lo leggerebbe la porta e lo si verifica con
   le chiavi dell'impianto, poi ci si riautentica con la chiave 0 nuova. Una
   tessera che non passa la prova non è programmata, qualunque cosa abbiano
   risposto i passi prima.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .ntag424 import (
    BLOCCO,
    NUMERO_APPLICAZIONE,
    NUMERO_FILE,
    NUMERO_META,
    SessioneEV2,
    apdu,
    autentica_passo_1,
    autentica_passo_2,
    chiave_applicazione,
    chiave_file,
    chiave_meta,
    chiave_riserva,
    dati_cambio_chiave,
)
from .sdm import ESITO_VALIDO, verifica_lettura

Invia = Callable[[bytes], Awaitable[bytes]]

_FABBRICA = bytes(BLOCCO)
_VERSIONE_CHIAVI = 0x01

SELEZIONA_APPLICAZIONE = bytes.fromhex("00A4040007D276000085010100")
SELEZIONA_FILE_NDEF = bytes.fromhex("00A4000C02E104")

_CMD_AUTENTICA = 0x71
_CMD_ALTRO = 0xAF
_CMD_IMPOSTAZIONI = 0x5F
_CMD_CAMBIA_CHIAVE = 0xC4
_FILE_NDEF = 0x02

_STATO_OK = 0x00
_STATO_ALTRO = 0xAF

# Il link della tessera. Il dominio non conta per l'impianto: conta per chi
# legge la tessera col telefono, che si vede proporre di aprirlo. Un dominio
# riservato non porta da nessuna parte e non raccoglie niente.
DOMINIO = "example.com/a"
_PREFISSO_HTTPS = 0x04

# Ogni chiave con la sua funzione. Le 3 e 4 non servono all'impianto, ma non
# restano quelle di fabbrica (vedi `chiave_riserva`).
_RISERVE = (3, 4)


class ErroreProgrammazione(Exception):
    """Un passo non è andato. Il messaggio dice quale, in parole."""


@dataclass(frozen=True)
class Esito:
    """Com'è andata: il contatore della lettura di prova, e se era già nostra."""

    contatore: int
    gia_nostra: bool


# ── il contenuto della tessera ─────────────────────────────────────────────


def messaggio_ndef() -> tuple[bytes, int, int]:
    """Il file NDEF da scrivere, e dove la tessera metterà dati cifrati e firma.

    Gli zeri sono segnaposto: a ogni lettura la tessera ci scrive sopra.
    Le posizioni contano dall'inizio del file, lunghezza NDEF compresa.
    """
    corpo = f"{DOMINIO}?picc_data={'0' * 32}&cmac={'0' * 16}".encode()
    dati = bytes([_PREFISSO_HTTPS]) + corpo
    record = bytes([0xD1, 0x01, len(dati), 0x55]) + dati
    file = len(record).to_bytes(2, "big") + record
    picc = file.index(b"picc_data=") + len(b"picc_data=")
    mac = file.index(b"cmac=") + len(b"cmac=")
    return file, picc, mac


def impostazioni_sdm(picc: int, mac: int) -> bytes:
    """I dati di ChangeFileSettings per il file NDEF (AN12196 §5.9)."""
    return (
        # SDM acceso; il file si legge e si scrive in chiaro, perché il link
        # lo deve poter leggere chiunque — è la firma a proteggerlo.
        bytes([0x40])
        # Lettura libera; scrittura, lettura-scrittura e modifica delle
        # impostazioni solo con la chiave 0. Senza, chiunque con un telefono
        # potrebbe riscrivere il link e spegnere il messaggio.
        + bytes([0x00, 0xE0])
        # UID e contatore nel messaggio, in esadecimale ASCII.
        + bytes([0xC1])
        # Contatore non leggibile a parte; messaggio cifrato con la chiave 1,
        # firmato con la 2.
        + bytes([0xFF, (NUMERO_META << 4) | NUMERO_FILE])
        + picc.to_bytes(3, "little")
        # La firma copre solo UID e contatore: inizio dei dati firmati e
        # posizione della firma coincidono.
        + mac.to_bytes(3, "little")
        + mac.to_bytes(3, "little")
    )


def link_da_ndef(file: bytes) -> str:
    """Il link dentro un file NDEF, senza prefisso; vuoto se non è dei nostri."""
    if len(file) < 2:
        return ""
    lunghezza = int.from_bytes(file[0:2], "big")
    record = file[2 : 2 + lunghezza]
    if len(record) != lunghezza or len(record) < 6:
        return ""
    if record[0] != 0xD1 or record[1] != 0x01 or record[3] != 0x55:
        return ""
    if 4 + record[2] != len(record):
        return ""
    try:
        return record[5:].decode("ascii")
    except UnicodeDecodeError:
        return ""


# ── dialogo con la tessera ─────────────────────────────────────────────────


async def _iso(invia: Invia, comando: bytes, passo: str) -> bytes:
    risposta = await invia(comando)
    if len(risposta) < 2 or risposta[-2:] != b"\x90\x00":
        raise ErroreProgrammazione(f"{passo}: la tessera ha risposto di no")
    return risposta[:-2]


def _nativo(risposta: bytes, passo: str) -> tuple[int, bytes]:
    """Stato e dati della risposta a un comando nativo (91 xx)."""
    if len(risposta) < 2 or risposta[-2] != 0x91:
        raise ErroreProgrammazione(f"{passo}: risposta incomprensibile")
    return risposta[-1], risposta[:-2]


async def _autentica(
    invia: Invia, chiave: bytes, casuale: Callable[[int], bytes]
) -> SessioneEV2 | None:
    """AuthenticateEV2First con la chiave 0. None se la chiave non è quella."""
    risposta = await invia(apdu(_CMD_AUTENTICA, bytes([NUMERO_APPLICAZIONE, 0x00])))
    stato, sfida = _nativo(risposta, "autenticazione")
    if stato != _STATO_ALTRO or len(sfida) != BLOCCO:
        raise ErroreProgrammazione(
            "autenticazione: la tessera non ha lanciato la sfida"
        )

    rnd_a = casuale(BLOCCO)
    replica, rnd_b = autentica_passo_1(chiave, sfida, rnd_a)
    risposta = await invia(apdu(_CMD_ALTRO, replica))
    stato, dati = _nativo(risposta, "autenticazione")
    if stato != _STATO_OK:
        # La tessera ha rifiutato la nostra risposta: la chiave non è questa.
        return None
    try:
        return autentica_passo_2(chiave, rnd_a, rnd_b, dati)
    except ValueError as err:
        # Ha accettato la nostra risposta ma non sa ruotare RndA: non è una
        # tessera che conosce la chiave, è qualcosa che finge di esserlo.
        raise ErroreProgrammazione(
            "autenticazione: la tessera non ha dimostrato di conoscere la chiave"
        ) from err


async def _comando_full(
    invia: Invia,
    sessione: SessioneEV2,
    comando: int,
    intestazione: bytes,
    dati: bytes,
    passo: str,
    *,
    firmata: bool = True,
) -> None:
    dati_comando = sessione.dati_full(comando, intestazione, dati)
    risposta = await invia(apdu(comando, dati_comando))
    stato, corpo = _nativo(risposta, passo)
    if stato != _STATO_OK:
        raise ErroreProgrammazione(
            f"{passo}: la tessera ha risposto errore {stato:02X}"
        )
    if not firmata:
        # Cambiata la chiave con cui ci si era autenticati, la sessione
        # finisce e la risposta arriva senza firma (AN12196 tab. 26).
        return
    try:
        sessione.chiudi(stato, corpo, cifrata=True)
    except ValueError as err:
        raise ErroreProgrammazione(
            f"{passo}: la risposta non porta la firma della sessione"
        ) from err


async def _scrivi_link(invia: Invia) -> None:
    """Scrive il link con i segnaposto, finché la scrittura è libera.

    Su una tessera già programmata la scrittura è chiusa: allora si controlla
    che il link sia già il nostro, confrontando tutto tranne i punti in cui la
    tessera mette messaggio e firma.
    """
    file, picc, mac = messaggio_ndef()
    await _iso(invia, SELEZIONA_FILE_NDEF, "selezione del file NDEF")
    risposta = await invia(bytes([0x00, 0xD6, 0x00, 0x00, len(file)]) + file)
    if risposta[-2:] == b"\x90\x00":
        return

    letto = await _iso(
        invia, bytes([0x00, 0xB0, 0x00, 0x00, len(file)]), "lettura del link"
    )
    maschera = set(range(picc, picc + 32)) | set(range(mac, mac + 16))
    uguale = len(letto) == len(file) and all(
        letto[i] == file[i] for i in range(len(file)) if i not in maschera
    )
    if not uguale:
        raise ErroreProgrammazione(
            "scrittura del link: la tessera non si lascia scrivere e il link che "
            "porta non è quello dell'impianto"
        )


async def _leggi_link(invia: Invia) -> str:
    """Il link come lo leggerebbe la porta: senza autenticazione."""
    await _iso(invia, SELEZIONA_FILE_NDEF, "selezione del file NDEF")
    testa = await _iso(invia, bytes.fromhex("00B0000002"), "lettura del link")
    lunghezza = int.from_bytes(testa, "big") if len(testa) == 2 else 0
    if not 6 <= lunghezza <= 200:
        return ""
    corpo = await _iso(
        invia, bytes([0x00, 0xB0, 0x00, 0x02, lunghezza]), "lettura del link"
    )
    return link_da_ndef(testa + corpo)


# ── la sequenza ────────────────────────────────────────────────────────────


async def programma(
    invia: Invia,
    uid: bytes,
    master: bytes,
    *,
    casuale: Callable[[int], bytes] = os.urandom,
) -> Esito:
    """Porta una NTAG 424 alle chiavi dell'impianto, e lo dimostra.

    Se qualcosa va storto a metà, si può ripetere: la chiave 0 cambia per
    ultima, quindi finché non è cambiata la tessera si riapre con quella di
    fabbrica, e le chiavi 1-4 già cambiate si riconoscono dal loro valore.
    """
    if len(uid) != 7:
        raise ErroreProgrammazione(
            "la tessera non ha un UID di 7 byte: non è una NTAG 424"
        )

    nuove = {
        NUMERO_APPLICAZIONE: chiave_applicazione(master, uid),
        NUMERO_META: chiave_meta(master),
        NUMERO_FILE: chiave_file(master, uid),
        **{n: chiave_riserva(master, uid, n) for n in _RISERVE},
    }

    await _iso(invia, SELEZIONA_APPLICAZIONE, "selezione dell'applicazione NDEF")
    await _scrivi_link(invia)

    await _iso(invia, SELEZIONA_APPLICAZIONE, "selezione dell'applicazione NDEF")
    sessione = await _autentica(invia, _FABBRICA, casuale)
    gia_nostra = sessione is None
    if gia_nostra:
        sessione = await _autentica(invia, nuove[NUMERO_APPLICAZIONE], casuale)
        if sessione is None:
            raise ErroreProgrammazione(
                "la chiave 0 della tessera non è né quella di fabbrica né quella "
                "dell'impianto: qualcuno l'ha già programmata con chiavi sue"
            )

    _, picc, mac = messaggio_ndef()
    await _comando_full(
        invia,
        sessione,
        _CMD_IMPOSTAZIONI,
        bytes([_FILE_NDEF]),
        impostazioni_sdm(picc, mac),
        "impostazioni SDM",
    )

    if not gia_nostra:
        for numero in (NUMERO_META, NUMERO_FILE, *_RISERVE):
            sessione = await _cambia_chiave(
                invia, sessione, numero, nuove, casuale
            )
        # Per ultima: da qui la tessera non si apre più con la chiave di
        # fabbrica, e la sessione finisce.
        await _comando_full(
            invia,
            sessione,
            _CMD_CAMBIA_CHIAVE,
            bytes([NUMERO_APPLICAZIONE]),
            dati_cambio_chiave(
                NUMERO_APPLICAZIONE,
                nuove[NUMERO_APPLICAZIONE],
                _VERSIONE_CHIAVI,
                vecchia=_FABBRICA,
                numero_autenticazione=NUMERO_APPLICAZIONE,
            ),
            "cambio della chiave 0",
            firmata=False,
        )

    # ── prova ──
    await _iso(invia, SELEZIONA_APPLICAZIONE, "selezione dell'applicazione NDEF")
    link = await _leggi_link(invia)
    verdetto = verifica_lettura(link, uid, master, None)
    if verdetto.esito != ESITO_VALIDO or verdetto.contatore is None:
        raise ErroreProgrammazione(
            f"prova: il messaggio della tessera non si verifica ({verdetto.esito})"
        )
    await _iso(invia, SELEZIONA_APPLICAZIONE, "selezione dell'applicazione NDEF")
    if await _autentica(invia, nuove[NUMERO_APPLICAZIONE], casuale) is None:
        raise ErroreProgrammazione("prova: la chiave 0 nuova non apre la tessera")

    return Esito(contatore=verdetto.contatore, gia_nostra=gia_nostra)


async def _cambia_chiave(
    invia: Invia,
    sessione: SessioneEV2,
    numero: int,
    nuove: dict[int, bytes],
    casuale: Callable[[int], bytes],
) -> SessioneEV2:
    """Cambia una delle chiavi 1-4, anche se una volta precedente l'ha già fatto.

    ChangeKey vuole la chiave vecchia (va in XOR con la nuova). Di norma è
    quella di fabbrica; dopo una programmazione interrotta può essere già la
    nuova. La tessera rifiuta la vecchia sbagliata e chiude la sessione: ci si
    riautentica e si prova l'altra.
    """
    for tentativo, vecchia in enumerate((_FABBRICA, nuove[numero])):
        if tentativo:
            await _iso(
                invia, SELEZIONA_APPLICAZIONE, "selezione dell'applicazione NDEF"
            )
            riaperta = await _autentica(invia, _FABBRICA, casuale)
            if riaperta is None:
                break
            sessione = riaperta
        try:
            await _comando_full(
                invia,
                sessione,
                _CMD_CAMBIA_CHIAVE,
                bytes([numero]),
                dati_cambio_chiave(
                    numero,
                    nuove[numero],
                    _VERSIONE_CHIAVI,
                    vecchia=vecchia,
                    numero_autenticazione=NUMERO_APPLICAZIONE,
                ),
                f"cambio della chiave {numero}",
            )
            return sessione
        except ErroreProgrammazione:
            if tentativo:
                raise
    raise ErroreProgrammazione(f"cambio della chiave {numero}: non riuscito")
