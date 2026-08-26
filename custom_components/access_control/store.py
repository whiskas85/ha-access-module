"""Persistenza di Controllo Accessi: impostazioni, registro tessere, varchi, log."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CARD_ACTIVE,
    CARD_BLACKLISTED,
    CARD_DISABLED,
    CONF_CARDS,
    CONF_GATES,
    CONF_LOG,
    CONF_SETTINGS,
    DEFAULT_GATE,
    DEFAULT_SETTINGS,
    RESULT_BLACKLIST,
    RESULT_DENIED,
    RESULT_LOCKOUT,
    ROLE_ADULT,
    SIGNAL_STATE_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .models import AccessEvent, Card, detect_technology, normalize_uid

_LOGGER = logging.getLogger(__name__)


class AccessStore:
    """Stato condiviso fra entità, pannello e motore di valutazione."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.cards: dict[str, Card] = {}
        self.gates: dict[str, dict[str, Any]] = {}
        self.log: list[AccessEvent] = []
        # Stato corrente della macchina a stati, scritto dal coordinator.
        self.system_state: str = ""
        self.state_reason: str = ""
        # Lockout
        self.failure_streak: int = 0
        self.locked_until: str | None = None
        # Enrollment: non persistito di proposito. Una modalità che accetta
        # tessere nuove non deve sopravvivere a un riavvio — se Home Assistant
        # riparte mentre è aperta, deve ripartire chiusa.
        self.enrollment_until = None
        # Su QUALE lettore si sta censendo. Con più varchi, aprire il
        # censimento su tutti significherebbe che una tessera passata al
        # garage mentre stai censendo all'ingresso finisce nel registro senza
        # che nessuno l'abbia voluta. Una lettura da un altro varco viene
        # valutata normalmente.
        self.enrollment_gate: str = ""

    # ── caricamento e salvataggio ──────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}

        # Le impostazioni vanno fuse con i default, non sostituite: un
        # aggiornamento che aggiunge una chiave non deve lasciare `None` in
        # giro per le installazioni esistenti.
        stored_settings = data.get(CONF_SETTINGS) or {}
        self.settings = {**DEFAULT_SETTINGS, **stored_settings}

        self.cards = {}
        for raw in data.get(CONF_CARDS) or []:
            try:
                card = Card.from_dict(raw)
            except (TypeError, ValueError):
                _LOGGER.warning("Tessera illeggibile nello store, ignorata: %s", raw)
                continue
            if card.uid:
                self.cards[card.id] = card

        gates = data.get(CONF_GATES) or []
        self.gates = {g["id"]: g for g in gates if g.get("id")}
        if not self.gates:
            self.gates = {DEFAULT_GATE["id"]: dict(DEFAULT_GATE)}

        self.log = [AccessEvent.from_dict(r) for r in (data.get(CONF_LOG) or [])]

        lockout = data.get("lockout") or {}
        self.failure_streak = int(lockout.get("failure_streak") or 0)
        self.locked_until = lockout.get("locked_until")

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                CONF_SETTINGS: self.settings,
                CONF_CARDS: [c.to_dict() for c in self.cards.values()],
                CONF_GATES: list(self.gates.values()),
                CONF_LOG: [e.to_dict() for e in self.log],
                "lockout": {
                    "failure_streak": self.failure_streak,
                    "locked_until": self.locked_until,
                },
            }
        )

    async def async_save_and_notify(self) -> None:
        await self.async_save()
        self.notify()

    def notify(self) -> None:
        """Sveglia le entità: pannello e entità leggono lo stesso stato."""
        async_dispatcher_send(self.hass, SIGNAL_STATE_CHANGED)

    # ── impostazioni ───────────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        self.settings.update(changes)
        await self.async_save_and_notify()

    def role_of(self, person: str) -> str:
        """Ruolo del titolare.

        Un titolare non mappato è trattato come adulto: il ruolo bambino è
        quello con i permessi più stretti e più specifici, e assegnarlo per
        omissione trasformerebbe una dimenticanza di configurazione in un
        diniego silenzioso durante la finestra scuola.
        """
        roles = self.settings.get("person_roles") or {}
        return roles.get(person) or ROLE_ADULT

    # ── registro tessere ───────────────────────────────────────────────────

    def card_by_uid(self, uid: str) -> Card | None:
        target = normalize_uid(uid)
        if not target:
            return None
        for card in self.cards.values():
            if card.uid == target:
                return card
        return None

    def card_by_id(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    async def async_add_card(
        self,
        uid: str,
        name: str = "",
        person: str = "",
        technology: str = "",
        note: str = "",
    ) -> Card:
        """Censisce una tessera. Se l'UID esiste già ne aggiorna i dati.

        La tecnologia, se non passata, viene rilevata dall'UID: è il caso
        normale: chi censisce non deve doverla sapere.

        L'UID è la chiave logica: due righe con lo stesso UID renderebbero il
        risultato della valutazione dipendente dall'ordine di iterazione.
        """
        normalized = normalize_uid(uid)
        if not normalized:
            raise ValueError("UID vuoto")

        rilevata = technology or detect_technology(normalized)

        existing = self.card_by_uid(normalized)
        if existing is not None:
            existing.name = name or existing.name
            existing.person = person or existing.person
            existing.technology = technology or existing.technology
            existing.note = note or existing.note
            await self.async_save_and_notify()
            return existing

        card = Card(
            uid=normalized,
            name=name or f"Tessera {normalized[-5:]}",
            person=person,
            technology=rilevata,
            note=note,
        )
        self.cards[card.id] = card
        await self.async_save_and_notify()
        return card

    async def async_assign_person(self, card_id: str, person: str) -> Card:
        """Abbina (o stacca, con person vuoto) una tessera a un titolare."""
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.person = person or ""
        await self.async_save_and_notify()
        return card

    # ── enrollment ─────────────────────────────────────────────────────────

    @property
    def enrollment_active(self) -> bool:
        if not self.enrollment_until:
            return False
        return dt_util.utcnow() < self.enrollment_until

    @property
    def enrollment_seconds_left(self) -> int:
        if not self.enrollment_active:
            return 0
        return max(
            0, int((self.enrollment_until - dt_util.utcnow()).total_seconds())
        )

    def start_enrollment(self, seconds: int, gate_id: str = "") -> None:
        self.enrollment_gate = gate_id or next(iter(self.gates), "")
        self.enrollment_until = dt_util.utcnow() + timedelta(seconds=seconds)
        self.notify()

    def cancel_enrollment(self) -> None:
        self.enrollment_until = None
        self.enrollment_gate = ""
        self.notify()

    def enrollment_accepts(self, gate_id: str) -> bool:
        """Questa lettura va censita, o valutata normalmente?"""
        if not self.enrollment_active:
            return False
        return not self.enrollment_gate or self.enrollment_gate == gate_id

    async def async_update_card(self, card_id: str, changes: dict[str, Any]) -> Card:
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)

        for key in ("name", "person", "technology", "note"):
            if key in changes:
                setattr(card, key, changes[key])
        if "uid" in changes:
            new_uid = normalize_uid(changes["uid"])
            clash = self.card_by_uid(new_uid)
            if new_uid and clash is not None and clash.id != card.id:
                raise ValueError(f"UID già assegnato a {clash.label}")
            card.uid = new_uid or card.uid
        if "state" in changes:
            await self.async_set_card_state(card_id, changes["state"], save=False)

        await self.async_save_and_notify()
        return card

    async def async_set_card_state(
        self, card_id: str, state: str, *, save: bool = True
    ) -> Card:
        """Attiva / disabilita / mette in blacklist una tessera.

        Disabilitata e blacklist sono cose diverse di proposito: una tessera
        riposta in un cassetto non deve generare allarmi quando qualcuno la
        prova, una tessera persa sì.
        """
        if state not in (CARD_ACTIVE, CARD_DISABLED, CARD_BLACKLISTED):
            raise ValueError(f"Stato tessera non valido: {state}")
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.state = state
        if save:
            await self.async_save_and_notify()
        return card

    async def async_remove_card(self, card_id: str) -> None:
        """Elimina una tessera dal registro.

        Dopo l'eliminazione una lettura di quell'UID risulta "sconosciuta" e
        non allarma. Se la tessera è stata persa la scelta giusta è la
        blacklist, non l'eliminazione.
        """
        if self.cards.pop(card_id, None) is not None:
            await self.async_save_and_notify()

    # ── varchi ─────────────────────────────────────────────────────────────

    def gate(self, gate_id: str) -> dict[str, Any] | None:
        return self.gates.get(gate_id)

    async def async_upsert_gate(self, gate: dict[str, Any]) -> dict[str, Any]:
        gate_id = gate.get("id")
        if not gate_id:
            raise ValueError("Varco senza id")
        current = self.gates.get(gate_id, dict(DEFAULT_GATE))
        current = {**current, **gate}
        self.gates[gate_id] = current
        await self.async_save_and_notify()
        return current

    async def async_remove_gate(self, gate_id: str) -> None:
        if self.gates.pop(gate_id, None) is not None:
            await self.async_save_and_notify()

    # ── lockout ────────────────────────────────────────────────────────────

    @property
    def is_locked_out(self) -> bool:
        if not self.locked_until:
            return False
        until = dt_util.parse_datetime(self.locked_until)
        if until is None:
            return False
        return dt_util.utcnow() < until

    async def async_register_failure(self) -> int:
        self.failure_streak += 1
        await self.async_save_and_notify()
        return self.failure_streak

    async def async_reset_failures(self) -> None:
        if self.failure_streak or self.locked_until:
            self.failure_streak = 0
            self.locked_until = None
            await self.async_save_and_notify()

    async def async_lock_readers(self, minutes: int) -> None:
        self.locked_until = (dt_util.utcnow() + timedelta(minutes=minutes)).isoformat()
        await self.async_save_and_notify()

    async def async_unlock_readers(self) -> None:
        self.locked_until = None
        self.failure_streak = 0
        await self.async_save_and_notify()

    # ── log accessi ────────────────────────────────────────────────────────

    async def async_append_log(self, event: AccessEvent) -> None:
        self.log.insert(0, event)
        cap = int(self.settings.get("log_max_entries") or 500)
        if len(self.log) > cap:
            del self.log[cap:]
        await self.async_save_and_notify()

    async def async_clear_log(self) -> None:
        self.log = []
        await self.async_save_and_notify()

    def denied_today(self) -> int:
        """Quanti tentativi sono stati rifiutati oggi.

        Si contano solo i rifiuti veri. Un censimento non è un tentativo di
        accesso — è un'operazione voluta, che al lettore risponde `ok` — e
        contarlo qui gonfierebbe le statistiche proprio nel momento in cui si
        sta configurando il sistema, cioè quando quel numero viene guardato di
        più. Per lo stesso motivo si elenca cosa conta invece di negare tutto
        ciò che non è `granted`: un esito nuovo non deve finire fra i rifiuti
        per il solo fatto di essere nuovo.
        """
        rifiuti = (RESULT_DENIED, RESULT_BLACKLIST, RESULT_LOCKOUT)
        today = dt_util.now().date()
        count = 0
        for event in self.log:
            when = event.when
            if when is None:
                continue
            if dt_util.as_local(when).date() != today:
                # Il log è ordinato dal più recente: appena si scende sotto
                # oggi non c'è più nulla da contare.
                break
            if event.result in rifiuti:
                count += 1
        return count
