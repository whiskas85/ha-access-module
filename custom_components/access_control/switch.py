"""Interruttore master di Controllo Accessi."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AccessEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    async_add_entities(
        [AccessMasterSwitch(entry.entry_id, data["store"], data["coordinator"])]
    )


class AccessMasterSwitch(AccessEntity, SwitchEntity):
    """Abilitazione generale del modulo.

    A master spento la macchina a stati va in `sleep` e nessuna credenziale
    apre: resta però tutta la tracciatura, perché sapere che qualcuno ha
    provato una tessera mentre il sistema era spento è esattamente il genere
    di cosa che si vuole ritrovare nel registro.
    """

    _attr_name = "Master accessi"
    _attr_icon = "mdi:shield-key"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_master"

    @property
    def is_on(self) -> bool:
        return bool(self.store.settings.get("master", True))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        await self.store.async_update_settings({"master": value})
        self.coordinator.async_refresh()
