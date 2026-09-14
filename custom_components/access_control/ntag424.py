"""NTAG 424 DNA: diversificazione delle chiavi e verifica del messaggio SDM.

Qui dentro c'è solo crittografia, e apposta: niente Home Assistant, niente
store, niente rete. È la parte in cui un errore non si vede — una verifica
sbagliata non fallisce, dice «valida» a una tessera falsa — e l'unico modo di
fidarsene è provarla contro i vettori pubblicati da NXP. Tenerla isolata è ciò
che permette di farlo senza avviare nient'altro.

Riferimenti: AN10922 per la diversificazione delle chiavi, AN12196 per SDM.

**Due chiavi, non una.** La tessera fa due cose distinte con due chiavi
distinte, e non possono essere dello stesso tipo:

- *cifra* UID e contatore, perché non viaggino in chiaro. Questa chiave è
  **una per impianto**, per forza: per sapere quale chiave derivare bisognerebbe
  conoscere l'UID, che però sta proprio dentro il blocco cifrato. Chi la
  scoprisse leggerebbe gli UID — che del resto qualunque telefono legge dalla
  tessera — ma non potrebbe fabbricare una tessera valida.
- *firma* il messaggio. Questa è **una per tessera**, derivata da master e
  UID: è quella che dimostra che la tessera è autentica, e chi la scoprisse
  clonerebbe quella tessera sola.

La master non esce mai da questo modulo: da lei si derivano le altre, e sono
quelle derivate a viaggiare.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC

BLOCCO = 16
_ZERO = bytes(BLOCCO)

# Costante del campo di Galois usata da CMAC con blocchi da 128 bit
# (NIST SP 800-38B). Serve a derivare le sottochiavi K1 e K2, che AN10922
# usa esplicitamente e che la libreria non espone.
_RB = 0x87

# Primi byte del vettore di sessione da cui la tessera ricava la chiave MAC
# (AN12196, «SV2»): 3C C3 00 01 00 80, seguiti da UID e contatore.
_SV2 = bytes.fromhex("3CC300010080")

# Etichetta dell'impianto dentro l'ingresso di diversificazione. Separa gli
# usi della stessa master: senza, la chiave di firma e quella di cifratura
# potrebbero coincidere per costruzione.
SISTEMA = b"HA-accessi"

# Quale chiave della tessera fa cosa. L'NTAG 424 ne ha cinque, 0-4.
NUMERO_APPLICAZIONE = 0  # protegge la configurazione della tessera
NUMERO_META = 1  # cifra UID e contatore
NUMERO_FILE = 2  # firma il messaggio


# ── primitive ──────────────────────────────────────────────────────────────


def _aes_blocco(chiave: bytes, blocco: bytes) -> bytes:
    cifratore = Cipher(algorithms.AES(chiave), modes.ECB()).encryptor()
    return cifratore.update(blocco) + cifratore.finalize()


def _cmac(chiave: bytes, dati: bytes) -> bytes:
    calcolo = CMAC(algorithms.AES(chiave))
    calcolo.update(dati)
    return calcolo.finalize()


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


def _raddoppia(blocco: bytes) -> bytes:
    """Moltiplicazione per x nel campo di SP 800-38B."""
    valore = int.from_bytes(blocco, "big") << 1
    if blocco[0] & 0x80:
        valore ^= _RB
    return (valore & ((1 << 128) - 1)).to_bytes(BLOCCO, "big")


def _sottochiavi(chiave: bytes) -> tuple[bytes, bytes]:
    k1 = _raddoppia(_aes_blocco(chiave, _ZERO))
    return k1, _raddoppia(k1)


# ── diversificazione (AN10922) ─────────────────────────────────────────────


def diversifica(master: bytes, ingresso: bytes) -> bytes:
    """Chiave derivata da una master, secondo AN10922 (AES-128).

    Non è un CMAC qualunque applicato all'ingresso, e la differenza conta: il
    dato viene **sempre** portato a 32 byte, anche quando basterebbero 16. Un
    CMAC standard su un ingresso corto userebbe un blocco solo e darebbe un
    risultato diverso — funzionerebbe lo stesso fra i nostri due capi, ma non
    sarebbe più lo schema che si dichiara di usare, e i vettori NXP non
    tornerebbero.
    """
    if len(master) != BLOCCO:
        raise ValueError("La master deve essere di 16 byte")
    if not 1 <= len(ingresso) <= 31:
        raise ValueError("L'ingresso di diversificazione va da 1 a 31 byte")

    k1, k2 = _sottochiavi(master)
    dati = b"\x01" + ingresso
    if len(dati) < 2 * BLOCCO:
        dati += b"\x80" + bytes(2 * BLOCCO - len(dati) - 1)
        ultima = k2
    else:
        ultima = k1
    dati = dati[:BLOCCO] + _xor(dati[BLOCCO:], ultima)

    cifratore = Cipher(algorithms.AES(master), modes.CBC(_ZERO)).encryptor()
    return (cifratore.update(dati) + cifratore.finalize())[BLOCCO:]


def chiave_meta(master: bytes) -> bytes:
    """La chiave che cifra UID e contatore: una per impianto."""
    return diversifica(master, bytes([NUMERO_META]) + SISTEMA)


def chiave_file(master: bytes, uid: bytes) -> bytes:
    """La chiave con cui questa tessera firma il messaggio."""
    return diversifica(master, uid + bytes([NUMERO_FILE]) + SISTEMA)


def chiave_applicazione(master: bytes, uid: bytes) -> bytes:
    """La chiave che protegge la configurazione di questa tessera.

    Senza cambiarla, chiunque con un telefono potrebbe riscrivere le
    impostazioni SDM della tessera — per esempio spegnere la firma — perché
    esce di fabbrica con la chiave tutta a zero.
    """
    return diversifica(master, uid + bytes([NUMERO_APPLICAZIONE]) + SISTEMA)


# ── messaggio SDM (AN12196) ────────────────────────────────────────────────


@dataclass(frozen=True)
class Lettura:
    """Quello che la tessera dichiara di sé: chi è e quante volte è stata letta."""

    uid: bytes
    contatore: int


def decifra_picc(chiave: bytes, cifrato: bytes) -> Lettura:
    """Apre il blocco cifrato con UID e contatore.

    Decifrare **non** dimostra niente: con una chiave sbagliata si ottiene un
    blocco di rumore che, una volta su tanti, ha l'aria di un UID. È la firma
    a dire se la tessera è vera. Per questo si pretende che ci siano entrambi,
    UID e contatore: una tessera configurata senza contatore non permetterebbe
    di riconoscere un messaggio già visto, e verrebbe ripetuta all'infinito.
    """
    if len(cifrato) != BLOCCO:
        raise ValueError("Il blocco cifrato deve essere di 16 byte")

    decifratore = Cipher(algorithms.AES(chiave), modes.CBC(_ZERO)).decryptor()
    chiaro = decifratore.update(cifrato) + decifratore.finalize()

    etichetta = chiaro[0]
    if not (etichetta & 0x80 and etichetta & 0x40):
        raise ValueError("Il messaggio non contiene UID e contatore")
    lunghezza = etichetta & 0x0F
    if lunghezza != 7:
        raise ValueError(f"UID di {lunghezza} byte: l'NTAG 424 ne ha 7")

    uid = chiaro[1 : 1 + lunghezza]
    contatore = int.from_bytes(chiaro[1 + lunghezza : 4 + lunghezza], "little")
    return Lettura(uid=uid, contatore=contatore)


def mac_sdm(chiave: bytes, lettura: Lettura, dati: bytes = b"") -> bytes:
    """La firma che la tessera avrebbe dovuto produrre per questa lettura.

    Prima si ricava una chiave di sessione legata a UID e contatore, poi si
    firma con quella. È ciò che rende la firma diversa a ogni lettura anche a
    parità di tessera: il contatore cambia, la chiave di sessione pure.

    Dei 16 byte del CMAC la tessera ne tiene 8, quelli in posizione dispari.
    """
    vettore = _SV2 + lettura.uid + lettura.contatore.to_bytes(3, "little")
    vettore += bytes(-len(vettore) % BLOCCO)
    sessione = _cmac(chiave, vettore)
    return _cmac(sessione, dati)[1::2]


def verifica(chiave: bytes, lettura: Lettura, mac: bytes, dati: bytes = b"") -> bool:
    """La firma è quella giusta?

    Il confronto è a tempo costante: uno che si ferma al primo byte diverso
    racconterebbe, col suo tempo di risposta, quanti byte si sono indovinati.
    """
    if len(mac) != 8:
        return False
    return hmac.compare_digest(mac_sdm(chiave, lettura, dati), mac)


def e_nuova(contatore: int, ultimo: int | None) -> bool:
    """Il contatore è andato avanti rispetto all'ultimo visto?

    Un messaggio firmato bene ma con un contatore già visto è una lettura
    **registrata e riprodotta**: qualcuno ha catturato il messaggio e lo sta
    rimandando. La firma da sola non lo rivela — era valida la prima volta, e
    lo è ancora — quindi è il contatore a doverlo fermare.
    """
    return ultimo is None or contatore > ultimo
