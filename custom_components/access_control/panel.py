"""Pannello di Controllo Accessi e API che lo alimenta."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components import panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    CARD_STATES,
    DEFAULT_GATE,
    DOMAIN,
    ENROLLMENT_TIMEOUT_S,
    LOCKOUT_MODES,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    ROLES,
    TECHNOLOGIES,
    TECHNOLOGY_SECURITY,
)

_LOGGER = logging.getLogger(__name__)

PANEL_JS = "access-control-panel.js"
STATIC_URL = f"/{DOMAIN}_static"
API_STATE = f"/api/{DOMAIN}/state"
API_COMMAND = f"/api/{DOMAIN}/command"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Registra risorse statiche, API e voce nella barra laterale."""
    if hass.data[DOMAIN].get("panel_registered"):
        return

    source = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(source), cache_headers=False)]
    )

    hass.http.register_view(AccessStateView)
    hass.http.register_view(AccessCommandView)

    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="access-control-panel",
            module_url=f"{STATIC_URL}/{PANEL_JS}",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            require_admin=True,
            config={},
        )
    except ValueError:
        # Già registrato da un reload precedente: non è un errore.
        _LOGGER.debug("Pannello già registrato")

    hass.data[DOMAIN]["panel_registered"] = True


async def async_remove_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(DOMAIN, {}).get("panel_registered"):
        return
    try:
        panel_custom.async_remove_panel(hass, PANEL_URL)
    except Exception:
        _LOGGER.debug("Rimozione pannello non riuscita", exc_info=True)
    hass.data[DOMAIN]["panel_registered"] = False


def _snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Tutto ciò che il pannello disegna, in una sola risposta."""
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]

    return {
        "stato": {
            "sistema": store.system_state,
            "motivo": store.state_reason,
            "armato": coordinator.is_armed,
            "master": bool(store.settings.get("master", True)),
            "porta": coordinator.door_status(),
            "presenza": coordinator.presence_recent(),
            "adulto_vicino": coordinator.adult_nearby(),
            "finestra_scuola": coordinator.school_window_active(),
            "lockout": store.is_locked_out,
            "fallimenti": store.failure_streak,
            "bloccati_fino_a": store.locked_until,
            "negati_oggi": store.denied_today(),
        },
        "enrollment": {
            "attivo": store.enrollment_active,
            "secondi": store.enrollment_seconds_left,
        },
        "impostazioni": store.settings,
        "tessere": [
            {
                **c.to_dict(),
                "sicurezza": c.security,
                "tecnologia_label": c.technology_label,
                "ruolo": store.role_of(c.person),
            }
            for c in sorted(
                store.cards.values(), key=lambda c: (c.person, c.name, c.uid)
            )
        ],
        "varchi": list(store.gates.values()),
        "log": [e.to_dict() for e in store.log[:200]],
        "opzioni": {
            "stati_tessera": list(CARD_STATES),
            "tecnologie": list(TECHNOLOGIES),
            "sicurezza_per_tecnologia": TECHNOLOGY_SECURITY,
            "ruoli": list(ROLES),
            "modalita_lockout": list(LOCKOUT_MODES),
            "varco_predefinito": DEFAULT_GATE,
        },
    }


class AccessStateView(HomeAssistantView):
    """Fotografia completa dello stato per il pannello."""

    url = API_STATE
    name = f"api:{DOMAIN}:state"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        if not request["hass_user"].is_admin:
            return self.json_message("Solo amministratori", 403)
        return self.json(_snapshot(hass))


class AccessCommandView(HomeAssistantView):
    """Comandi del pannello.

    Un solo endpoint con un campo `action`, invece di una rotta per verbo: le
    azioni sono poche e tutte sullo stesso oggetto, e la lista dei permessi
    resta in un punto solo.
    """

    url = API_COMMAND
    name = f"api:{DOMAIN}:command"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        if not request["hass_user"].is_admin:
            return self.json_message("Solo amministratori", 403)

        try:
            body = await request.json()
        except ValueError:
            return self.json_message("JSON non valido", 400)

        action = body.get("action")
        data = hass.data[DOMAIN]
        store = data["store"]
        coordinator = data["coordinator"]

        try:
            if action == "set_settings":
                await store.async_update_settings(body.get("settings") or {})
                coordinator.async_refresh()

            elif action == "add_card":
                await store.async_add_card(
                    uid=body.get("uid", ""),
                    name=body.get("name", ""),
                    person=body.get("person", ""),
                    technology=body.get("technology", "sconosciuta"),
                    note=body.get("note", ""),
                )

            elif action == "update_card":
                await store.async_update_card(
                    body["card_id"], body.get("changes") or {}
                )

            elif action == "set_card_state":
                await store.async_set_card_state(body["card_id"], body["state"])

            elif action == "assign_person":
                await store.async_assign_person(
                    body["card_id"], body.get("person", "")
                )

            elif action == "start_enrollment":
                store.start_enrollment(ENROLLMENT_TIMEOUT_S)

            elif action == "cancel_enrollment":
                store.cancel_enrollment()

            elif action == "remove_card":
                await store.async_remove_card(body["card_id"])

            elif action == "upsert_gate":
                await store.async_upsert_gate(body.get("gate") or {})

            elif action == "remove_gate":
                await store.async_remove_gate(body["gate_id"])

            elif action == "unlock_readers":
                await store.async_unlock_readers()

            elif action == "clear_log":
                await store.async_clear_log()

            elif action == "scan":
                # Prova la catena completa senza andare al varco.
                await data["evaluator"].async_handle_scan(
                    body.get("uid", ""), body.get("gate", "")
                )

            else:
                return self.json_message(f"Azione sconosciuta: {action}", 400)

        except KeyError as err:
            return self.json_message(f"Riferimento inesistente: {err}", 404)
        except ValueError as err:
            return self.json_message(str(err), 400)

        return self.json(_snapshot(hass))
