"""Sensori di Controllo Accessi.

Espongono cosa farebbe il sistema adesso e perché, così la logica è
ispezionabile senza aprire il pannello né leggere il codice.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, RESULT_GRANTED
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]
    async_add_entities(
        [
            AccessStateSensor(entry.entry_id, store, coordinator),
            AccessReasonSensor(entry.entry_id, store, coordinator),
            AccessDoorSensor(entry.entry_id, store, coordinator),
            AccessLastEntrySensor(entry.entry_id, store, coordinator),
            AccessDeniedTodaySensor(entry.entry_id, store, coordinator),
            AccessCardCountSensor(entry.entry_id, store, coordinator),
        ]
    )


class AccessStateSensor(AccessEntity, SensorEntity):
    _attr_name = "Stato"
    _attr_icon = "mdi:state-machine"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_state"

    @property
    def native_value(self) -> str:
        return self.store.system_state or "sleep"


class AccessReasonSensor(AccessEntity, SensorEntity):
    _attr_name = "Motivo stato"
    _attr_icon = "mdi:help-circle-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_reason"

    @property
    def native_value(self) -> str:
        # Gli stati di un sensore sono limitati a 255 caratteri: un motivo
        # più lungo renderebbe l'entità non valida e sparirebbe del tutto.
        return (self.store.state_reason or "")[:255]


class AccessDoorSensor(AccessEntity, SensorEntity):
    _attr_name = "Stato porta"
    _attr_icon = "mdi:door"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_door"

    @property
    def native_value(self) -> str:
        return self.coordinator.door_status()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        settings = self.store.settings
        return {
            "serratura": settings.get("door_lock_entity") or "non configurata",
            "contatto": settings.get("door_contact_entity") or "non configurato",
        }


class AccessLastEntrySensor(AccessEntity, SensorEntity):
    _attr_name = "Ultimo accesso"
    _attr_icon = "mdi:login"
    _attr_device_class = "timestamp"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_last_entry"

    @property
    def native_value(self):
        for event in self.store.log:
            if event.result == RESULT_GRANTED:
                return event.when
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for event in self.store.log:
            if event.result == RESULT_GRANTED:
                return {
                    "tessera": event.card_name,
                    "titolare": event.person,
                    "varco": event.gate,
                    "stato_sistema": event.system_state,
                }
        return {}


class AccessDeniedTodaySensor(AccessEntity, SensorEntity):
    _attr_name = "Tentativi negati oggi"
    _attr_icon = "mdi:cancel"
    _attr_state_class = "measurement"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_denied_today"

    @property
    def native_value(self) -> int:
        return self.store.denied_today()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "fallimenti_consecutivi": self.store.failure_streak,
            "lettori_bloccati": self.store.is_locked_out,
            "bloccati_fino_a": self.store.locked_until,
        }


class AccessCardCountSensor(AccessEntity, SensorEntity):
    _attr_name = "Tessere censite"
    _attr_icon = "mdi:card-account-details"
    _attr_state_class = "measurement"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_cards"

    @property
    def native_value(self) -> int:
        return len(self.store.cards)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for card in self.store.cards.values():
            counts[card.state] = counts.get(card.state, 0) + 1
        return {
            "attive": counts.get("attiva", 0),
            "disabilitate": counts.get("disabilitata", 0),
            "in_blacklist": counts.get("blacklist", 0),
            "deboli": sum(
                1 for c in self.store.cards.values() if c.security == "debole"
            ),
            "aggiornato": dt_util.now().isoformat(timespec="seconds"),
        }
