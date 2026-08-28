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
    ALARM_LABELS,
    CARD_STATES,
    DEFAULT_GATE,
    DEFAULT_WINDOW,
    DEVICE_LEARNING_TIMEOUT_S,
    DOMAIN,
    ENROLLMENT_TIMEOUT_S,
    NOTIFY_LABELS,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    REASON_LABELS,
    TECHNOLOGIES,
    TECHNOLOGY_SECURITY,
)
from .foto import AccessPhotoView, async_scatta
from .nomi import nome_dispositivo, nome_persona

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
    hass.http.register_view(AccessPhotoView)
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
    def _voce(eid: str, nome: str, foto: str, stato: str, locale: bool, note: str = ""):
        tessere = [c for c in store.cards.values() if c.person == eid]
        return {
            "entity_id": eid,
            "nome": nome,
            "foto": foto,
            "stato": stato,
            "ruolo": store.role_of(eid),
            "ruolo_nome": store.group_name(store.role_of(eid))
            if store.role_of(eid)
            else "",
            "seguita": eid in (store.settings.get("person_entities") or []),
            "locale": locale,
            "note": note,
            "tessere": len(tessere),
            "tessere_attive": sum(1 for c in tessere if c.state == "attiva"),
        }

    persone = [
        _voce(
            state.entity_id,
            state.attributes.get("friendly_name") or state.entity_id,
            state.attributes.get("entity_picture") or "",
            state.state,
            False,
        )
        for state in hass.states.async_all("person")
    ]

    # Le persone create qui non hanno presenza, e non e' una mancanza: la
    # presenza serve a decidere se la casa e' occupata, e chi ha le chiavi ma
    # non il telefono non puo' dirlo. Le finestre le fanno entrare per ruolo,
    # che e' l'informazione che le riguarda.
    persone += [
        _voce(p["id"], p.get("nome") or p["id"], "", "", True, p.get("note", ""))
        for p in store.people.values()
    ]

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


