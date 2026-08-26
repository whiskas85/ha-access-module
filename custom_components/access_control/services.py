"""Servizi di Controllo Accessi."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .actions import async_open_gate
from .const import (
    ALARM_TAMPER,
    CARD_STATES,
    DEVICE_LEARNING_TIMEOUT_S,
    DOMAIN,
    ENROLLMENT_TIMEOUT_S,
    SERVICE_OPEN_GATE,
    TECHNOLOGIES,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SCAN = "scan"
SERVICE_ENROLL = "enroll_card"
SERVICE_SET_CARD_STATE = "set_card_state"
SERVICE_REMOVE_CARD = "remove_card"
SERVICE_CLEAR_ALARM = "clear_alarm"
SERVICE_RAISE_TAMPER = "report_tamper"
SERVICE_CLEAR_LOG = "clear_log"
SERVICE_START_ENROLLMENT = "start_enrollment"
SERVICE_START_DEVICE_LEARNING = "start_device_learning"
SERVICE_SET_READING = "set_reading_enabled"

OPEN_GATE_SCHEMA = vol.Schema({vol.Required("gate"): cv.string})

SCAN_SCHEMA = vol.Schema(
    {
        vol.Required("uid"): cv.string,
        vol.Optional("device", default=""): cv.string,
    }
)

ENROLLMENT_SCHEMA = vol.Schema(
    {
        vol.Optional("device", default=""): cv.string,
        vol.Optional("seconds", default=ENROLLMENT_TIMEOUT_S): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)

DEVICE_LEARNING_SCHEMA = vol.Schema(
    {
        vol.Optional("seconds", default=DEVICE_LEARNING_TIMEOUT_S): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)

ENROLL_SCHEMA = vol.Schema(
    {
        vol.Required("uid"): cv.string,
        vol.Optional("name", default=""): cv.string,
        vol.Optional("person", default=""): cv.string,
        # Omessa, viene rilevata dall'UID: è il caso normale.
        vol.Optional("technology"): vol.In(TECHNOLOGIES),
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

TAMPER_SCHEMA = vol.Schema({vol.Optional("device", default=""): cv.string})

READING_SCHEMA = vol.Schema({vol.Required("enabled"): cv.boolean})


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

    async def _open_gate(call: ServiceCall) -> None:
        await async_open_gate(hass, call.data["gate"])

    async def _scan(call: ServiceCall) -> None:
        """Inietta una lettura, come se arrivasse da un lettore."""
        await _data()["evaluator"].async_handle_scan(
            call.data["uid"], call.data.get("device", "")
        )

    async def _enroll(call: ServiceCall) -> None:
        card = await _data()["store"].async_add_card(
            uid=call.data["uid"],
            name=call.data.get("name", ""),
            person=call.data.get("person", ""),
            technology=call.data.get("technology", ""),
            note=call.data.get("note", ""),
        )
        _LOGGER.info(
            "Tessera censita: %s — %s (%s)",
            card.label,
            card.technology_label,
            card.security,
        )

    async def _start_enrollment(call: ServiceCall) -> None:
        _data()["store"].start_enrollment(
            call.data.get("seconds", ENROLLMENT_TIMEOUT_S),
            call.data.get("device", ""),
        )

    async def _start_device_learning(call: ServiceCall) -> None:
        _data()["store"].start_device_learning(
            call.data.get("seconds", DEVICE_LEARNING_TIMEOUT_S)
        )

    async def _set_state(call: ServiceCall) -> None:
        await _data()["store"].async_set_card_state(
            _resolve_card_id(call), call.data["state"]
        )

    async def _remove(call: ServiceCall) -> None:
        await _data()["store"].async_remove_card(_resolve_card_id(call))

    async def _clear_alarm(_call: ServiceCall) -> None:
        data = _data()
        await data["store"].async_clear_alarm()
        # Sbloccare l'impianto senza riaccendere i lettori lascerebbe un
        # sistema che si dichiara normale e non legge niente.
        await data["evaluator"].async_set_readers_enabled(True)

    async def _report_tamper(call: ServiceCall) -> None:
        """Segnala la manomissione di un lettore.

        Esposto come servizio perché è il microswitch di tamper a chiamarlo,
        tramite un'automazione: così il giorno che il contatto viene cablato
        non serve toccare l'integration.
        """
        data = _data()
        if not data["store"].settings.get("alarm_on_tamper", True):
            return
        await data["evaluator"].async_raise_alarm(
            ALARM_TAMPER, call.data.get("device", "")
        )

    async def _set_reading(call: ServiceCall) -> None:
        await _data()["evaluator"].async_set_readers_enabled(call.data["enabled"])

    async def _clear_log(_call: ServiceCall) -> None:
        await _data()["store"].async_clear_log()

    registrations = (
        (SERVICE_OPEN_GATE, _open_gate, OPEN_GATE_SCHEMA),
        (SERVICE_SCAN, _scan, SCAN_SCHEMA),
        (SERVICE_START_ENROLLMENT, _start_enrollment, ENROLLMENT_SCHEMA),
        (SERVICE_START_DEVICE_LEARNING, _start_device_learning, DEVICE_LEARNING_SCHEMA),
        (SERVICE_ENROLL, _enroll, ENROLL_SCHEMA),
        (SERVICE_SET_CARD_STATE, _set_state, CARD_STATE_SCHEMA),
        (SERVICE_REMOVE_CARD, _remove, REMOVE_SCHEMA),
        (SERVICE_CLEAR_ALARM, _clear_alarm, None),
        (SERVICE_RAISE_TAMPER, _report_tamper, TAMPER_SCHEMA),
        (SERVICE_SET_READING, _set_reading, READING_SCHEMA),
        (SERVICE_CLEAR_LOG, _clear_log, None),
    )
    for name, handler, schema in registrations:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


def async_unload_services(hass: HomeAssistant) -> None:
    for name in (
        SERVICE_OPEN_GATE,
        SERVICE_SCAN,
        SERVICE_START_ENROLLMENT,
        SERVICE_START_DEVICE_LEARNING,
        SERVICE_ENROLL,
        SERVICE_SET_CARD_STATE,
        SERVICE_REMOVE_CARD,
        SERVICE_CLEAR_ALARM,
        SERVICE_RAISE_TAMPER,
        SERVICE_SET_READING,
        SERVICE_CLEAR_LOG,
    ):
        hass.services.async_remove(DOMAIN, name)
