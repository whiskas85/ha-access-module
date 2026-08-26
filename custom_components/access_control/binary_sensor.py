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

from .const import ALARM_LABELS, DOMAIN
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]
    async_add_entities(
        [
            AccessArmedSensor(entry.entry_id, store, coordinator),
            AccessWindowSensor(entry.entry_id, store, coordinator),
            AccessPresenceSensor(entry.entry_id, store, coordinator),
            AccessAdultNearbySensor(entry.entry_id, store, coordinator),
            AccessDoorAjarSensor(entry.entry_id, store, coordinator),
            AccessAlarmSensor(entry.entry_id, store, coordinator),
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
        # Armato = una finestra ammette qualcuno E non siamo in allarme.
        # Sono le due macchine a stati messe insieme, ed è l'unico posto dove
        # ha senso farlo: qui la domanda è "adesso aprirebbe?".
        return self.coordinator.is_open and not self.store.in_alarm


class AccessWindowSensor(AccessEntity, BinarySensorEntity):
    _attr_name = "Finestra attiva"
    _attr_icon = "mdi:school"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_window"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.active_windows())


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


class AccessAlarmSensor(AccessEntity, BinarySensorEntity):
    """Sistema in allarme: i lettori sono spenti finché non si sblocca."""

    _attr_name = "Allarme"
    _attr_icon = "mdi:shield-alert"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_alarm"

    @property
    def is_on(self) -> bool:
        return self.store.in_alarm

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "motivo": ALARM_LABELS.get(
                self.store.alarm_reason, self.store.alarm_reason
            ),
            "dal": self.store.alarm_since,
            "fallimenti_consecutivi": self.store.failure_streak,
            "soglia": self.store.settings.get("alarm_threshold"),
        }