def _registro(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """Il registro, con i nomi accanto agli identificativi.

    Gli identificativi restano: sono loro a non cambiare quando qualcuno
    rinomina una persona, e un registro che perde il riferimento non e' piu'
    un registro. Ma accanto ci va il nome, perche' una riga che dice
    `person.marco` a `e9dee30b...` non si legge — e il registro si guarda
    proprio quando si ha fretta di capire.
    """
    righe = []
    for evento in store.log[:200]:
        riga = evento.to_dict()
        riga["person_nome"] = nome_persona(hass, store, riga.get("person") or "")
        riga["varco_nome"] = nome_dispositivo(hass, store, riga.get("varco") or "")
        righe.append(riga)
    return righe


async def _prova_camera(hass: HomeAssistant, store, entity_id: str) -> list[str]:
    """Prova subito la telecamera, e ricorda come si ottiene una foto.

    Tre esiti. Se l'istantanea funziona non c'e' altro da dire. Se non
    funziona ma la diretta si apre, la foto si ottiene lo stesso prendendo un
    fotogramma: costa qualche secondo, quindi la notifica parte per una strada
    diversa — e va saputo prima, non a ogni lettura. Se non si ottiene niente,
    lo si dice adesso.

    Perche' si ricorda invece di riprovare ogni volta: aprire il flusso video
    mentre la catena di un accesso sta scorrendo vorrebbe dire una porta che
    si apre due secondi dopo per colpa di una fotografia.

    Nessuno dei tre esiti rifiuta la scelta. Puo' trattarsi di una telecamera
    spenta adesso e viva stasera, e bloccare la configurazione per
    un'indisponibilita' momentanea sarebbe peggio del difetto che evita.
    """
    if not entity_id:
        return []

    from homeassistant.components import camera as camera_ha

    stato = hass.states.get(entity_id)
    nome = (stato and stato.attributes.get("friendly_name")) or entity_id

    modo = "niente"
    dettaglio = ""
    try:
        await camera_ha.async_get_image(hass, entity_id, timeout=10)
        modo = "scatto"
    except Exception as err:  # noqa: BLE001 — qualunque guasto vale lo stesso
        dettaglio = str(err)
        if await async_scatta(hass, entity_id):
            modo = "diretta"

    camere = dict(store.settings.get("camere_scatto") or {})
    camere[entity_id] = modo
    await store.async_update_settings({"camere_scatto": camere})

    if modo == "scatto":
        return []
    if modo == "diretta":
        return [
            f"«{nome}» non sa produrre un'istantanea, ma la diretta si apre: "
            f"la foto sara' un fotogramma del video. Arriva qualche secondo "
            f"dopo la notifica, e non ritarda l'apertura della porta."
        ]

    _LOGGER.warning("Da %s non si ottiene nessuna immagine: %s", entity_id, dettaglio)
    return [
        f"Da «{nome}» non si ottiene nessuna immagine ({dettaglio}): ne' "
        f"un'istantanea ne' un fotogramma della diretta. La scelta e' salvata, "
        f"ma la notifica arriverebbe senza foto."
    ]


def _nome_dispositivo(hass: HomeAssistant, store, device_id: str) -> str:
    # Condivisa con le notifiche: due funzioni separate divergono, e lo stesso
    # lettore finisce col chiamarsi in un modo a schermo e in un altro nel
    # messaggio che arriva sul telefono.
    return nome_dispositivo(hass, store, device_id)


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
                "azioni": voce.get("azioni") or [],
                "azioni_ko": voce.get("azioni_ko") or [],
                "azioni_allarme": voce.get("azioni_allarme") or [],
                "reader_service": voce.get("reader_service", ""),
                "enable_switch": voce.get("enable_switch", ""),
                "camera": voce.get("camera", ""),
                # Quali varchi apre, dedotto dalle sue azioni: non è un campo
                # da tenere allineato a mano, è una conseguenza.
                "varchi": [
                    g["id"] for g in store.gates.values() if _usa_varco(voce, g["id"])
                ],
            }
        )
    return sorted(fuori, key=lambda d: (d["nome"] or "").lower())


def _varchi(hass: HomeAssistant, store) -> list[dict[str, Any]]:
    """I varchi, con lo stato attuale dell'entità che li apre.

    Un varco che punta a un'entità sparita va detto: da fuori un'apertura che
    non succede sembra un problema di tessera, e si va a cercare dalla parte
    sbagliata.
    """
    fuori = []
    for gate in store.gates.values():
        entity_id = gate.get("entity_id") or ""
        stato = hass.states.get(entity_id) if entity_id else None
        fuori.append(
            {
                **gate,
                "entita_presente": stato is not None,
                "entita_stato": stato.state if stato else "",
                "usato_da": [
                    d.get("nome") or k
                    for k, d in store.devices.items()
                    if _usa_varco(d, gate["id"])
                ],
            }
        )
    return sorted(fuori, key=lambda g: (g.get("name") or "").lower())


