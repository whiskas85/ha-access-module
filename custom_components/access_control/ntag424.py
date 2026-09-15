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
import zlib
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


def chiave_riserva(master: bytes, uid: bytes, numero: int) -> bytes:
    """Le chiavi 3 e 4, che l'impianto non usa.

    Non si lasciano a zero lo stesso: AN12196 raccomanda di impostarle tutte,
    e una chiave di fabbrica su una tessera programmata è una porta di cui
    chiunque ha la chiave, anche se oggi non apre niente di nostro.
    """
    if numero in (NUMERO_APPLICAZIONE, NUMERO_META, NUMERO_FILE):
        raise ValueError("Le chiavi 0, 1 e 2 hanno la loro funzione")
    return diversifica(master, uid + bytes([numero]) + SISTEMA)


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


def _cbc(chiave: bytes, iv: bytes, dati: bytes, *, cifra: bool) -> bytes:
    cipher = Cipher(algorithms.AES(chiave), modes.CBC(iv))
    lavoro = cipher.encryptor() if cifra else cipher.decryptor()
    return lavoro.update(dati) + lavoro.finalize()


# ── messaggistica sicura EV2 (AN12196 §4, §5.6, §5.9, §5.16) ──────────────
#
# Serve alla programmazione: per cambiare chiavi e impostazioni la tessera
# vuole un'autenticazione a sfida, e poi comandi cifrati e firmati con due
# chiavi di sessione nate da quella sfida. Tutto qui dentro, e quindi in Home
# Assistant: il lettore passa i byte e basta, e non vede mai né le chiavi né
# le chiavi di sessione (SPEC.md §15, scelta «B»).

# Prefissi dei vettori da cui nascono le chiavi di sessione (SV1, SV2) e gli
# IV dei comandi e delle risposte cifrate.
_SV_ENC = bytes.fromhex("A55A00010080")
_SV_MAC = bytes.fromhex("5AA500010080")
_IV_COMANDO = bytes.fromhex("A55A")
_IV_RISPOSTA = bytes.fromhex("5AA5")


def _ruota(dati: bytes) -> bytes:
    """Rotazione a sinistra di un byte: RndB → RndB'."""
    return dati[1:] + dati[:1]


def _riempi(dati: bytes) -> bytes:
    """Padding ISO/IEC 9797-1 metodo 2: 80 e poi zeri, sempre."""
    dati += b"\x80"
    return dati + bytes(-len(dati) % BLOCCO)


def _svuota(dati: bytes) -> bytes:
    """Toglie il padding del metodo 2, e pretende che ci sia davvero."""
    fine = dati.rstrip(b"\x00")
    if not fine or fine[-1] != 0x80:
        raise ValueError("Padding assente o sbagliato")
    return fine[:-1]


def _troncato(mac: bytes) -> bytes:
    """Degli 16 byte di un CMAC la tessera usa gli 8 in posizione dispari."""
    return mac[1::2]


def chiavi_di_sessione(
    chiave: bytes, rnd_a: bytes, rnd_b: bytes
) -> tuple[bytes, bytes]:
    """Le due chiavi di sessione (cifratura, firma) dopo AuthenticateEV2First.

    I 26 byte variabili mescolano i due casuali come vuole AN12196: i primi
    2 di RndA, poi 6 di RndA in XOR con i primi 6 di RndB, poi gli ultimi 10
    di RndB e gli ultimi 8 di RndA.
    """
    miscela = (
        rnd_a[0:2]
        + _xor(rnd_a[2:8], rnd_b[0:6])
        + rnd_b[6:16]
        + rnd_a[8:16]
    )
    return _cmac(chiave, _SV_ENC + miscela), _cmac(chiave, _SV_MAC + miscela)


def autentica_passo_1(
    chiave: bytes, rnd_b_cifrato: bytes, rnd_a: bytes
) -> tuple[bytes, bytes]:
    """Risposta alla sfida della tessera: (dati da mandarle, RndB in chiaro).

    La tessera manda RndB cifrato con la chiave; si risponde con RndA seguito
    da RndB ruotato, cifrati insieme. Chi non conosce la chiave non sa ruotare
    un RndB che non riesce a leggere.
    """
    if len(rnd_b_cifrato) != BLOCCO or len(rnd_a) != BLOCCO:
        raise ValueError("RndA e RndB sono di 16 byte")
    rnd_b = _cbc(chiave, _ZERO, rnd_b_cifrato, cifra=False)
    return _cbc(chiave, _ZERO, rnd_a + _ruota(rnd_b), cifra=True), rnd_b


