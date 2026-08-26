"""Macchina a stati di Controllo Accessi.

Unica proprietaria di `store.system_state`. Nessun altro modulo lo scrive.
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
    STATE_ADULT_RETURN,
    STATE_OCCUPIED,
    STATE_SCHOOL,
    STATE_SLEEP,
)
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

# La rete di sicurezza: se un listener di stato si perde, entro un minuto la
# macchina si riallinea comunque. La finestra scuola ha risoluzione al minuto,
# quindi più fitto di così non servirebbe a niente.
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
    """Calcola lo stato del sistema e lo tiene aggiornato."""

    def __init__(self, hass: HomeAssistant, store: AccessStore) -> None:
        self.hass = hass
        self.store = store
        # Momento in cui l'ultima persona è stata vista in casa. È ciò che
        # implementa il ritardo di ritorno a sleep: la casa non è "vuota"
        # nell'istante in cui l'ultimo se ne va.
        self._last_presence: Any = None

    # ── ciclo di vita ──────────────────────────────────────────────────────

    def async_start(self) -> CALLBACK_TYPE:
        """Avvia gli osservatori. Ritorna la funzione per fermarli."""
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
            entity_id = settings.get(key)
            if entity_id:
                entities.append(entity_id)
        return entities

    # ── lettura dell'impianto ──────────────────────────────────────────────

    @property
    def master_on(self) -> bool:
        return bool(self.store.settings.get("master", True))

    def anyone_home(self) -> bool:
        persons = self.store.settings.get("person_entities") or []
        return any(
            (state := self.hass.states.get(entity)) is not None
            and state.state == "home"
            for entity in persons
        )

    def presence_recent(self) -> bool:
        """Presenza, con il ritardo di ritorno a sleep già applicato."""
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
            if self.store.role_of(entity) != "adulto":
                continue
            if state.state == zone_name:
                return True
        return False

    def school_window_active(self) -> bool:
        settings = self.store.settings
        now = dt_util.now()
        if now.weekday() not in (settings.get("school_days") or []):
            return False
        start = _parse_hhmm(settings.get("school_start"), time(15, 30))
        end = _parse_hhmm(settings.get("school_end"), time(16, 30))
        current = now.time()
        if start <= end:
            return start <= current <= end
        # Finestra che scavalca la mezzanotte.
        return current >= start or current <= end

    def door_status(self) -> str:
        """Incrocia due fonti indipendenti: serratura e contatto sull'anta.

        Anta chiusa con serratura sbloccata NON è incoerente: è la porta
        accostata ma non mandata in sicurezza, cioè la condizione normale di
        casa abitata. Incoerente è solo l'anta aperta mentre la serratura
        dichiara chiusa a chiave — fisicamente impossibile, quindi guasto o
        forzamento.
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

    # ── calcolo dello stato ────────────────────────────────────────────────

    def compute_state(self) -> tuple[str, str]:
        """Ritorna (stato, motivo leggibile). Priorità decrescente."""
        if not self.master_on:
            return STATE_SLEEP, "Master accessi spento"

        if self.presence_recent():
            return STATE_OCCUPIED, "Casa occupata: presenza rilevata"

        if self.adult_nearby():
            return STATE_ADULT_RETURN, "Rientro adulto: qualcuno in avvicinamento"

        if self.school_window_active():
            end = self.store.settings.get("school_end", "")
            return STATE_SCHOOL, f"Finestra scuola attiva fino alle {end}"

        return STATE_SLEEP, "Sleep: fuori finestra scuola, nessuno in avvicinamento"

    @property
    def is_armed(self) -> bool:
        """Il sistema accetterebbe una credenziale in questo momento."""
        return self.master_on and self.store.system_state != STATE_SLEEP

    @callback
    def async_refresh(self) -> None:
        state, reason = self.compute_state()
        previous = self.store.system_state
        self.store.system_state = state
        self.store.state_reason = reason
        if previous and previous != state:
            _LOGGER.debug("Stato accessi %s -> %s (%s)", previous, state, reason)

        # Si notifica a ogni giro, non solo quando lo stato cambia: alcune
        # entità dipendono dallo scorrere del tempo e non da una transizione —
        # "porta socchiusa" diventa vero perché sono passati cinque minuti,
        # non perché è cambiato qualcosa. Notificando solo sui cambi di stato
        # resterebbero ferme finché non si muove qualcos'altro.
        self.store.notify()
