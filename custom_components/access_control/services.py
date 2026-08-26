"""Servizi di Controllo Accessi."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CARD_STATES,
    DOMAIN,
    TECHNOLOGIES,
)
from .models import normalize_uid

_LOGGER = logging.getLogger(__name__)

SERVICE_SCAN = "scan"
SERVICE_ENROLL = "enroll_card"
SERVICE_SET_CARD_STATE = "set_card_state"
SERVICE_REMOVE_CARD = "remove_card"
SERVICE_UNLOCK_READERS = "unlock_readers"
SERVICE_CLEAR_LOG = "clear_log"

SCAN_SCHEMA = vol.Schema(
    {
        vol.Required("uid"): cv.string,
        vol.Optional("gate", default=""): cv.string,
    }
)

ENROLL_SCHEMA = vol.Schema(
    {
        vol.Required("uid"): cv.string,
        vol.Optional("name", default=""): cv.string,
        vol.Optional("person", default=""): cv.string,
        vol.Optional("technology", default="sconosciuta"): vol.In(TECHNOLOGIES),
        vol.Optional("note", default=""): cv.string,
    }
)

CARD_STATE_SCHEMA = vol.Schema(
    {
        vol.Exclusive("card_id", "riferimento"): cv.string,
        vol.Exclusive("uid", "riferimento"): cv.string,
        vol.Required("state"): vol.In(CARD_STATES),
    }
)

REMOVE_SCHEMA = vol.Schema(
    {
        vol.Exclusive("card_id", "riferimento"): cv.string,
        vol.Exclusive("uid", "riferimento"): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Registra i servizi. Idempotente: un reload non li duplica."""

    def _data() -> dict:
        return hass.data[DOMAIN]

    def _resolve_card_id(call: ServiceCall) -> str:
        store = _data()["store"]
        card_id = call.data.get("card_id")
        if card_id:
            if store.card_by_id(card_id) is None:
                raise vol.Invalid(f"Nessuna tessera con id {card_id}")
            return card_id
        card = store.card_by_uid(call.data.get("uid", ""))
        if card is None:
            raise vol.Invalid("Nessuna tessera con questo UID")
        return card.id

    async def _scan(call: ServiceCall) -> None:
        """Inietta una lettura.

        Serve sia per provare la catena senza andare al cancello, sia per i
        lettori che non passano dall'integrazione Tag.
        """
        await _data()["evaluator"].async_handle_scan(
            call.data["uid"], call.data.get("gate", "")
        )

    async def _enroll(call: ServiceCall) -> None:
        card = await _data()["store"].async_add_card(
            uid=call.data["uid"],
            name=call.data.get("name", ""),
            person=call.data.get("person", ""),
            technology=call.data.get("technology", "sconosciuta"),
            note=call.data.get("note", ""),
        )
        _LOGGER.info("Tessera censita: %s (%s)", card.label, card.security)

    async def _set_state(call: ServiceCall) -> None:
        store = _data()["store"]
        await store.async_set_card_state(_resolve_card_id(call), call.data["state"])

    async def _remove(call: ServiceCall) -> None:
        store = _data()["store"]
        await store.async_remove_card(_resolve_card_id(call))

    async def _unlock(_call: ServiceCall) -> None:
        await _data()["store"].async_unlock_readers()

    async def _clear_log(_call: ServiceCall) -> None:
        await _data()["store"].async_clear_log()

    registrations = (
        (SERVICE_SCAN, _scan, SCAN_SCHEMA),
        (SERVICE_ENROLL, _enroll, ENROLL_SCHEMA),
        (SERVICE_SET_CARD_STATE, _set_state, CARD_STATE_SCHEMA),
        (SERVICE_REMOVE_CARD, _remove, REMOVE_SCHEMA),
        (SERVICE_UNLOCK_READERS, _unlock, None),
        (SERVICE_CLEAR_LOG, _clear_log, None),
    )
    for name, handler, schema in registrations:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


def async_unload_services(hass: HomeAssistant) -> None:
    for name in (
        SERVICE_SCAN,
        SERVICE_ENROLL,
        SERVICE_SET_CARD_STATE,
        SERVICE_REMOVE_CARD,
        SERVICE_UNLOCK_READERS,
        SERVICE_CLEAR_LOG,
    ):
        hass.services.async_remove(DOMAIN, name)


__all__ = ["async_setup_services", "async_unload_services", "normalize_uid"]
