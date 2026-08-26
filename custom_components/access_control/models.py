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
    TECH_UNKNOWN,
    TECHNOLOGY_SECURITY,
)


def _now_iso() -> str:
    return dt_util.utcnow().isoformat()


def normalize_uid(raw: str | None) -> str:
    """Porta un UID alla forma canonica del registro.

    I lettori scrivono lo stesso UID in modi diversi — maiuscolo o minuscolo,
    con trattini, con due punti, o attaccato. Confrontare le forme grezze
    farebbe risultare "non censita" una tessera che è nel registro, e il
    diniego sarebbe indistinguibile da quello legittimo: un bug del genere si
    manifesterebbe solo come "a volte non apre".
    """
    if not raw:
        return ""
    cleaned = str(raw).strip().upper()
    for junk in (":", " ", "_"):
        cleaned = cleaned.replace(junk, "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


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
        """Livello di sicurezza derivato dalla tecnologia dichiarata."""
        return TECHNOLOGY_SECURITY.get(self.technology, SECURITY_UNKNOWN)

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
