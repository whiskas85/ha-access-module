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
