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
    async_add_entities(
        [
            AccessStartEnrollmentButton(entry.entry_id, store, coordinator),
            AccessUnlockReadersButton(entry.entry_id, store, coordinator),
            AccessClearLogButton(entry.entry_id, store, coordinator),
        ]
    )


class AccessStartEnrollmentButton(AccessEntity, ButtonEntity):
    """Apre il censimento su un lettore registrato qualsiasi.

    Un'entità per lettore sarebbe sbagliata: i lettori registrati cambiano a
    runtime mentre le entità si creano all'avvio, quindi l'elenco resterebbe
    indietro. Qui basta "apri il censimento"; scegliere su quale lettore, se
    ce n'è più d'uno, è cosa del pannello.
    """

    _attr_name = "Aggiungi tessera"
    _attr_icon = "mdi:card-plus"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_start_enrollment"

    @property
    def available(self) -> bool:
        # Senza lettori registrati non c'è niente che possa leggere.
        return bool(self.store.devices)

    async def async_press(self) -> None:
        self.store.start_enrollment(ENROLLMENT_TIMEOUT_S)


class AccessUnlockReadersButton(AccessEntity, ButtonEntity):
    """Sblocca l'allarme e riaccende i lettori.

    Le due cose insieme, sempre: sbloccare senza riaccendere lascerebbe un
    impianto che si dichiara normale e non legge niente.
    """

    _attr_name = "Sblocca allarme"
    _attr_icon = "mdi:shield-refresh"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_unlock_readers"

    @property
    def available(self) -> bool:
        return self.store.in_alarm or self.store.failure_streak > 0

    async def async_press(self) -> None:
        await self.store.async_clear_alarm()
        evaluator = self.hass.data[DOMAIN].get("evaluator")
        if evaluator is not None:
            await evaluator.async_set_readers_enabled(True)


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
