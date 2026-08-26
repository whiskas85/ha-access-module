"""Sensori binari di Controllo Accessi."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]
    async_add_entities(
        [
            AccessArmedSensor(entry.entry_id, store, coordinator),
            AccessSchoolWindowSensor(entry.entry_id, store, coordinator),
            AccessPresenceSensor(entry.entry_id, store, coordinator),
            AccessAdultNearbySensor(entry.entry_id, store, coordinator),
            AccessDoorAjarSensor(entry.entry_id, store, coordinator),
            AccessLockoutSensor(entry.entry_id, store, coordinator),
            AccessEnrollmentSensor(entry.entry_id, store, coordinator),
        ]
    )


class AccessArmedSensor(AccessEntity, BinarySensorEntity):
    """Il sensore chiave: accetterei una credenziale in questo momento?"""

    _attr_name = "Sistema armato"
    _attr_icon = "mdi:shield-check"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_armed"

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_armed


class AccessSchoolWindowSensor(AccessEntity, BinarySensorEntity):
    _attr_name = "Finestra scuola attiva"
    _attr_icon = "mdi:school"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_school_window"

    @property
    def is_on(self) -> bool:
        return self.coordinator.school_window_active()


class AccessPresenceSensor(AccessEntity, BinarySensorEntity):
    """Presenza con il ritardo di ritorno a sleep già applicato."""

    _attr_name = "Presenza recente"
    _attr_icon = "mdi:home-account"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_presence"

    @property
    def is_on(self) -> bool:
        return self.coordinator.presence_recent()


class AccessAdultNearbySensor(AccessEntity, BinarySensorEntity):
    _attr_name = "Adulto in avvicinamento"
    _attr_icon = "mdi:map-marker-account"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_adult_nearby"

    @property
    def is_on(self) -> bool:
        return self.coordinator.adult_nearby()


class AccessDoorAjarSensor(AccessEntity, BinarySensorEntity):
    """Porta aperta da più dei minuti configurati."""

    _attr_name = "Porta socchiusa"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_door_ajar"

    @property
    def is_on(self) -> bool:
        contact_id = self.store.settings.get("door_contact_entity")
        if not contact_id:
            return False
        state = self.hass.states.get(contact_id)
        if state is None or state.state != "on":
            return False
        minutes = int(self.store.settings.get("door_ajar_min") or 5)
        return dt_util.utcnow() - state.last_changed >= timedelta(minutes=minutes)


class AccessEnrollmentSensor(AccessEntity, BinarySensorEntity):
    """Finestra di censimento aperta.

    Vale la pena esporlo: mentre è `on` la prossima tessera letta viene
    registrata invece che valutata, ed è uno stato che non deve passare
    inosservato se resta aperto per distrazione.
    """

    _attr_name = "Censimento in corso"
    _attr_icon = "mdi:card-plus"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_enrollment"

    @property
    def is_on(self) -> bool:
        return self.store.enrollment_active

    @property
    def extra_state_attributes(self) -> dict:
        return {"secondi_rimasti": self.store.enrollment_seconds_left}


class AccessLockoutSensor(AccessEntity, BinarySensorEntity):
    _attr_name = "Lettori bloccati"
    _attr_icon = "mdi:lock-alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_lockout"

    @property
    def is_on(self) -> bool:
        return self.store.is_locked_out

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "modalita": self.store.settings.get("lockout_mode"),
            "fallimenti_consecutivi": self.store.failure_streak,
            "fino_a": self.store.locked_until,
        }