@dataclass
class SessioneEV2:
    """Un'autenticazione riuscita: chiavi di sessione, TI e contatore comandi.

    Il contatore sale di uno a ogni scambio con la tessera, anche per i
    comandi in chiaro, ed entra in ogni IV e in ogni firma: un comando
    registrato e rimandato più tardi porta il contatore sbagliato e la
    tessera lo rifiuta.
    """

    enc: bytes
    mac: bytes
    ti: bytes
    contatore: int = 0

    def _contatore(self, scarto: int = 0) -> bytes:
        return (self.contatore + scarto).to_bytes(2, "little")

    def _iv(self, prefisso: bytes, scarto: int) -> bytes:
        vettore = prefisso + self.ti + self._contatore(scarto)
        return _aes_blocco(self.enc, vettore + bytes(BLOCCO - len(vettore)))

    def cifra(self, dati: bytes) -> bytes:
        """I dati di un comando in CommMode.Full, già con il padding."""
        return _cbc(self.enc, self._iv(_IV_COMANDO, 0), _riempi(dati), cifra=True)

    def decifra(self, dati: bytes) -> bytes:
        """I dati di una risposta in CommMode.Full, senza padding."""
        if not dati:
            return b""
        chiaro = _cbc(self.enc, self._iv(_IV_RISPOSTA, 1), dati, cifra=False)
        return _svuota(chiaro)

    def mac_comando(self, comando: int, intestazione: bytes, dati: bytes) -> bytes:
        corpo = bytes([comando]) + self._contatore() + self.ti + intestazione + dati
        return _troncato(_cmac(self.mac, corpo))

    def mac_risposta(self, stato: int, dati: bytes) -> bytes:
        corpo = bytes([stato]) + self._contatore(1) + self.ti + dati
        return _troncato(_cmac(self.mac, corpo))

    def dati_full(self, comando: int, intestazione: bytes, dati: bytes) -> bytes:
        """Il campo dati di un comando CommMode.Full: intestazione, cifrato, firma."""
        cifrato = self.cifra(dati)
        return intestazione + cifrato + self.mac_comando(comando, intestazione, cifrato)

    def chiudi(self, stato: int, risposta: bytes, *, cifrata: bool) -> bytes:
        """Verifica la firma della risposta, la decifra, e fa salire il contatore.

        Una firma sbagliata non si tollera: vuol dire che a rispondere non è
        la tessera con cui ci si è autenticati, o che qualcuno ha toccato i
        byte per strada. Si interrompe tutto.
        """
        if len(risposta) < 8:
            raise ValueError("Risposta senza firma")
        dati, firma = risposta[:-8], risposta[-8:]
        if not hmac.compare_digest(self.mac_risposta(stato, dati), firma):
            raise ValueError("Firma della risposta non valida")
        chiaro = self.decifra(dati) if cifrata else dati
        self.contatore += 1
        return chiaro


def autentica_passo_2(
    chiave: bytes, rnd_a: bytes, rnd_b: bytes, risposta: bytes
) -> SessioneEV2:
    """Chiude l'autenticazione, e controlla che la tessera conosca la chiave.

    La tessera rimanda RndA ruotato: se lo sa ruotare, ha letto RndA, cioè
    ha la chiave. Solo allora si aprono le chiavi di sessione.
    """
    if len(risposta) != 2 * BLOCCO:
        raise ValueError("Risposta di autenticazione della lunghezza sbagliata")
    chiaro = _cbc(chiave, _ZERO, risposta, cifra=False)
    ti, rnd_a_ruotato = chiaro[0:4], chiaro[4:20]
    if not hmac.compare_digest(rnd_a_ruotato, _ruota(rnd_a)):
        raise ValueError("La tessera non ha dimostrato di conoscere la chiave")
    enc, mac = chiavi_di_sessione(chiave, rnd_a, rnd_b)
    return SessioneEV2(enc=enc, mac=mac, ti=ti)


def crc32_nxp(dati: bytes) -> bytes:
    """Il CRC32 che ChangeKey vuole sulla chiave nuova: senza l'inversione
    finale del CRC32 standard, e con i byte in ordine little-endian."""
    return ((zlib.crc32(dati) ^ 0xFFFFFFFF) & 0xFFFFFFFF).to_bytes(4, "little")


def dati_cambio_chiave(
    numero: int,
    nuova: bytes,
    versione: int,
    *,
    vecchia: bytes,
    numero_autenticazione: int,
) -> bytes:
    """I dati in chiaro di ChangeKey (AN12196 §5.16).

    Due forme. Se si cambia la chiave con cui ci si è autenticati, basta la
    nuova. Se se ne cambia un'altra, la nuova va in XOR con la vecchia e
    accompagnata dal suo CRC: così la tessera controlla che chi la cambia
    conosca anche quella vecchia, e che la nuova sia arrivata intera.
    """
    if len(nuova) != BLOCCO or len(vecchia) != BLOCCO:
        raise ValueError("Le chiavi sono di 16 byte")
    if numero == numero_autenticazione:
        return nuova + bytes([versione])
    return _xor(vecchia, nuova) + bytes([versione]) + crc32_nxp(nuova)


def apdu(comando: int, dati: bytes = b"") -> bytes:
    """Un comando nativo della tessera avvolto in un APDU ISO 7816-4."""
    if dati:
        return bytes([0x90, comando, 0x00, 0x00, len(dati)]) + dati + b"\x00"
    return bytes([0x90, comando, 0x00, 0x00, 0x00])


def e_nuova(contatore: int, ultimo: int | None) -> bool:
    """Il contatore è andato avanti rispetto all'ultimo visto?

    Un messaggio firmato bene ma con un contatore già visto è una lettura
    **registrata e riprodotta**: qualcuno ha catturato il messaggio e lo sta
    rimandando. La firma da sola non lo rivela — era valida la prima volta, e
    lo è ancora — quindi è il contatore a doverlo fermare.
    """
    return ultimo is None or contatore > ultimo
