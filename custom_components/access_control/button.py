"""Pulsanti di Controllo Accessi."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]
    async_add_entities(
        [
            AccessUnlockReadersButton(entry.entry_id, store, coordinator),
            AccessClearLogButton(entry.entry_id, store, coordinator),
        ]
    )


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
