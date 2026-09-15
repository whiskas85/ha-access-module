"""Una NTAG 424 DNA finta, quanto basta per provare la programmazione.

Risponde ai comandi che la sequenza usa, con le regole della tessera vera:
autenticazione a sfida, comandi cifrati e firmati con il contatore, chiave
vecchia pretesa da ChangeKey, scrittura chiusa dalle impostazioni, messaggio
SDM a ogni lettura libera. Un comando con la firma sbagliata viene rifiutato
e chiude la sessione, come fa la tessera.

Usa la crittografia di `ntag424.py`, quindi non la prova: quella è provata
contro i vettori NXP in `test_ntag424.py`. Qui si prova la *sequenza* — che
i passi siano quelli giusti, nell'ordine giusto, e che una tessera vera
nelle stesse condizioni finirebbe programmata.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class TesseraSimulata:
    def __init__(self, ntag424, uid: bytes) -> None:
        self.n = ntag424
        self.uid = uid
        self.chiavi = {n: bytes(16) for n in range(5)}
        self.versioni = {n: 0 for n in range(5)}
        self.file = bytearray(256)
        self.scrittura_libera = True
        self.sdm: dict | None = None
        self.contatore_sdm = 0
        self.app = False
        self.file_ndef = False
        self._sfida: tuple[int, bytes] | None = None
        self.sessione = None
        self.numero_sessione: int | None = None

    # ── utilità ──

    def _chiudi_sessione(self) -> None:
        self.sessione = None
        self.numero_sessione = None
        self._sfida = None

    def _cbc(self, chiave, iv, dati, cifra):
        c = Cipher(algorithms.AES(chiave), modes.CBC(iv))
        lavoro = c.encryptor() if cifra else c.decryptor()
        return lavoro.update(dati) + lavoro.finalize()

    def _file_letto(self) -> bytes:
        """Il file NDEF come lo vede chi lo legge: con il messaggio SDM."""
        dati = bytearray(self.file)
        if self.sdm is None:
            return bytes(dati)
        self.contatore_sdm += 1
        chiaro = (
            bytes([0xC7])
            + self.uid
            + self.contatore_sdm.to_bytes(3, "little")
            + os.urandom(5)
        )
        picc = self._cbc(self.chiavi[self.sdm["meta"]], bytes(16), chiaro, True)
        lettura = self.n.Lettura(uid=self.uid, contatore=self.contatore_sdm)
        mac = self.n.mac_sdm(self.chiavi[self.sdm["file"]], lettura)
        for inizio, valore in ((self.sdm["picc"], picc), (self.sdm["mac"], mac)):
            testo = valore.hex().upper().encode()
            dati[inizio : inizio + len(testo)] = testo
        return bytes(dati)

    # ── comandi ──

    def rispondi(self, comando: bytes) -> bytes:
        if comando[:2] == b"\x00\xa4":
            return self._seleziona(comando)
        if comando[:2] == b"\x00\xd6":
            return self._aggiorna(comando)
        if comando[:2] == b"\x00\xb0":
            return self._leggi(comando)
        if comando[0] == 0x90:
            codice = comando[1]
            dati = comando[5:-1] if len(comando) > 5 else b""
            if codice == 0x71:
                return self._autentica_1(dati)
            if codice == 0xAF:
                return self._autentica_2(dati)
            if codice == 0x5F:
                return self._impostazioni(dati)
            if codice == 0xC4:
                return self._cambia_chiave(dati)
        return b"\x6d\x00"

    def _seleziona(self, comando: bytes) -> bytes:
        if comando[2] == 0x04 and b"\xd2\x76\x00\x00\x85\x01\x01" in comando:
            self.app, self.file_ndef = True, False
            self._chiudi_sessione()
            return b"\x90\x00"
        if comando[2] == 0x00 and comando[5:7] == b"\xe1\x04" and self.app:
            self.file_ndef = True
            return b"\x90\x00"
        return b"\x6a\x82"

    def _aggiorna(self, comando: bytes) -> bytes:
        if not self.file_ndef:
            return b"\x69\x86"
        if not self.scrittura_libera:
            return b"\x69\x82"
        inizio = (comando[2] << 8) | comando[3]
        dati = comando[5 : 5 + comando[4]]
        self.file[inizio : inizio + len(dati)] = dati
        return b"\x90\x00"

    def _leggi(self, comando: bytes) -> bytes:
        if not self.file_ndef:
            return b"\x69\x86"
        inizio = (comando[2] << 8) | comando[3]
        quanti = comando[4] or 256
        return self._file_letto()[inizio : inizio + quanti] + b"\x90\x00"

    def _autentica_1(self, dati: bytes) -> bytes:
        self._chiudi_sessione()
        numero = dati[0]
        rnd_b = os.urandom(16)
        self._sfida = (numero, rnd_b)
        return self._cbc(self.chiavi[numero], bytes(16), rnd_b, True) + b"\x91\xaf"

    def _autentica_2(self, dati: bytes) -> bytes:
        if self._sfida is None:
            return b"\x91\xca"
        numero, rnd_b = self._sfida
        chiave = self.chiavi[numero]
        chiaro = self._cbc(chiave, bytes(16), dati, False)
        rnd_a, rnd_b_ruotato = chiaro[:16], chiaro[16:]
        self._sfida = None
        if rnd_b_ruotato != rnd_b[1:] + rnd_b[:1]:
            return b"\x91\xae"
        ti = os.urandom(4)
        risposta = ti + rnd_a[1:] + rnd_a[:1] + bytes(12)
        enc, mac = self.n.chiavi_di_sessione(chiave, rnd_a, rnd_b)
        self.sessione = self.n.SessioneEV2(enc=enc, mac=mac, ti=ti)
        self.numero_sessione = numero
        return self._cbc(chiave, bytes(16), risposta, True) + b"\x91\x00"

    def _apri_comando(self, codice: int, dati: bytes, lunghezza_testa: int):
        """Verifica firma e decifra un comando Full. None se non va."""
        s = self.sessione
        if s is None:
            return None
        testa, cifrato, firma = (
            dati[:lunghezza_testa],
            dati[lunghezza_testa:-8],
            dati[-8:],
        )
        if s.mac_comando(codice, testa, cifrato) != firma:
            return None
        iv = s._iv(bytes.fromhex("A55A"), 0)
        chiaro = self._cbc(s.enc, iv, cifrato, False)
        return testa, self.n._svuota(chiaro)

    def _risposta_firmata(self) -> bytes:
        s = self.sessione
        firma = s.mac_risposta(0x00, b"")
        s.contatore += 1
        return firma + b"\x91\x00"

    def _impostazioni(self, dati: bytes) -> bytes:
        if self.numero_sessione != 0:
            return b"\x91\x9d"
        aperto = self._apri_comando(0x5F, dati, 1)
        if aperto is None:
            self._chiudi_sessione()
            return b"\x91\x1e"
        _, s = aperto
        self.scrittura_libera = (s[2] & 0x0F) == 0x0E
        self.sdm = {
            "meta": s[5] >> 4,
            "file": s[5] & 0x0F,
            "picc": int.from_bytes(s[6:9], "little"),
            "mac": int.from_bytes(s[12:15], "little"),
        }
        return self._risposta_firmata()

    def _cambia_chiave(self, dati: bytes) -> bytes:
        if self.numero_sessione != 0:
            return b"\x91\x9d"
        aperto = self._apri_comando(0xC4, dati, 1)
        if aperto is None:
            self._chiudi_sessione()
            return b"\x91\x1e"
        testa, chiaro = aperto
        numero = testa[0]
        if numero == self.numero_sessione:
            self.chiavi[numero] = chiaro[:16]
            self.versioni[numero] = chiaro[16]
            self._chiudi_sessione()
            return b"\x91\x00"
        vecchia = self.chiavi[numero]
        nuova = bytes(a ^ b for a, b in zip(chiaro[:16], vecchia, strict=True))
        if self.n.crc32_nxp(nuova) != chiaro[17:21]:
            # La vecchia chiave non era quella: la nuova non torna col suo CRC.
            self._chiudi_sessione()
            return b"\x91\x1e"
        self.chiavi[numero] = nuova
        self.versioni[numero] = chiaro[16]
        return self._risposta_firmata()