def _usa_varco(device: dict[str, Any], gate_id: str) -> bool:
    """Questo lettore apre quel varco fra le sue azioni?"""
    import json

    try:
        blob = json.dumps(device.get("azioni") or [])
    except (TypeError, ValueError):
        return False
    return f'"{gate_id}"' in blob and "open_gate" in blob


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
            # Armato = una finestra ammette qualcuno E non siamo in
            # allarme: sono le due macchine messe insieme, ed e' la
            # domanda che il pannello mostra in cima.
            "armato": coordinator.is_open and not store.in_alarm,
            "master": bool(store.settings.get("master", True)),
            "porta": coordinator.door_status(),
            "presenza": coordinator.presence_recent(),
            "adulto_vicino": coordinator.adult_nearby(),
            "finestre_attive": [
                w.get("name") or w["id"] for w in coordinator.active_windows()
            ],
            "in_allarme": store.in_alarm,
            "fallimenti": store.failure_streak,
            "negati_oggi": store.denied_today(),
            # I nomi, non gli identificativi: un gruppo aggiunto a mano ha
            # un id a trattini bassi che a schermo si legge male.
            "ruoli_ammessi": [
                store.group_name(r) for r in coordinator.open_roles()
            ],
        },
        "sicurezza": {
            "stato": store.security_state,
            "in_allarme": store.in_alarm,
            "motivo": ALARM_LABELS.get(store.alarm_reason, store.alarm_reason),
            "dal": store.alarm_since,
            "fallimenti": store.failure_streak,
            "soglia": store.settings.get("alarm_threshold"),
        },
        "finestre": sorted(
            (
                {**w, "attiva": coordinator.window_active(w)}
                for w in store.windows.values()
            ),
            key=lambda w: (w.get("start") or ""),
        ),
        "notifiche": store.notifications,
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
        "log": _registro(hass, store),
        "opzioni": {
            "stati_tessera": list(CARD_STATES),
            "tecnologie": list(TECHNOLOGIES),
            "sicurezza_per_tecnologia": TECHNOLOGY_SECURITY,
            "ruoli": store.group_ids,
            "gruppi": store.groups,
            "varco_predefinito": DEFAULT_GATE,
            "finestra_predefinita": DEFAULT_WINDOW,
            "tipi_notifica": NOTIFY_LABELS,
            "motivi": REASON_LABELS,
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
        avvisi: list[str] = []
        data = hass.data[DOMAIN]
        store = data["store"]
        coordinator = data["coordinator"]
        enrollment = data["enrollment"]

        try:
            if action == "set_settings":
                impostazioni = body.get("settings") or {}
                avvisi += await _prova_camera(
                    hass, store, impostazioni.get("camera_entity", "")
                )
                await store.async_update_settings(impostazioni)
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

            elif action == "add_group":
                await store.async_add_group(body.get("nome", ""))

            elif action == "remove_group":
                await store.async_remove_group(body["group_id"])

            elif action == "add_person":
                await store.async_add_person(
                    body.get("nome", ""), body.get("note", "")
                )

            elif action == "set_person":
                await store.async_update_person(
                    body["person_id"], body.get("changes") or {}
                )

            elif action == "remove_person":
                await store.async_remove_person(body["person_id"])

            elif action == "set_person_role":
                await store.async_set_person_role(
                    body["person"], body.get("role", "")
                )

            elif action == "start_enrollment":
                await enrollment.async_start(body.get("device", ""))

            elif action == "cancel_enrollment":
                await enrollment.async_close("annullato dal pannello")

            elif action == "register_device":
                await store.async_register_device(
                    body["device_id"], body.get("nome", ""), body.get("note", "")
                )

            elif action == "set_device":
                cambiamenti = body.get("changes") or {}
                avvisi += await _prova_camera(hass, store, cambiamenti.get("camera", ""))
                await store.async_update_device(body["device_id"], cambiamenti)

            elif action == "upsert_window":
                await store.async_upsert_window(body.get("window") or {})
                coordinator.async_refresh()

            elif action == "remove_window":
                await store.async_remove_window(body["window_id"])
                coordinator.async_refresh()

            elif action == "set_notifications":
                await store.async_update_notifications(body.get("changes") or {})

            elif action == "clear_alarm":
                await store.async_clear_alarm()
                await data["evaluator"].async_set_readers_enabled(True)

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
                await store.async_clear_alarm()
                await data["evaluator"].async_set_readers_enabled(True)

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

        dati = _snapshot(hass)
        if avvisi:
            # «Salvato, pero'…»: non e' un errore, quindi non e' un codice di
            # errore. Ma non e' nemmeno silenzio.
            dati["avviso"] = " ".join(avvisi)
        return self.json(dati)
