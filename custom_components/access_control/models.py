"""Modello dati di Controllo Accessi."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    CARD_ACTIVE,
    SECURITY_UNKNOWN,
    TECH_ISO14443A_7B,
    TECH_MIFARE_CLASSIC,
    TECH_UNKNOWN,
    TECHNOLOGY_LABELS,
    TECHNOLOGY_SECURITY,
)


def _now_iso() -> str:
    return dt_util.utcnow().isoformat()


def normalize_uid(raw: str | None) -> str:
    """Porta un UID alla forma canonica del registro.

    I lettori scrivono lo stesso UID in modi diversi — maiuscolo o minuscolo,
    separato da trattini, da due punti, da spazi, o tutto attaccato.
    Confrontare le forme grezze farebbe risultare "non censita" una tessera
    che è nel registro, e quel diniego sarebbe indistinguibile da uno
    legittimo: un bug del genere si manifesta solo come "a volte non apre",
    che è fra le cose più difficili da diagnosticare su un impianto.

    Perciò non basta uniformare i separatori: vanno **tolti tutti** e poi
    rimessi a passo fisso, così `04A1B2C3` e `04-a1-b2-c3` finiscono sulla
    stessa riga del registro.

    Un UID che non è esadecimale (lettore che manda un identificativo suo)
    viene solo ripulito e messo in maiuscolo, senza raggrupparlo: raggruppare
    a due a due qualcosa che non sono byte lo renderebbe solo illeggibile.
    """
    if not raw:
        return ""

    cleaned = str(raw).strip().upper()
    for junk in (":", " ", "_", "-"):
        cleaned = cleaned.replace(junk, "")
    if not cleaned:
        return ""

    is_hex = all(c in "0123456789ABCDEF" for c in cleaned)
    if is_hex and len(cleaned) % 2 == 0:
        return "-".join(
            cleaned[i : i + 2] for i in range(0, len(cleaned), 2)
        )
    return cleaned


def uid_bytes(uid: str) -> int:
    """Quanti byte ha l'UID."""
    return len(uid.replace("-", "")) // 2


def detect_technology(uid: str) -> str:
    """Riconosce la famiglia della tessera dal solo UID.

    Chi compra le tessere non sa che chip ci sia dentro, quindi la tecnologia
    va rilevata e non chiesta. L'unico dato che il PN532 via ESPHome fornisce
    è l'UID — niente SAK, niente ATQA — ma la sua lunghezza è normata da
    ISO/IEC 14443-3 e distingue le due famiglie:

    - **4 byte** (single size): MIFARE Classic 1K/4K. UID clonabile.
    - **7 byte** (double size): Ultralight, NTAG21x, NTAG424, DESFire. Quale
      dei quattro non è distinguibile senza SAK.

    Che non si distinguano fra loro non è però un problema, perché **oggi
    contano tutte uguale**: senza verifica del cryptogram, un NTAG424 di cui
    leggiamo solo l'UID si clona esattamente come una Classic. La distinzione
    fra 4 e 7 byte serve a dare un'etichetta onesta a chi guarda il registro,
    non ad assegnare permessi diversi.

    Il livello di sicurezza lo decide `TECHNOLOGY_SECURITY`, e nessuno dei due
    esiti di questa funzione vale `forte`: ci si arriva solo verificando
    davvero qualcosa, non riconoscendo un formato.
    """
    n = uid_bytes(uid)
    if n == 4:
        return TECH_MIFARE_CLASSIC
    if n in (7, 10):
        return TECH_ISO14443A_7B
    return TECH_UNKNOWN


@dataclass
class Card:
    """Una credenziale censita nel registro."""

    uid: str
    name: str = ""
    person: str = ""
    technology: str = TECH_UNKNOWN
    state: str = CARD_ACTIVE
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = field(default_factory=_now_iso)
    last_used: str | None = None
    uses: int = 0
    note: str = ""

    @property
    def security(self) -> str:
        """Livello di sicurezza derivato dalla tecnologia rilevata."""
        return TECHNOLOGY_SECURITY.get(self.technology, SECURITY_UNKNOWN)

    @property
    def technology_label(self) -> str:
        return TECHNOLOGY_LABELS.get(self.technology, self.technology)

    @property
    def label(self) -> str:
        """Etichetta leggibile per log e notifiche."""
        return self.name or f"tessera {self.uid[-5:]}"

    def register_use(self) -> None:
        self.uses += 1
        self.last_used = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "uid": self.uid,
            "name": self.name,
            "person": self.person,
            "technology": self.technology,
            "state": self.state,
            "created": self.created,
            "last_used": self.last_used,
            "uses": self.uses,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Card:
        card = cls(
            uid=normalize_uid(data.get("uid")),
            name=data.get("name", ""),
            person=data.get("person", ""),
            technology=data.get("technology", TECH_UNKNOWN),
            state=data.get("state", CARD_ACTIVE),
            note=data.get("note", ""),
        )
        if data.get("id"):
            card.id = data["id"]
        if data.get("created"):
            card.created = data["created"]
        card.last_used = data.get("last_used")
        card.uses = int(data.get("uses") or 0)
        return card


@dataclass
class AccessEvent:
    """Una riga del registro accessi.

    Viene emessa sul bus e conservata nello store. Le due copie servono a cose
    diverse: il bus fa reagire le automazioni adesso, lo store risponde alla
    domanda "chi è entrato martedì scorso" — a cui il recorder, che si
    autocancella dopo pochi giorni, non risponde.
    """

    result: str
    uid: str = ""
    card_id: str | None = None
    card_name: str = ""
    card_state: str = ""
    card_security: str = ""
    person: str = ""
    role: str = ""
    gate: str = ""
    system_state: str = ""
    reason: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "esito": self.result,
            "motivo": self.reason,
            "uid": self.uid,
            "card_id": self.card_id,
            "card_nome": self.card_name,
            "card_stato": self.card_state,
            "card_sicurezza": self.card_security,
            "person": self.person,
            "ruolo": self.role,
            "varco": self.gate,
            "stato_sistema": self.system_state,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessEvent:
        return cls(
            result=data.get("esito", ""),
            reason=data.get("motivo", ""),
            uid=data.get("uid", ""),
            card_id=data.get("card_id"),
            card_name=data.get("card_nome", ""),
            card_state=data.get("card_stato", ""),
            card_security=data.get("card_sicurezza", ""),
            person=data.get("person", ""),
            role=data.get("ruolo", ""),
            gate=data.get("varco", ""),
            system_state=data.get("stato_sistema", ""),
            timestamp=data.get("timestamp") or _now_iso(),
        )

    @property
    def when(self) -> datetime | None:
        return dt_util.parse_datetime(self.timestamp)
