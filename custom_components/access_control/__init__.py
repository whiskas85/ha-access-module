"""Controllo Accessi — policy, tracciatura ed eventi.

Il tag valida l'accesso, il lettore decide l'azione.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .actions import async_open_gate
from .const import DOMAIN, PLATFORMS
from .coordinator import AccessCoordinator
from .enrollment import EnrollmentManager
from .evaluator import AccessEvaluator
from .panel import async_remove_panel, async_setup_panel
from .services import async_setup_services, async_unload_services
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

# Evento dell'integrazione Tag nativa. Resta ascoltato per i lettori che non
# possono essere modificati (telefoni, tag NFC letti dall'app).
EVENT_TAG_SCANNED = "tag_scanned"

# Evento del nostro firmware, che NON passa dall'integrazione Tag.
#
# È la differenza che protegge il registro tag: `tag_scanned` fa creare a Home
# Assistant un'entità per ogni UID mai visto, quindi chi cicla centomila
# codici con un Flipper crea centomila entità. Il nostro nodo manda questo, e
# il tag entra nel registro solo dopo che la lettura è stata validata.
EVENT_READER_SCAN = "esphome.access_control_read"

# Azioni dei pulsanti nelle notifiche.
ACTION_CLEAR_ALARM = "ACCESS_CLEAR_ALARM"
ACTION_OPEN_PREFIX = "ACCESS_OPEN_"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Inizializza l'integration da una config entry."""
    store = AccessStore(hass)
    await store.async_load()

    # Le scelte fatte nel config flow diventano impostazioni modificabili dal
    # pannello: la config entry dice come partire, non come restare.
    for key, value in entry.data.items():
        if value not in (None, "", []) and not store.settings.get(key):
            store.settings[key] = value
    await store.async_save()

    coordinator = AccessCoordinator(hass, store)
    enrollment = EnrollmentManager(hass, store)
    evaluator = AccessEvaluator(hass, store, coordinator, enrollment)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update(
        {
            "store": store,
            "coordinator": coordinator,
            "enrollment": enrollment,
            "evaluator": evaluator,
            entry.entry_id: {"config": dict(entry.data)},
        }
    )

    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(enrollment.async_shutdown)
    entry.async_on_unload(_async_subscribe_reads(hass, store, evaluator))
    entry.async_on_unload(_async_subscribe_notification_actions(hass))

    _seed_readers_from_tags(hass, store)

    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version or "")
    hass.data[DOMAIN]["version"] = version

    await async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_panel(hass, version)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.debug("Controllo Accessi avviato (entry %s)", entry.entry_id)
    return True


@callback
def _async_subscribe_reads(
    hass: HomeAssistant, store: AccessStore, evaluator: AccessEvaluator
):
    """Ascolta le letture, da entrambe le sorgenti.

    Si ascolta l'evento grezzo e non un trigger per tessera censita, ed è una
    scelta di sicurezza: una tessera sconosciuta deve ricevere lo stesso `ko`
    di una valida fuori orario. Con un aggancio per tessera, una lettura
    ignota non attiverebbe nulla, il lettore andrebbe in timeout e suonerebbe
    il pattern "non raggiungibile" — dicendo a chi ha la tessera in mano che
    quella tessera non è censita.
    """

    async def _da_tag(event: Event) -> None:
        uid = event.data.get("tag_id")
        if uid:
            await evaluator.async_handle_scan(
                uid, event.data.get("device_id") or ""
            )

    async def _da_lettore(event: Event) -> None:
        uid = event.data.get("uid") or event.data.get("tag_id")
        if not uid:
            return
        device_id = event.data.get("device_id") or ""
        if not device_id:
            # Il firmware può dichiarare il proprio nome invece del device_id,
            # che non sempre viaggia negli eventi personalizzati di ESPHome.
            device_id = _device_per_nome(hass, event.data.get("lettore") or "")
        await evaluator.async_handle_scan(uid, device_id)

    unsub_tag = hass.bus.async_listen(EVENT_TAG_SCANNED, _da_tag)
    unsub_lettore = hass.bus.async_listen(EVENT_READER_SCAN, _da_lettore)

    @callback
    def _stop() -> None:
        unsub_tag()
        unsub_lettore()

    return _stop


def _device_per_nome(hass: HomeAssistant, nome: str) -> str:
    """Trova il device_id di un nodo ESPHome dal suo nome."""
    if not nome:
        return ""
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    atteso = nome.replace("_", "-").lower()
    for device in registry.devices.values():
        candidati = {
            (device.name or "").replace("_", "-").lower(),
            (device.name_by_user or "").replace("_", "-").lower(),
        }
        if atteso in candidati:
            return device.id
    return ""


@callback
def _async_subscribe_notification_actions(hass: HomeAssistant):
    """I pulsanti nelle notifiche di allarme.

    Sono la via d'uscita quando l'allarme scatta mentre qualcuno sta
    rientrando: l'impianto resta bloccato, ma chi ha il telefono può aprire
    per chi è alla porta senza sbloccare tutto.
    """

    async def _handle(event: Event) -> None:
        azione = event.data.get("action") or ""
        data = hass.data.get(DOMAIN) or {}
        if not data:
            return

        if azione == ACTION_CLEAR_ALARM:
            await data["store"].async_clear_alarm()
            await data["evaluator"].async_set_readers_enabled(True)
            _LOGGER.info("Allarme sbloccato da notifica")
            return

        if azione.startswith(ACTION_OPEN_PREFIX):
            gate_id = azione[len(ACTION_OPEN_PREFIX) :].lower()
            try:
                await async_open_gate(hass, gate_id)
                _LOGGER.info("Varco %s aperto da notifica", gate_id)
            except ValueError as err:
                _LOGGER.error("Apertura da notifica fallita: %s", err)

    return hass.bus.async_listen("mobile_app_notification_action", _handle)


@callback
def _seed_readers_from_tags(hass: HomeAssistant, store: AccessStore) -> None:
    """Riconosce i lettori già usati in passato, senza aspettare una lettura."""
    coppie = [
        (
            state.attributes.get("last_scanned_by_device_id"),
            state.state if state.state not in ("unknown", "unavailable") else None,
        )
        for state in hass.states.async_all("tag")
    ]
    store.seed_readers([c for c in coppie if c[0]])


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
