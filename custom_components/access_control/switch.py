"""Interruttori di Controllo Accessi: master e censimento."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ENROLLMENT_TIMEOUT_S
from .entity import AccessEntity
from .enrollment import EnrollmentManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN]
    async_add_entities(
        [
            AccessMasterSwitch(
                entry.entry_id, data["store"], data["coordinator"]
            ),
            AccessEnrollmentSwitch(
                entry.entry_id,
                data["store"],
                data["coordinator"],
                data["enrollment"],
            ),
        ]
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


class AccessEnrollmentSwitch(AccessEntity, SwitchEntity):
    """Finestra di censimento: aperta o chiusa.

    Un interruttore e non due pulsanti perche' il censimento e' uno *stato*,
    non un comando: dura un minuto, si chiude da solo alla prima tessera e
    puo' essere revocato. Con due pulsanti quello stato non si vedrebbe da
    nessuna parte, e "l'ho aperto o no?" resterebbe una domanda senza
    risposta proprio mentre si e' fuori, davanti al lettore.

    Si spegne da solo: alla prima lettura, allo scadere del minuto, o
    riaprendo il censimento su un altro lettore dal pannello.
    """

    _attr_name = "Censimento tessera"
    _attr_icon = "mdi:card-plus"

    def __init__(
        self,
        entry_id: str,
        store,
        coordinator,
        enrollment: EnrollmentManager,
    ) -> None:
        super().__init__(entry_id, store, coordinator)
        self.enrollment = enrollment

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_enrollment"

    @property
    def available(self) -> bool:
        # Senza lettori registrati non c'e' niente che possa leggere.
        return bool(self.store.devices)

    @property
    def is_on(self) -> bool:
        return self.store.enrollment_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "secondi_rimanenti": self.store.enrollment_seconds_left,
            "lettore": self.store.enrollment_device,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.enrollment.async_start(seconds=ENROLLMENT_TIMEOUT_S)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.enrollment.async_close("interruttore spento")
