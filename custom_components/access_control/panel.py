"""Pannello di Controllo Accessi e API che lo alimenta."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components import panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CARD_STATES,
    DEFAULT_GATE,
    DEVICE_LEARNING_TIMEOUT_S,
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


async def async_setup_panel(hass: HomeAssistant, version: str = "") -> None:
    """Registra risorse statiche, API e voce nella barra laterale."""
    if hass.data[DOMAIN].get("panel_registered"):
        return

    source = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(source), cache_headers=False)]
    )

    hass.http.register_view(AccessStateView)
    hass.http.register_view(AccessCommandView)

    # La versione nell'URL del modulo è ciò che impedisce al browser di
    # continuare a servire il pannello vecchio dopo un aggiornamento.
    # `cache_headers=False` non basta: il frontend di Home Assistant ha un
    # service worker che conserva le risorse per conto suo, e sul telefono un
    # pannello di due versioni fa può restare lì per giorni. Cambiando URL a
    # ogni versione, la richiesta è per una risorsa che in cache non c'è.
    modulo = f"{STATIC_URL}/{PANEL_JS}"
    if version:
        modulo = f"{modulo}?v={version}"

    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="access-control-panel",
            module_url=modulo,
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


def _persone(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """I titolari, con quel poco che serve a riconoscerli a colpo d'occhio.

    Si elencano tutte le `person` dell'impianto e non solo quelle configurate:
    una tessera va poter essere abbinata anche a chi non è ancora fra le
    persone seguite per la presenza, che è una lista con un altro scopo.
    """
    persone = []
    for state in hass.states.async_all("person"):
        eid = state.entity_id
        tessere = [c for c in store.cards.values() if c.person == eid]
        persone.append(
            {
                "entity_id": eid,
                "nome": state.attributes.get("friendly_name") or eid,
                "foto": state.attributes.get("entity_picture") or "",
                "stato": state.state,
                "ruolo": store.role_of(eid),
                "seguita": eid in (store.settings.get("person_entities") or []),
                "tessere": len(tessere),
                "tessere_attive": sum(1 for c in tessere if c.state == "attiva"),
            }
        )
    return sorted(persone, key=lambda p: p["nome"].lower())


def _dispositivi_disponibili(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """Tutti i dispositivi di Home Assistant, per la scelta con ricerca.

    Non si filtra per integrazione o modello: non c'è un attributo che dica
    "questo ha un lettore NFC", e un filtro indovinato nasconderebbe proprio
    il dispositivo giusto senza spiegare perché non c'è. Si manda l'elenco
    completo e si cerca; chi ha già letto qualcosa è marcato, così di solito
    lo si trova in cima senza cercare.
    """
    registry = dr.async_get(hass)
    fuori = []
    for device in registry.devices.values():
        if device.disabled_by:
            continue
        fuori.append(
            {
                "device_id": device.id,
                "nome": device.name_by_user or device.name or device.id,
                "modello": device.model or "",
                "marca": device.manufacturer or "",
                "ha_letto": device.id in store.readers,
                "letture": (store.readers.get(device.id) or {}).get("letture", 0),
                "registrato": device.id in store.devices,
            }
        )
    # Chi ha già letto per primo: quasi sempre è quello che si sta cercando.
    return sorted(
        fuori, key=lambda d: (not d["ha_letto"], (d["nome"] or "").lower())
    )


def _nome_dispositivo(hass: HomeAssistant, store, device_id: str) -> str:
    if not device_id:
        return ""
    voce = store.devices.get(device_id) or {}
    if voce.get("nome"):
        return voce["nome"]
    device = dr.async_get(hass).async_get(device_id)
    return (device.name_by_user or device.name) if device else device_id


def _dispositivi(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """I lettori registrati, con quello che si è osservato di loro."""
    registry = dr.async_get(hass)
    fuori = []
    for device_id, voce in store.devices.items():
        device = registry.async_get(device_id)
        osservato = store.readers.get(device_id) or {}
        fuori.append(
            {
                "device_id": device_id,
                "nome": voce.get("nome")
                or ((device.name_by_user or device.name) if device else "")
                or device_id,
                "modello": (device.model or "") if device else "",
                "marca": (device.manufacturer or "") if device else "",
                # Un dispositivo rimosso da Home Assistant resta registrato ma
                # va detto: altrimenti un varco punta a un fantasma.
                "assente": device is None,
                "aggiunto": voce.get("aggiunto"),
                "note": voce.get("note", ""),
                "letture": osservato.get("letture", 0),
                "ultima": osservato.get("ultima"),
                "varchi": [
                    g["id"]
                    for g in store.gates.values()
                    if g.get("reader_device_id") == device_id
                ],
            }
        )
    return sorted(fuori, key=lambda d: (d["nome"] or "").lower())


def _varchi(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """I varchi, con il nome del lettore a cui sono legati.

    Il `reader_device_id` non è un dettaglio estetico: è ciò che permette di
    capire da quale lettore arriva una lettura. Se manca, ogni lettura viene
    attribuita al primo varco — con un lettore solo non cambia niente, con due
    significa che il secondo non riceve mai nulla e che il censimento aperto
    lì resterebbe in attesa per sempre. Perciò il pannello deve poterlo dire.
    """
    registry = dr.async_get(hass)
    varchi = []
    for gate in store.gates.values():
        device_id = gate.get("reader_device_id") or ""
        device = registry.async_get(device_id) if device_id else None
        varchi.append(
            {
                **gate,
                "reader_device_name": (
                    (device.name_by_user or device.name) if device else ""
                ),
                "reader_device_mancante": not device_id,
            }
        )
    return varchi


def _snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Tutto ciò che il pannello disegna, in una sola risposta."""
    data = hass.data[DOMAIN]
    store, coordinator = data["store"], data["coordinator"]

    return {
        # Il pannello la confronta con la propria: se non coincidono, uno dei
        # due è vecchio e va detto invece di lasciar credere che manchino
        # funzioni che in realtà ci sono.
        "versione": data.get("version", ""),
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
            "device": store.enrollment_device,
            "device_nome": _nome_dispositivo(hass, store, store.enrollment_device),
        },
        "persone": _persone(hass, store),
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
        "varchi": _varchi(hass, store),
        "dispositivi": _dispositivi(hass, store),
        "dispositivi_ha": _dispositivi_disponibili(hass, store),
        "registrazione_dispositivo": {
            "attiva": store.device_learning_active,
            "secondi": store.device_learning_seconds_left,
        },
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

            elif action == "set_person_role":
                await store.async_set_person_role(
                    body["person"], body.get("role", "")
                )

            elif action == "start_enrollment":
                store.start_enrollment(ENROLLMENT_TIMEOUT_S, body.get("device", ""))

            elif action == "cancel_enrollment":
                store.cancel_enrollment()

            elif action == "register_device":
                await store.async_register_device(
                    body["device_id"], body.get("nome", ""), body.get("note", "")
                )

            elif action == "unregister_device":
                await store.async_unregister_device(body["device_id"])

            elif action == "start_device_learning":
                store.start_device_learning(DEVICE_LEARNING_TIMEOUT_S)

            elif action == "cancel_device_learning":
                store.cancel_device_learning()

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
