"""Notifiche configurabili.

Ogni tipo di evento ha il suo interruttore, il suo destinatario e il suo
testo, sotto un master generale. Il testo usa segnaposto invece di essere
composto nel codice: così si cambia da pannello e non da qui.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SEGNAPOSTO = ("tessera", "titolare", "lettore", "motivo", "ora", "stato")


def _riempi(testo: str, valori: dict[str, Any]) -> str:
    """Sostituisce i segnaposto, senza esplodere su quelli sconosciuti.

    `str.format` solleverebbe KeyError su un segnaposto scritto male nel
    pannello, e una notifica di allarme che non parte per un refuso in un
    testo è il momento peggiore per scoprire un errore di battitura.
    """
    fuori = testo
    for chiave in SEGNAPOSTO:
        fuori = fuori.replace("{" + chiave + "}", str(valori.get(chiave, "")))
    return fuori


async def async_notify(
    hass: HomeAssistant,
    tipo: str,
    valori: dict[str, Any] | None = None,
) -> bool:
    """Manda la notifica del tipo indicato, se è abilitata.

    Ritorna True se è partita davvero: il chiamante non deve indovinarlo, e
    nel registro serve sapere se qualcuno è stato avvisato o no.
    """
    store = hass.data[DOMAIN]["store"]
    conf = store.notifications

    if not conf.get("master", True):
        return False

    tipo_conf = (conf.get("tipi") or {}).get(tipo)
    if not tipo_conf or not tipo_conf.get("attivo"):
        return False

    servizio = tipo_conf.get("service") or conf.get("service") or ""
    if "." not in servizio:
        _LOGGER.warning("Notifica %s senza servizio valido: %s", tipo, servizio)
        return False

    valori = dict(valori or {})
    valori.setdefault("ora", dt_util.now().strftime("%H:%M"))
    valori.setdefault("stato", store.system_state)

    dati: dict[str, Any] = {}
    if tipo_conf.get("alta_priorita"):
        # ttl 0 + priorità alta: la notifica passa anche col telefono in
        # standby, che per un allarme è il solo momento in cui conta.
        dati.update({"ttl": 0, "priority": "high"})
    camera = store.settings.get("camera_entity")
    if tipo_conf.get("immagine") and camera:
        dati["image"] = f"/api/camera_proxy/{camera}"

    payload: dict[str, Any] = {
        "title": _riempi(tipo_conf.get("titolo", ""), valori),
        "message": _riempi(tipo_conf.get("messaggio", ""), valori) or " ",
    }
    if dati:
        payload["data"] = dati

    dominio, _, nome = servizio.partition(".")
    try:
        await hass.services.async_call(dominio, nome, payload, blocking=False)
    except Exception:
        _LOGGER.exception("Notifica %s fallita su %s", tipo, servizio)
        return False
    return True


async def async_notify_alarm_with_open(
    hass: HomeAssistant,
    valori: dict[str, Any],
    azioni: list[dict[str, str]],
) -> bool:
    """Notifica di allarme, con i pulsanti per aprire comunque dal telefono.

    È la via d'uscita quando l'allarme scatta mentre qualcuno sta rientrando:
    l'impianto resta bloccato — è il punto dell'allarme — ma chi ha il
    telefono può far entrare chi è alla porta senza sbloccare tutto.
    """
    store = hass.data[DOMAIN]["store"]
    conf = store.notifications
    tipo_conf = (conf.get("tipi") or {}).get("allarme") or {}

    if not conf.get("master", True) or not tipo_conf.get("attivo"):
        return False

    servizio = tipo_conf.get("service") or conf.get("service") or ""
    if "." not in servizio:
        return False

    valori = dict(valori)
    valori.setdefault("ora", dt_util.now().strftime("%H:%M"))
    valori.setdefault("stato", store.system_state)

    dati: dict[str, Any] = {"ttl": 0, "priority": "high"}
    if camera := store.settings.get("camera_entity"):
        dati["image"] = f"/api/camera_proxy/{camera}"
    if azioni:
        dati["actions"] = azioni

    dominio, _, nome = servizio.partition(".")
    try:
        await hass.services.async_call(
            dominio,
            nome,
            {
                "title": _riempi(tipo_conf.get("titolo", ""), valori),
                "message": _riempi(tipo_conf.get("messaggio", ""), valori) or " ",
                "data": dati,
            },
            blocking=False,
        )
    except Exception:
        _LOGGER.exception("Notifica di allarme fallita su %s", servizio)
        return False
    return True
