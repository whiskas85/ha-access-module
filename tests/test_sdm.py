"""Dal link letto alla porta al verdetto: `sdm.py`.

I messaggi vengono o dall'esempio pubblicato da NXP (chiavi di fabbrica) o
fabbricati qui con le stesse operazioni della tessera, per le chiavi
dell'impianto. Nessuna lettura di una tessera vera: il messaggio contiene
l'UID, e un UID reale nel repository è un UID pubblicato (SPEC.md §3).

`sdm.py` importa `ntag424.py` con un import relativo, quindi va caricato come
parte di un pacchetto. Il pacchetto vero importa Home Assistant: qui se ne
registra uno vuoto che punta alla stessa cartella, e basta.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_CARTELLA = (
    Path(__file__).resolve().parent.parent / "custom_components" / "access_control"
)
_pacchetto = types.ModuleType("access_control")
_pacchetto.__path__ = [str(_CARTELLA)]
sys.modules.setdefault("access_control", _pacchetto)

sdm = importlib.import_module("access_control.sdm")
ntag424 = importlib.import_module("access_control.ntag424")

ZERO = bytes(16)
MASTER = bytes(range(16))
UID = bytes.fromhex("04112233445566")
ALTRO_UID = bytes.fromhex("04112233445567")

# L'esempio di AN12196, a chiavi di fabbrica: UID 04DE5F1EACC040, contatore 61.
AN12196_UID = bytes.fromhex("04DE5F1EACC040")
AN12196_LINK = (
    "example.com/a?picc_data=EF963FF7828658A599F3041510671E88&cmac=94EED9EE65337086"
)


def _link(picc: bytes, mac: bytes) -> str:
    return f"example.com/a?picc_data={picc.hex().upper()}&cmac={mac.hex().upper()}"


def _messaggio(master: bytes, uid: bytes, contatore: int) -> str:
    """Il link che produrrebbe una tessera programmata con questa master."""
    chiaro = (
        bytes([0xC7])  # UID e contatore presenti, UID di 7 byte
        + uid
        + contatore.to_bytes(3, "little")
        + bytes.fromhex("A1B2C3D4E5")  # riempimento casuale della tessera
    )
    cifratore = Cipher(
        algorithms.AES(ntag424.chiave_meta(master)), modes.CBC(ZERO)
    ).encryptor()
    picc = cifratore.update(chiaro) + cifratore.finalize()
    lettura = ntag424.Lettura(uid=uid, contatore=contatore)
    mac = ntag424.mac_sdm(ntag424.chiave_file(master, uid), lettura)
    return _link(picc, mac)


# ── chiavi dell'impianto ───────────────────────────────────────────────────


def test_messaggio_dell_impianto_e_valido():
    verdetto = sdm.verifica_lettura(_messaggio(MASTER, UID, 8), UID, MASTER, None)
    assert verdetto.esito == sdm.ESITO_VALIDO
    assert verdetto.contatore == 8
    assert verdetto.forte


def test_contatore_che_sale_resta_valido():
    verdetto = sdm.verifica_lettura(_messaggio(MASTER, UID, 9), UID, MASTER, 8)
    assert verdetto.esito == sdm.ESITO_VALIDO


def test_contatore_gia_visto_e_un_replay():
    link = _messaggio(MASTER, UID, 8)
    assert sdm.verifica_lettura(link, UID, MASTER, 8).esito == sdm.ESITO_REPLAY
    assert sdm.verifica_lettura(link, UID, MASTER, 9).esito == sdm.ESITO_REPLAY
    assert not sdm.verifica_lettura(link, UID, MASTER, 8).forte


def test_messaggio_di_un_altra_tessera_non_vale():
    # Il messaggio vero di una tessera, presentato da un'altra con un altro
    # UID: è la lettura registrata e rigiocata da una tessera clone.
    link = _messaggio(MASTER, UID, 8)
    verdetto = sdm.verifica_lettura(link, ALTRO_UID, MASTER, None)
    assert verdetto.esito == sdm.ESITO_NON_VALIDO
    assert not verdetto.forte


def test_firma_alterata_non_vale():
    picc, mac = sdm.estrai(_messaggio(MASTER, UID, 8))
    alterata = bytes([mac[0] ^ 0x01]) + mac[1:]
    verdetto = sdm.verifica_lettura(_link(picc, alterata), UID, MASTER, None)
    assert verdetto.esito == sdm.ESITO_NON_VALIDO


def test_messaggio_di_un_altro_impianto_non_vale():
    link = _messaggio(bytes(range(1, 17)), UID, 8)
    assert sdm.verifica_lettura(link, UID, MASTER, None).esito == sdm.ESITO_NON_VALIDO


def test_senza_master_nessuna_tessera_e_forte():
    verdetto = sdm.verifica_lettura(_messaggio(MASTER, UID, 8), UID, None, None)
    assert verdetto.esito == sdm.ESITO_NON_VALIDO
    assert not verdetto.forte


# ── chiavi di fabbrica ─────────────────────────────────────────────────────


def test_esempio_nxp_a_chiavi_di_fabbrica():
    verdetto = sdm.verifica_lettura(AN12196_LINK, AN12196_UID, None, None)
    assert verdetto.esito == sdm.ESITO_FABBRICA
    assert verdetto.contatore == 61


def test_chiavi_di_fabbrica_non_sono_mai_forti():
    # Nemmeno con una master presente e un contatore mai visto: quelle chiavi
    # le conosce chiunque, e un messaggio così lo fabbrica chiunque.
    verdetto = sdm.verifica_lettura(AN12196_LINK, AN12196_UID, MASTER, None)
    assert verdetto.esito == sdm.ESITO_FABBRICA
    assert not verdetto.forte


def test_chiavi_di_fabbrica_con_l_uid_sbagliato_non_valgono():
    verdetto = sdm.verifica_lettura(AN12196_LINK, UID, None, None)
    assert verdetto.esito == sdm.ESITO_NON_VALIDO


# ── link che non portano un messaggio ──────────────────────────────────────


def test_letture_senza_messaggio():
    for link in (
        "",
        "example.com/a",
        "example.com/a?",
        "example.com/a?picc_data=EF963FF7828658A599F3041510671E88",
        "example.com/a?cmac=94EED9EE65337086",
        # lunghezze sbagliate
        "example.com/a?picc_data=EF963FF7828658A599F3041510671E8&cmac=94EED9EE65337086",
        "example.com/a?picc_data=EF963FF7828658A599F3041510671E88&cmac=94EED9EE6533708",
        # non esadecimale, spazi dentro
        "example.com/a?picc_data=EF963FF7828658A599F3041510671EXX&cmac=94EED9EE65337086",
        "example.com/a?picc_data=EF963FF7828658A5+9F3041510671E88&cmac=94EED9EE65337086",
    ):
        assert sdm.verifica_lettura(link, AN12196_UID, None, None).esito == (
            sdm.ESITO_ASSENTE
        ), link


def test_campi_ripetuti_si_scartano():
    # Due `cmac`: chi l'ha costruito vuole vedere quale dei due viene letto.
    link = AN12196_LINK + "&cmac=0000000000000000"
    assert sdm.estrai(link) is None


def test_link_troppo_lungo_si_scarta():
    assert sdm.estrai(AN12196_LINK + "&x=" + "a" * 300) is None


def test_non_stringa_si_scarta():
    assert sdm.estrai(None) is None
    assert sdm.estrai(12345) is None
