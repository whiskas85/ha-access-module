"""La foto per le notifiche, anche quando la telecamera non sa scattare.

Non tutte le entità `camera.` producono un fermo immagine. Le videocamere in
sola diretta di certe integrazioni — le Ring, per dirne una — rispondono con
un errore alla richiesta di istantanea, pur avendo un flusso video che
funziona benissimo. Fino a ieri il modulo si arrendeva lì e la notifica
partiva senza allegato.

Ma un fotogramma di quel flusso è una foto. Quindi: prima si prova a
scattare; se non si può, si apre la diretta e si prende un frame con ffmpeg.

**Perché la foto non finisce in `/config/www/`.** Sarebbe la strada corta —
un file, un indirizzo `/local/...`, fatto. Ma quella cartella è pubblica: chi
indovina il nome del file vede chi c'era alla porta, senza aver mai fatto
l'accesso a Home Assistant. Per una foto della propria porta è un prezzo che
non vale la comodità. I fotogrammi restano quindi in memoria, dietro un
indirizzo autenticato come tutto il resto, e scadono da soli.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Quanti fotogrammi si tengono e per quanto. Pochi e brevi: servono il tempo
# che il telefono impiega ad aprire la notifica, non un istante di più. Il
# ricordo di chi è passato dalla porta sta nel registro, non qui.
MAX_FOTO = 8
SCADENZA_S = 900

URL_FOTO = f"/api/{DOMAIN}/foto/{{token}}"


async def async_scatta(hass: HomeAssistant, entity_id: str) -> bytes | None:
    """Un'immagine da questa telecamera, comunque la si riesca a ottenere."""
    if not entity_id:
        return None

    from homeassistant.components import camera as camera_ha

    try:
        immagine = await camera_ha.async_get_image(hass, entity_id, timeout=10)
        if immagine and immagine.content:
            return immagine.content
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Scatto diretto non riuscito su %s: %s", entity_id, err)

    return await _async_fotogramma(hass, entity_id)


async def _async_fotogramma(hass: HomeAssistant, entity_id: str) -> bytes | None:
    """Un fotogramma preso dalla diretta.

    Costa qualche secondo — bisogna aprire il flusso e aspettare un'immagine
    completa — ed è il motivo per cui non è la prima strada ma la seconda.
    """
    from homeassistant.components import camera as camera_ha

    try:
        sorgente = await camera_ha.async_get_stream_source(hass, entity_id)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Nessuna diretta da %s: %s", entity_id, err)
        return None

    if not sorgente:
        return None

    # ffmpeg puo' non essere ancora avviato: nessuna delle integrazioni di
    # questa casa e' obbligata a usarlo. Si avvia qui, alla prima volta che
    # serve davvero, invece di dichiararlo come dipendenza e farlo partire
    # anche agli impianti che la foto non la vogliono.
    if "ffmpeg" not in hass.config.components:
        from homeassistant.setup import async_setup_component

        if not await async_setup_component(hass, "ffmpeg", {}):
            _LOGGER.warning(
                "ffmpeg non disponibile: niente fotogramma dalla diretta di %s",
                entity_id,
            )
            return None

    try:
        from homeassistant.components import ffmpeg as ffmpeg_ha

        # Il tempo massimo lo mettiamo noi: `async_get_image` di ffmpeg non
        # prende un `timeout`, e un flusso che non arriva mai lascerebbe
        # appesa la notifica per sempre.
        async with asyncio.timeout(20):
            return await ffmpeg_ha.async_get_image(hass, sorgente)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Fotogramma dalla diretta di %s non riuscito: %s", entity_id, err
        )
        return None


def deposita(hass: HomeAssistant, dati: bytes) -> str:
    """Mette da parte l'immagine e restituisce l'indirizzo da cui si legge."""
    magazzino: dict[str, Any] = hass.data[DOMAIN].setdefault("foto", {})
    _pulisci(magazzino)

    token = secrets.token_urlsafe(16)
    magazzino[token] = (dati, time.monotonic())
    return URL_FOTO.format(token=token)


def _pulisci(magazzino: dict[str, Any]) -> None:
    adesso = time.monotonic()
    for token in [
        t for t, (_, quando) in magazzino.items() if adesso - quando > SCADENZA_S
    ]:
        magazzino.pop(token, None)

    # Anche senza scadenza: un impianto che legge molto non deve poter far
    # crescere questa memoria senza limite.
    while len(magazzino) >= MAX_FOTO:
        piu_vecchio = min(magazzino, key=lambda t: magazzino[t][1])
        magazzino.pop(piu_vecchio, None)


class AccessPhotoView(HomeAssistantView):
    """Serve un fotogramma, a chi ha diritto di vederlo.

    `requires_auth` è il punto di tutto il giro: l'app companion allega da sola
    le credenziali quando l'indirizzo è di Home Assistant, esattamente come fa
    con `/api/camera_proxy/`. Chi non ha accesso all'impianto non vede la foto
    nemmeno avendone l'indirizzo.
    """

    url = f"/api/{DOMAIN}/foto/{{token}}"
    name = f"api:{DOMAIN}:foto"
    requires_auth = True

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app["hass"]
        magazzino = hass.data.get(DOMAIN, {}).get("foto") or {}
        voce = magazzino.get(token)
        if not voce:
            return web.Response(status=404)
        return web.Response(body=voce[0], content_type="image/jpeg")
