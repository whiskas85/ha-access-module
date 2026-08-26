"""Macchina di AUTORIZZAZIONE: chi può entrare adesso.

Non decide se c'è un allarme in corso — quella è l'altra macchina, che sta nel
motore di valutazione. Qui si risponde solo a "in questo momento, quali ruoli
sono ammessi e su quali lettori".
"""

from __future__ import annotations

import logging
from datetime import time, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    ROLE_ADULT,
    ROLE_CHILD,
    STATE_CLOSED,
    STATE_OPEN,
)
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

# La rete di sicurezza: se un listener di stato si perde, entro un minuto la
# macchina si riallinea comunque. Le finestre hanno risoluzione al minuto,
# quindi più fitto non servirebbe a niente.
TICK = timedelta(minutes=1)

DOOR_CLOSED = "chiusa"
DOOR_OPEN = "aperta"
DOOR_OPENING = "in_apertura"
DOOR_FAULT = "errore"
DOOR_INCONSISTENT = "incoerente"
DOOR_UNKNOWN = "sconosciuto"

_UNAVAILABLE = ("unknown", "unavailable", "", None)


def _parse_hhmm(raw: str, fallback: time) -> time:
    try:
        hours, _, minutes = str(raw).partition(":")
        return time(int(hours), int(minutes or 0))
    except (TypeError, ValueError):
        return fallback


