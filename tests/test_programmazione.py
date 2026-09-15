"""La sequenza di programmazione, contro una NTAG 424 simulata.

Si prova il giro intero come succederà alla porta: una tessera di fabbrica
esce con le chiavi dell'impianto e un messaggio che si verifica. E si provano
le cose che alla porta non si possono provare senza rischiare una tessera:
la programmazione interrotta e ripresa, la risposta manomessa per strada, la
tessera che ha chiavi di qualcun altro. E che dal tramite — cioè dal lettore
— non passi mai una chiave in chiaro.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulatore_ntag424 import TesseraSimulata

_CARTELLA = (
    Path(__file__).resolve().parent.parent / "custom_components" / "access_control"
)
_pacchetto = types.ModuleType("access_control")
_pacchetto.__path__ = [str(_CARTELLA)]
sys.modules.setdefault("access_control", _pacchetto)

ntag424 = importlib.import_module("access_control.ntag424")
sdm = importlib.import_module("access_control.sdm")
prog = importlib.import_module("access_control.programmazione")

MASTER = bytes(range(16))
UID = bytes.fromhex("04112233445566")


class Tramite:
    """Il lettore: passa i byte e li registra, come farebbe uno manomesso."""

    def __init__(self, tessera: TesseraSimulata, *, guasto_dopo: int | None = None):
        self.tessera = tessera
        self.traffico: list[bytes] = []
        self.guasto_dopo = guasto_dopo
        self.altera = None

    async def __call__(self, comando: bytes) -> bytes:
        if self.guasto_dopo is not None and len(self.traffico) >= self.guasto_dopo:
            raise prog.ErroreProgrammazione("la tessera si è allontanata")
        self.traffico.append(comando)
        risposta = self.tessera.rispondi(comando)
        if self.altera is not None:
            risposta = self.altera(comando, risposta)
        self.traffico.append(risposta)
        return risposta


def _programma(tramite: Tramite, master: bytes = MASTER):
    return asyncio.run(prog.programma(tramite, UID, master))


def _chiavi_attese(master: bytes = MASTER) -> dict[int, bytes]:
    return {
        0: ntag424.chiave_applicazione(master, UID),
        1: ntag424.chiave_meta(master),
        2: ntag424.chiave_file(master, UID),
        3: ntag424.chiave_riserva(master, UID, 3),
        4: ntag424.chiave_riserva(master, UID, 4),
    }


# ── il giro normale ────────────────────────────────────────────────────────


def test_una_tessera_di_fabbrica_esce_programmata():
    tessera = TesseraSimulata(ntag424, UID)
    esito = _programma(Tramite(tessera))
    assert not esito.gia_nostra
    assert tessera.chiavi == _chiavi_attese()
    assert not tessera.scrittura_libera


def test_dopo_la_programmazione_la_porta_la_verifica_come_forte():
    tessera = TesseraSimulata(ntag424, UID)
    esito = _programma(Tramite(tessera))
    # La lettura della porta: libera, senza autenticazione.
    tessera.rispondi(prog.SELEZIONA_APPLICAZIONE)
    tessera.rispondi(prog.SELEZIONA_FILE_NDEF)
    file = tessera.rispondi(bytes.fromhex("00B0000000"))[:-2]
    link = prog.link_da_ndef(file)
    verdetto = sdm.verifica_lettura(link, UID, MASTER, esito.contatore)
    assert verdetto.esito == sdm.ESITO_VALIDO
    assert verdetto.contatore > esito.contatore


def test_programmarla_di_nuovo_non_fa_danni():
    tessera = TesseraSimulata(ntag424, UID)
    _programma(Tramite(tessera))
    esito = _programma(Tramite(tessera))
    assert esito.gia_nostra
    assert tessera.chiavi == _chiavi_attese()


# ── dal lettore non passa niente di segreto ────────────────────────────────


def test_nessuna_chiave_passa_in_chiaro_dal_tramite():
    tessera = TesseraSimulata(ntag424, UID)
    tramite = Tramite(tessera)
    _programma(tramite)
    traffico = b"".join(tramite.traffico)
    for chiave in (MASTER, *_chiavi_attese().values()):
        assert chiave not in traffico


# ── quando qualcosa va storto ──────────────────────────────────────────────


@pytest.mark.parametrize("guasto_dopo", range(2, 60, 3))
def test_una_programmazione_interrotta_si_riprende(guasto_dopo):
    # La tessera si allontana a un passo qualunque. Ripetendo, deve finire
    # programmata comunque: la chiave 0 cambia per ultima apposta.
    tessera = TesseraSimulata(ntag424, UID)
    with contextlib.suppress(prog.ErroreProgrammazione):
        _programma(Tramite(tessera, guasto_dopo=guasto_dopo))
    _programma(Tramite(tessera))
    assert tessera.chiavi == _chiavi_attese()


def test_una_risposta_manomessa_ferma_tutto_prima_delle_chiavi():
    tessera = TesseraSimulata(ntag424, UID)
    tramite = Tramite(tessera)

    def altera(comando: bytes, risposta: bytes) -> bytes:
        # La firma della risposta alle impostazioni SDM, cambiata di un bit.
        if comando[:2] == b"\x90\x5f" and len(risposta) == 10:
            return bytes([risposta[0] ^ 0x01]) + risposta[1:]
        return risposta

    tramite.altera = altera
    with pytest.raises(prog.ErroreProgrammazione):
        _programma(tramite)
    assert tessera.chiavi[0] == bytes(16)


def test_una_tessera_con_chiavi_di_altri_non_si_tocca():
    tessera = TesseraSimulata(ntag424, UID)
    _programma(Tramite(tessera), master=bytes(range(1, 17)))
    prima = dict(tessera.chiavi)
    with pytest.raises(prog.ErroreProgrammazione, match="chiavi sue"):
        _programma(Tramite(tessera))
    assert tessera.chiavi == prima


def test_uid_che_non_e_di_una_ntag424_si_rifiuta():
    tessera = TesseraSimulata(ntag424, UID)
    with pytest.raises(prog.ErroreProgrammazione):
        asyncio.run(prog.programma(Tramite(tessera), bytes(4), MASTER))


# ── il contenuto della tessera ─────────────────────────────────────────────


def test_il_link_con_i_segnaposto_si_legge_come_quello_della_porta():
    file, picc, mac = prog.messaggio_ndef()
    link = prog.link_da_ndef(file)
    assert link.startswith(prog.DOMINIO)
    assert file[picc : picc + 32] == b"0" * 32
    assert file[mac : mac + 16] == b"0" * 16
    # Deve stare nei limiti che il lettore accetta.
    assert len(file) - 2 <= 200
