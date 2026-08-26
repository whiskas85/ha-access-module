"""Base comune alle entità di Controllo Accessi."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, PANEL_URL, SIGNAL_STATE_CHANGED
from .coordinator import AccessCoordinator
from .store import AccessStore

MANUFACTURER = "Controllo Accessi"


def system_device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_system")},
        name="Controllo Accessi",
        manufacturer=MANUFACTURER,
        configuration_url=f"homeassistant://{PANEL_URL}",
    )


class AccessEntity(Entity):
    """Entità che si ridisegna quando cambia lo stato condiviso.

    Pannello ed entità scrivono sullo stesso store: senza questo aggancio,
    spegnere il master dalla pagina lascerebbe l'interruttore esposto fermo
    al valore precedente, e i due si contraddirebbero a schermo.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        store: AccessStore,
        coordinator: AccessCoordinator,
    ) -> None:
        self._entry_id = entry_id
        self.store = store
        self.coordinator = coordinator
        self._attr_device_info = system_device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_STATE_CHANGED, self._handle_state_changed
            )
        )

    @callback
    def _handle_state_changed(self) -> None:
        """Riscrive lo stato dell'entità.

        Il decoratore non è un dettaglio: senza, Home Assistant considera
        questa funzione lavoro sincrono e la esegue in un thread del pool, da
        cui `async_write_ha_state` solleva un RuntimeError che il dispatcher
        inghiotte — e l'entità resterebbe ferma all'ultimo valore scritto
        all'avvio mentre il pannello mostra quello aggiornato.
        """
        if self.hass is not None:
            self.async_write_ha_state()