class AccessCoordinator:
    """Calcola chi è ammesso adesso, e lo tiene aggiornato."""

    def __init__(self, hass: HomeAssistant, store: AccessStore) -> None:
        self.hass = hass
        self.store = store
        self._last_presence: Any = None

    # ── ciclo di vita ──────────────────────────────────────────────────────

    def async_start(self) -> CALLBACK_TYPE:
        unsubs: list[CALLBACK_TYPE] = []

        @callback
        def _on_change(_event: Event) -> None:
            self.async_refresh()

        watched = self._watched_entities()
        if watched:
            unsubs.append(
                async_track_state_change_event(self.hass, watched, _on_change)
            )

        @callback
        def _on_tick(_now) -> None:
            self.async_refresh()

        unsubs.append(async_track_time_interval(self.hass, _on_tick, TICK))
        self.async_refresh()

        @callback
        def _stop() -> None:
            for unsub in unsubs:
                unsub()

        return _stop

    def _watched_entities(self) -> list[str]:
        settings = self.store.settings
        entities = list(settings.get("person_entities") or [])
        for key in ("door_lock_entity", "door_contact_entity"):
            if entity_id := settings.get(key):
                entities.append(entity_id)
        return entities

    # ── lettura dell'impianto ──────────────────────────────────────────────

    @property
    def master_on(self) -> bool:
        return bool(self.store.settings.get("master", True))

    def anyone_home(self) -> bool:
        return any(
            (state := self.hass.states.get(entity)) is not None
            and state.state == "home"
            for entity in (self.store.settings.get("person_entities") or [])
        )

    def presence_recent(self) -> bool:
        """Presenza, con il ritardo di ritorno a chiuso già applicato."""
        if self.anyone_home():
            self._last_presence = dt_util.utcnow()
            return True
        if self._last_presence is None:
            return False
        delay = int(self.store.settings.get("sleep_delay_min") or 10)
        return dt_util.utcnow() - self._last_presence < timedelta(minutes=delay)

    def adult_nearby(self) -> bool:
        """Un adulto è dentro la zona di avvicinamento.

        Lo stato di una `person` dentro una zona è il *nome* della zona, non
        il suo entity_id: confrontare con `zone.vicinanze` non troverebbe mai
        nulla, e il rientro adulto non scatterebbe mai.
        """
        zone_entity = self.store.settings.get("nearby_zone")
        if not zone_entity:
            return False
        zone = self.hass.states.get(zone_entity)
        if zone is None:
            return False
        zone_name = zone.attributes.get("friendly_name") or zone_entity

        for entity in self.store.settings.get("person_entities") or []:
            state = self.hass.states.get(entity)
            if state is None or state.state == "home":
                continue
            if self.store.role_of(entity) != ROLE_ADULT:
                continue
            if state.state == zone_name:
                return True
        return False

    # ── finestre ───────────────────────────────────────────────────────────

    def window_active(self, window: dict[str, Any]) -> bool:
        if not window.get("enabled", True):
            return False
        now = dt_util.now()
        if now.weekday() not in (window.get("days") or []):
            return False
        start = _parse_hhmm(window.get("start"), time(0, 0))
        end = _parse_hhmm(window.get("end"), time(23, 59))
        current = now.time()
        if start <= end:
            return start <= current <= end
        # Finestra che scavalca la mezzanotte.
        return current >= start or current <= end

    def active_windows(self) -> list[dict[str, Any]]:
        if not self.master_on:
            return []
        return [w for w in self.store.windows.values() if self.window_active(w)]

    def allows(self, role: str, device_id: str) -> tuple[bool, str]:
        """Questo ruolo può entrare adesso da questo lettore?

        Ritorna (ammesso, nome della finestra o della regola che lo ammette).
        Le opzioni di presenza si SOMMANO alle finestre: sono scorciatoie per
        i casi che valgono sempre, non regole che le scavalcano.
        """
        if not self.master_on or not role:
            return False, ""

        for window in self.active_windows():
            if role not in (window.get("roles") or []):
                continue
            consentiti = window.get("devices") or []
            if consentiti and device_id not in consentiti:
                continue
            return True, window.get("name") or window.get("id", "")

        settings = self.store.settings
        if settings.get("presence_opens_all") and self.presence_recent():
            return True, "casa occupata"
        if (
            settings.get("nearby_opens_adults")
            and role == ROLE_ADULT
            and self.adult_nearby()
        ):
            return True, "adulto in avvicinamento"

        return False, ""

    def open_roles(self) -> list[str]:
        """Quali ruoli sono ammessi adesso, da almeno un lettore."""
        ruoli = []
        for role in (ROLE_CHILD, ROLE_ADULT):
            ammesso, _ = self.allows(role, "")
            if ammesso:
                ruoli.append(role)
        return ruoli

    # ── porta ──────────────────────────────────────────────────────────────

    def door_status(self) -> str:
        """Incrocia due fonti indipendenti: serratura e contatto sull'anta.

        Anta chiusa con serratura sbloccata NON è incoerente: è la porta
        accostata ma non mandata in sicurezza, cioè la condizione normale di
        casa abitata. Incoerente è solo l'anta aperta mentre la serratura
        dichiara chiusa a chiave — fisicamente impossibile.
        """
        settings = self.store.settings
        lock_id = settings.get("door_lock_entity")
        contact_id = settings.get("door_contact_entity")
        if not lock_id or not contact_id:
            return DOOR_UNKNOWN

        lock = self.hass.states.get(lock_id)
        contact = self.hass.states.get(contact_id)
        if lock is None or contact is None:
            return DOOR_UNKNOWN
        if lock.state in _UNAVAILABLE or contact.state in _UNAVAILABLE:
            return DOOR_UNKNOWN
        if lock.state == "jammed":
            return DOOR_FAULT
        if lock.state in ("opening", "unlocking", "locking"):
            return DOOR_OPENING

        anta_aperta = contact.state == "on"
        if anta_aperta and lock.state == "locked":
            return DOOR_INCONSISTENT
        return DOOR_OPEN if anta_aperta else DOOR_CLOSED

    # ── stato complessivo ──────────────────────────────────────────────────

    def compute_state(self) -> tuple[str, str]:
        """Ritorna (stato, motivo leggibile)."""
        if not self.master_on:
            return STATE_CLOSED, "Master accessi spento"

        ruoli = self.open_roles()
        if not ruoli:
            return STATE_CLOSED, "Nessuna finestra attiva in questo momento"

        finestre = [w.get("name") or w["id"] for w in self.active_windows()]
        if finestre:
            elenco = ", ".join(finestre)
            ammessi = ", ".join(ruoli)
            return STATE_OPEN, f"Finestra attiva: {elenco} — ammessi: {ammessi}"
        return STATE_OPEN, f"Ammessi: {', '.join(ruoli)} (presenza in casa)"

    @property
    def is_open(self) -> bool:
        return self.store.system_state == STATE_OPEN

    @callback
    def async_refresh(self) -> None:
        state, reason = self.compute_state()
        previous = self.store.system_state
        self.store.system_state = state
        self.store.state_reason = reason
        if previous and previous != state:
            _LOGGER.debug("Autorizzazione %s -> %s (%s)", previous, state, reason)

        # Si notifica a ogni giro, non solo quando lo stato cambia: alcune
        # entità dipendono dallo scorrere del tempo e non da una transizione —
        # "porta socchiusa" diventa vero perché sono passati cinque minuti.
        self.store.notify()
