"""Verifica della crittografia NTAG 424 DNA contro i vettori pubblicati da NXP.

Una verifica crittografica sbagliata non fallisce: dice «valida» a una tessera
falsa, e da fuori non c'è niente che lo mostri. L'unico modo di fidarsene è
farle riprodurre, byte per byte, i valori che NXP pubblica nelle sue note
applicative. Se questi test passano, il codice calcola esattamente quello che
calcola la tessera.

Il modulo si carica direttamente dal file, senza passare dal pacchetto: il
pacchetto importa Home Assistant, e qui non serve né lo si vuole installare.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_FILE = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "access_control"
    / "ntag424.py"
)
_spec = importlib.util.spec_from_file_location("ntag424", _FILE)
ntag424 = importlib.util.module_from_spec(_spec)
# Va registrato prima di eseguirlo: `@dataclass` cerca il proprio modulo in
# `sys.modules`, e caricandolo da file non ci finirebbe da solo.
sys.modules["ntag424"] = ntag424
_spec.loader.exec_module(ntag424)

ZERO = bytes(16)


# ── AN10922: diversificazione ──────────────────────────────────────────────

AN10922_MASTER = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
AN10922_INGRESSO = bytes.fromhex(
    "04782E21801D80"  # UID
    "3042F5"  # AID
    "4E585020416275"  # identificativo di sistema: «NXP Abu»
)


def test_sottochiave_iniziale_an10922():
    # Il primo passo di AN10922: la master cifra un blocco di zeri.
    assert ntag424._aes_blocco(AN10922_MASTER, ZERO) == bytes.fromhex(
        "FDE4FBAE4A09E020EFF722969F83832B"
    )


def test_diversificazione_an10922():
    assert ntag424.diversifica(AN10922_MASTER, AN10922_INGRESSO) == bytes.fromhex(
        "A8DD63A3B89D54B37CA802473FDA9175"
    )


def test_diversificazione_rifiuta_ingressi_fuori_misura():
    with pytest.raises(ValueError):
        ntag424.diversifica(AN10922_MASTER, b"")
    with pytest.raises(ValueError):
        ntag424.diversifica(AN10922_MASTER, bytes(32))
    with pytest.raises(ValueError):
        ntag424.diversifica(bytes(15), AN10922_INGRESSO)


# ── AN12196: messaggio SDM ─────────────────────────────────────────────────
#
# L'esempio di AN12196 con dati PICC cifrati e firma, a chiavi tutte a zero:
# e=EF963FF7828658A599F3041510671E88  c=94EED9EE65337086

AN12196_PICC = bytes.fromhex("EF963FF7828658A599F3041510671E88")
AN12196_MAC = bytes.fromhex("94EED9EE65337086")


def test_decifratura_picc_an12196():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    assert lettura.uid == bytes.fromhex("04DE5F1EACC040")
    assert lettura.contatore == 61


def test_firma_an12196():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    assert ntag424.mac_sdm(ZERO, lettura) == AN12196_MAC


def test_verifica_accetta_la_firma_giusta():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    assert ntag424.verifica(ZERO, lettura, AN12196_MAC)


# ── quello che deve essere rifiutato ───────────────────────────────────────


def test_verifica_rifiuta_una_firma_alterata_di_un_bit():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    alterata = bytes([AN12196_MAC[0] ^ 0x01]) + AN12196_MAC[1:]
    assert not ntag424.verifica(ZERO, lettura, alterata)


def test_verifica_rifiuta_la_firma_di_un_altro_uid():
    # La firma giusta, attaccata a un'altra tessera: è il clone dell'UID che
    # la verifica esiste per fermare.
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    altra = ntag424.Lettura(uid=bytes.fromhex("04DE5F1EACC041"), contatore=61)
    assert ntag424.verifica(ZERO, lettura, AN12196_MAC)
    assert not ntag424.verifica(ZERO, altra, AN12196_MAC)


def test_verifica_rifiuta_la_firma_con_un_altro_contatore():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    dopo = ntag424.Lettura(uid=lettura.uid, contatore=lettura.contatore + 1)
    assert not ntag424.verifica(ZERO, dopo, AN12196_MAC)


def test_verifica_rifiuta_con_la_chiave_sbagliata():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    assert not ntag424.verifica(bytes([1]) + ZERO[1:], lettura, AN12196_MAC)


def test_verifica_rifiuta_una_firma_della_lunghezza_sbagliata():
    lettura = ntag424.decifra_picc(ZERO, AN12196_PICC)
    assert not ntag424.verifica(ZERO, lettura, AN12196_MAC[:7])


def test_decifratura_con_chiave_sbagliata_non_produce_una_lettura_valida():
    # Con la chiave sbagliata esce rumore. O il rumore non ha nemmeno la forma
    # di un messaggio, o ce l'ha per caso — ma allora la firma non torna.
    chiave_sbagliata = bytes([1]) + ZERO[1:]
    try:
        lettura = ntag424.decifra_picc(chiave_sbagliata, AN12196_PICC)
    except ValueError:
        return
    assert not ntag424.verifica(ZERO, lettura, AN12196_MAC)


# ── contatore: niente messaggi riprodotti ─────────────────────────────────


def test_contatore_nuovo_accettato():
    assert ntag424.e_nuova(61, None)
    assert ntag424.e_nuova(62, 61)


def test_contatore_ripetuto_o_indietro_rifiutato():
    assert not ntag424.e_nuova(61, 61)
    assert not ntag424.e_nuova(60, 61)


# ── chiavi dell'impianto ───────────────────────────────────────────────────


def test_le_chiavi_per_scopi_diversi_sono_diverse():
    master = bytes(range(16))
    uid = bytes.fromhex("047BA7521F1E90")
    chiavi = {
        ntag424.chiave_meta(master),
        ntag424.chiave_file(master, uid),
        ntag424.chiave_applicazione(master, uid),
    }
    assert len(chiavi) == 3


def test_la_chiave_di_firma_cambia_da_tessera_a_tessera():
    master = bytes(range(16))
    assert ntag424.chiave_file(
        master, bytes.fromhex("047BA7521F1E90")
    ) != ntag424.chiave_file(master, bytes.fromhex("047BA7521F1E91"))


def test_la_chiave_di_cifratura_e_una_sola_per_impianto():
    # Non dipende dall'UID, per forza: l'UID sta dentro il blocco che cifra.
    master = bytes(range(16))
    assert ntag424.chiave_meta(master) == ntag424.chiave_meta(master)


# ── AN12196 §5.6: AuthenticateEV2First con la chiave 0 a zero ─────────────

AUTH_RND_A = bytes.fromhex("13C5DB8A5930439FC3DEF9A4C675360F")
AUTH_RND_B_CIFRATO = bytes.fromhex("A04C124213C186F22399D33AC2A30215")
AUTH_RISPOSTA = bytes.fromhex(
    "3FA64DB5446D1F34CD6EA311167F5E4985B89690C04A05F17FA7AB2F08120663"
)
AUTH_ENC = bytes.fromhex("1309C877509E5A215007FF0ED19CA564")
AUTH_MAC = bytes.fromhex("4C6626F5E72EA694202139295C7A7FC7")
AUTH_TI = bytes.fromhex("9D00C4DF")


def test_autenticazione_passo_1_an12196():
    dati, rnd_b = ntag424.autentica_passo_1(ZERO, AUTH_RND_B_CIFRATO, AUTH_RND_A)
    assert rnd_b == bytes.fromhex("B9E2FC789B64BF237CCCAA20EC7E6E48")
    assert dati == bytes.fromhex(
        "35C3E05A752E0144BAC0DE51C1F22C56B34408A23D8AEA266CAB947EA8E0118D"
    )


def test_autenticazione_passo_2_e_chiavi_di_sessione_an12196():
    _, rnd_b = ntag424.autentica_passo_1(ZERO, AUTH_RND_B_CIFRATO, AUTH_RND_A)
    sessione = ntag424.autentica_passo_2(ZERO, AUTH_RND_A, rnd_b, AUTH_RISPOSTA)
    assert sessione.ti == AUTH_TI
    assert sessione.enc == AUTH_ENC
    assert sessione.mac == AUTH_MAC
    assert sessione.contatore == 0


def test_autenticazione_rifiuta_una_tessera_che_non_conosce_la_chiave():
    # La risposta di una tessera con un'altra chiave: RndA ruotato non torna.
    _, rnd_b = ntag424.autentica_passo_1(ZERO, AUTH_RND_B_CIFRATO, AUTH_RND_A)
    alterata = bytes([AUTH_RISPOSTA[0] ^ 0x01]) + AUTH_RISPOSTA[1:]
    with pytest.raises(ValueError):
        ntag424.autentica_passo_2(ZERO, AUTH_RND_A, rnd_b, alterata)


# ── AN12196 §5.9: ChangeFileSettings in CommMode.Full ─────────────────────


def _sessione_an12196(contatore: int) -> object:
    return ntag424.SessioneEV2(
        enc=AUTH_ENC, mac=AUTH_MAC, ti=AUTH_TI, contatore=contatore
    )


def test_change_file_settings_an12196():
    sessione = _sessione_an12196(1)
    impostazioni = bytes.fromhex("4000E0C1F121200000430000430000")
    assert sessione._iv(bytes.fromhex("A55A"), 0) == bytes.fromhex(
        "3E27082AB2ACC1EF55C57547934E9962"
    )
    dati = sessione.dati_full(0x5F, b"\x02", impostazioni)
    assert ntag424.apdu(0x5F, dati) == bytes.fromhex(
        "905F0000190261B6D97903566E84C3AE5274467E89EAD799B7C1A0EF7A0400"
    )


def test_risposta_firmata_an12196():
    sessione = _sessione_an12196(1)
    assert sessione.chiudi(0x00, bytes.fromhex("57BFF87B1241E93D"), cifrata=True) == b""
    assert sessione.contatore == 2


def test_risposta_con_firma_sbagliata_interrompe():
    sessione = _sessione_an12196(1)
    with pytest.raises(ValueError):
        sessione.chiudi(0x00, bytes.fromhex("57BFF87B1241E93C"), cifrata=True)
    # Il contatore non sale: la risposta non si è accettata.
    assert sessione.contatore == 1


# ── AN12196 §5.16: ChangeKey, nei due casi ─────────────────────────────────


def test_crc32_della_chiave_nuova_an12196():
    nuova = bytes.fromhex("F3847D627727ED3BC9C4CC050489B966")
    assert ntag424.crc32_nxp(nuova) == bytes.fromhex("789DFADC")


def test_change_key_di_un_altra_chiave_an12196():
    # Caso 1: si cambia la chiave 2 da autenticati con la 0.
    sessione = ntag424.SessioneEV2(
        enc=bytes.fromhex("4CF3CB41A22583A61E89B158D252FC53"),
        mac=bytes.fromhex("5529860B2FC5FB6154B7F28361D30BF9"),
        ti=bytes.fromhex("7614281A"),
        contatore=2,
    )
    chiaro = ntag424.dati_cambio_chiave(
        2,
        bytes.fromhex("F3847D627727ED3BC9C4CC050489B966"),
        0x01,
        vecchia=ZERO,
        numero_autenticazione=0,
    )
    dati = sessione.dati_full(0xC4, b"\x02", chiaro)
    assert ntag424.apdu(0xC4, dati) == bytes.fromhex(
        "90C4000029022CF362B7BF4311FF3BE1DAA295E8C68DE09050560D19B9E16C2393AE9CD1FA"
        "C75D0CE20BCD1D06E600"
    )


def test_change_key_della_chiave_di_autenticazione_an12196():
    # Caso 2: si cambia la chiave 0 da autenticati con la 0.
    sessione = ntag424.SessioneEV2(
        enc=bytes.fromhex("4CF3CB41A22583A61E89B158D252FC53"),
        mac=bytes.fromhex("5529860B2FC5FB6154B7F28361D30BF9"),
        ti=bytes.fromhex("7614281A"),
        contatore=3,
    )
    chiaro = ntag424.dati_cambio_chiave(
        0,
        bytes.fromhex("5004BF991F408672B1EF00F08F9E8647"),
        0x01,
        vecchia=ZERO,
        numero_autenticazione=0,
    )
    dati = sessione.dati_full(0xC4, b"\x00", chiaro)
    assert ntag424.apdu(0xC4, dati) == bytes.fromhex(
        "90C400002900C0EB4DEEFEDDF0B513A03A95A75491818580503190D4D05053FF75668A01D6FD"
        "A6610234BDED643200"
    )


def test_una_firma_fatta_con_le_nostre_chiavi_si_verifica():
    # Il giro completo con chiavi derivate invece che a zero: quello che
    # succederà con una tessera programmata dal modulo.
    master = bytes(range(16))
    lettura = ntag424.Lettura(uid=bytes.fromhex("047BA7521F1E90"), contatore=7)
    chiave = ntag424.chiave_file(master, lettura.uid)
    mac = ntag424.mac_sdm(chiave, lettura)
    assert ntag424.verifica(chiave, lettura, mac)
    assert not ntag424.verifica(
        ntag424.chiave_file(master, bytes.fromhex("047BA7521F1E91")), lettura, mac
    )
