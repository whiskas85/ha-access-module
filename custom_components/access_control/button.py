"""Pulsanti di Controllo Accessi."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ENROLLMENT_TIMEOUT_S
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]
    # Un pulsante per varco: con più lettori, "abilita lettura" senza dire
    # quale non è un'istruzione completa.
    entities: list[AccessEntity] = [
        AccessStartEnrollmentButton(entry.entry_id, store, coordinator, gate_id, gate)
        for gate_id, gate in store.gates.items()
    ]
    entities += [
        AccessUnlockReadersButton(entry.entry_id, store, coordinator),
        AccessClearLogButton(entry.entry_id, store, coordinator),
    ]
    async_add_entities(entities)


class AccessStartEnrollmentButton(AccessEntity, ButtonEntity):
    """Apre la finestra di censimento su un varco, senza passare dal pannello."""

    _attr_icon = "mdi:card-plus"

    def __init__(self, entry_id, store, coordinator, gate_id, gate) -> None:
        super().__init__(entry_id, store, coordinator)
        self._gate_id = gate_id
        self._attr_name = f"Abilita lettura tessera — {gate.get('name') or gate_id}"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_start_enrollment_{self._gate_id}"

    async def async_press(self) -> None:
        self.store.start_enrollment(ENROLLMENT_TIMEOUT_S, self._gate_id)


class AccessUnlockReadersButton(AccessEntity, ButtonEntity):
    """Sblocca i lettori dopo un lockout, senza aspettare la scadenza."""

    _attr_name = "Sblocca lettori"
    _attr_icon = "mdi:lock-open-check"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_unlock_readers"

    @property
    def available(self) -> bool:
        return self.store.is_locked_out or self.store.failure_streak > 0

    async def async_press(self) -> None:
        await self.store.async_unlock_readers()


class AccessClearLogButton(AccessEntity, ButtonEntity):
    """Svuota il registro accessi.

    Separato dal pannello di proposito: cancellare un registro accessi è
    un'azione che va lasciata tracciabile in logbook, non nascosta in un menu.
    """

    _attr_name = "Svuota registro accessi"
    _attr_icon = "mdi:notebook-remove"
    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_clear_log"

    async def async_press(self) -> None:
        await self.store.async_clear_log()
