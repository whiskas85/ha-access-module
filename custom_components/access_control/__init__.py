"""Controllo Accessi — policy, tracciatura ed eventi. L'apertura la fanno gli script."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, PLATFORMS
from .coordinator import AccessCoordinator
from .evaluator import AccessEvaluator
from .panel import async_remove_panel, async_setup_panel
from .services import async_setup_services, async_unload_services
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

# Emesso dall'integrazione Tag nativa a ogni lettura, comprese quelle di
# tessere mai viste prima.
EVENT_TAG_SCANNED = "tag_scanned"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Inizializza l'integration da una config entry."""
    store = AccessStore(hass)
    await store.async_load()

    # Le scelte fatte nel config flow diventano impostazioni modificabili dal
    # pannello: la config entry dice come partire, non come restare.
    initial = {k: v for k, v in entry.data.items() if v not in (None, "", [])}
    if initial:
        for key, value in initial.items():
            store.settings.setdefault(key, value)
            if not store.settings.get(key):
                store.settings[key] = value
        await store.async_save()

    coordinator = AccessCoordinator(hass, store)
    evaluator = AccessEvaluator(hass, store, coordinator)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update(
        {
            "store": store,
            "coordinator": coordinator,
            "evaluator": evaluator,
            entry.entry_id: {"config": dict(entry.data)},
        }
    )

    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(_async_subscribe_tags(hass, store, evaluator))

    await async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_panel(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.debug("Controllo Accessi avviato (entry %s)", entry.entry_id)
    return True


@callback
def _async_subscribe_tags(
    hass: HomeAssistant, store: AccessStore, evaluator: AccessEvaluator
):
    """Ascolta ogni lettura di tag.

    Si ascolta l'evento grezzo e non un trigger per tessera censita, ed è una
    scelta di sicurezza: una tessera sconosciuta deve ricevere lo stesso `ko`
    di una tessera valida fuori orario. Con un aggancio per tessera, una
    lettura ignota non attiverebbe nulla, il lettore andrebbe in timeout e
    suonerebbe il pattern "non raggiungibile" — dicendo a chi ha in mano la
    tessera che quella tessera non è censita. Qui l'indistinguibilità è
    garantita per costruzione, non per disciplina.
    """

    async def _handle(event: Event) -> None:
        uid = event.data.get("tag_id")
        if not uid:
            return
        gate_id = _gate_for_device(store, event.data.get("device_id"))
        await evaluator.async_handle_scan(uid, gate_id)

    return hass.bus.async_listen(EVENT_TAG_SCANNED, _handle)


def _gate_for_device(store: AccessStore, device_id: str | None) -> str:
    """Da quale varco arriva questa lettura."""
    if device_id:
        for gate_id, gate in store.gates.items():
            if gate.get("reader_device_id") == device_id:
                return gate_id
    return next(iter(store.gates), "ingresso")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica la config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await async_remove_panel(hass)
        async_unload_services(hass)
        for key in ("store", "coordinator", "evaluator", entry.entry_id):
            hass.data[DOMAIN].pop(key, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
