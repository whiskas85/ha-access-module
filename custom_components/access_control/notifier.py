"""Notifiche configurabili.

Ogni tipo di evento ha il suo interruttore, il suo destinatario e il suo
testo, sotto un master generale. Il testo usa segnaposto invece di essere
composto nel codice: così si cambia da pannello e non da qui.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NOTIFY_DESTINAZIONE, PANEL_URL
from .foto import async_scatta, deposita

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


def _destinazione(tipo: str) -> dict[str, Any]:
    """Dove porta il tocco sulla notifica.

    Due chiavi per lo stesso percorso: Android legge `clickAction`, iOS legge
    `url`. Metterle tutte e due costa niente e evita che la notifica si apra
    sulla schermata iniziale su meta' dei telefoni di casa.
    """
    sezione = NOTIFY_DESTINAZIONE.get(tipo)
    if sezione is None:
        return {}
    percorso = f"/{PANEL_URL}/{sezione}" if sezione else f"/{PANEL_URL}"
    return {"clickAction": percorso, "url": percorso}


async def _async_azioni_custom(
    hass: HomeAssistant,
    tipo: str,
    tipo_conf: dict[str, Any],
    valori: dict[str, Any],
) -> bool:
    """Esegue la sequenza scritta a mano al posto della notifica del modulo.

    I segnaposto arrivano come variabile `notifica`, quindi dentro l'editor si
    scrive `{{ notifica.tessera }}` come nelle azioni di un lettore si scrive
    `{{ accesso.person }}`. Sono due nomi diversi perche' sono due cose
    diverse: qui non c'e' una decisione di accesso, c'e' un avviso da dare.
    """
    sequenza = tipo_conf.get("azioni") or []
    if not sequenza:
        _LOGGER.warning(
            "Notifica %s in modo personalizzato ma senza nessuna azione: "
            "non e' partito niente",
            tipo,
        )
        return False

    from homeassistant.helpers.script import Script

    script = Script(
        hass,
        sequenza,
        f"Controllo Accessi — notifica {tipo}",
        DOMAIN,
        script_mode="parallel",
        max_runs=5,
    )
    try:
        await script.async_run({"notifica": valori}, context=Context())
    except Exception:
        _LOGGER.exception("Azioni della notifica %s fallite", tipo)
        return False
    return True


def _modo_camera(store, camera: str) -> str:
    """Come si ottiene una foto da questa telecamera.

    «scatto» e' l'istantanea, immediata. «diretta» e' un fotogramma preso dal
    flusso video, che costa qualche secondo e vale solo per le telecamere che
    non sanno scattare. Lo decide la prova fatta scegliendola, non ogni
    notifica: provare tutte le volte metterebbe quei secondi sulla strada
    della porta che si apre.
    """
    if not camera:
        return ""
    return (store.settings.get("camere_scatto") or {}).get(camera, "scatto")


async def _async_manda_con_fotogramma(
    hass: HomeAssistant,
    dominio: str,
    nome: str,
    payload: dict[str, Any],
    camera: str,
) -> None:
    """Prende il fotogramma e poi manda: in disparte, non sulla strada.

    Aprire una diretta e aspettare un'immagine completa costa secondi, e
    questa funzione viene chiamata mentre la catena di un accesso sta ancora
    scorrendo. Farla aspettare vorrebbe dire una porta che si apre due secondi
    dopo per colpa di una fotografia.
    """
    immagine = await async_scatta(hass, camera)
    if immagine:
        dati = {**payload.get("data", {}), "image": deposita(hass, immagine)}
        payload = {**payload, "data": dati}
    else:
        _LOGGER.warning("Nessun fotogramma da %s: notifica senza foto", camera)

    try:
        await hass.services.async_call(dominio, nome, payload, blocking=False)
    except Exception:
        _LOGGER.exception("Notifica con foto fallita su %s.%s", dominio, nome)


async def async_notify(
    hass: HomeAssistant,
    tipo: str,
    valori: dict[str, Any] | None = None,
    camera: str = "",
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

    valori = dict(valori or {})
    valori.setdefault("ora", dt_util.now().strftime("%H:%M"))
    valori.setdefault("stato", store.system_state)
    valori.setdefault("telecamera", camera or store.settings.get("camera_entity") or "")

    # Il modo personalizzato non passa da un servizio di notifica: la sequenza
    # puo' non notificare affatto — accendere una luce, far parlare un
    # altoparlante — e pretendere un destinatario la escluderebbe.
    if tipo_conf.get("modo") == "custom":
        return await _async_azioni_custom(hass, tipo, tipo_conf, valori)

    servizio = tipo_conf.get("service") or conf.get("service") or ""
    if "." not in servizio:
        _LOGGER.warning("Notifica %s senza servizio valido: %s", tipo, servizio)
        return False

    dati: dict[str, Any] = _destinazione(tipo)
    if tipo_conf.get("alta_priorita"):
        # ttl 0 + priorità alta: la notifica passa anche col telefono in
        # standby, che per un allarme è il solo momento in cui conta.
        dati.update({"ttl": 0, "priority": "high"})
    # Prima quella del lettore, poi quella generale: una casa con due porte
    # ha due telecamere, e la foto della porta sbagliata e' peggio di nessuna
    # foto — fa credere di aver visto.
    camera = camera or store.settings.get("camera_entity")
    modo = _modo_camera(store, camera) if tipo_conf.get("immagine") else ""
    if tipo_conf.get("immagine"):
        if camera and modo != "diretta":
            dati["image"] = f"/api/camera_proxy/{camera}"
        elif not camera:
            # Chiedere la foto senza aver scelto la telecamera mandava la
            # notifica senza allegato e senza dire niente: da fuori sembra un
            # difetto dell'allegato, non una configurazione che manca.
            _LOGGER.warning(
                "Notifica %s: e' richiesta la foto ma non c'e' nessuna "
                "telecamera scelta nelle impostazioni del modulo",
                tipo,
            )

    payload: dict[str, Any] = {
        "title": _riempi(tipo_conf.get("titolo", ""), valori),
        "message": _riempi(tipo_conf.get("messaggio", ""), valori) or " ",
    }
    if dati:
        payload["data"] = dati

    dominio, _, nome = servizio.partition(".")
    if modo == "diretta":
        hass.async_create_task(
            _async_manda_con_fotogramma(hass, dominio, nome, payload, camera)
        )
        return True

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
    camera: str = "",
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

    valori = dict(valori)
    valori.setdefault("ora", dt_util.now().strftime("%H:%M"))
    valori.setdefault("stato", store.system_state)
    valori.setdefault("telecamera", camera or store.settings.get("camera_entity") or "")

    if tipo_conf.get("modo") == "custom":
        # Niente pulsanti «apri comunque»: quelli li mette la notifica del
        # modulo. Chi scrive la propria sequenza decide anche questo, e
        # aggiungerglieli sotto sarebbe metterle in bocca parole sue.
        return await _async_azioni_custom(hass, "allarme", tipo_conf, valori)

    servizio = tipo_conf.get("service") or conf.get("service") or ""
    if "." not in servizio:
        return False

    dati: dict[str, Any] = {**_destinazione("allarme"), "ttl": 0, "priority": "high"}
    camera = camera or store.settings.get("camera_entity")
    modo = _modo_camera(store, camera)
    if camera and modo != "diretta":
        dati["image"] = f"/api/camera_proxy/{camera}"
    elif not camera and tipo_conf.get("immagine"):
        _LOGGER.warning(
            "Notifica di allarme: e' richiesta la foto ma non c'e' nessuna "
            "telecamera scelta, ne' sul lettore ne' nelle impostazioni"
        )
    if azioni:
        dati["actions"] = azioni

    dominio, _, nome = servizio.partition(".")
    payload = {
        "title": _riempi(tipo_conf.get("titolo", ""), valori),
        "message": _riempi(tipo_conf.get("messaggio", ""), valori) or " ",
        "data": dati,
    }

    if modo == "diretta":
        hass.async_create_task(
            _async_manda_con_fotogramma(hass, dominio, nome, payload, camera)
        )
        return True

    try:
        await hass.services.async_call(dominio, nome, payload, blocking=False)
    except Exception:
        _LOGGER.exception("Notifica di allarme fallita su %s", servizio)
        return False
    return True
