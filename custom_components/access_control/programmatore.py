"""Programmazione delle tessere dal lettore: la parte che parla con Home Assistant.

La sequenza sta in `programmazione.py` e non sa niente di Home Assistant.
Qui c'è il resto: aprire il tramite sul lettore, aspettare la tessera,
controllare che sia **quella scelta**, passare i comandi avanti e indietro,
e alla fine chiudere il tramite qualunque cosa sia successa.

**Perché si controlla l'UID.** Il lettore sta in strada. Durante la
finestra, chiunque ci appoggi una tessera se la vedrebbe programmare con le
chiavi dell'impianto; si programma quindi solo la tessera scelta dal
pannello, e ogni altra si rifiuta senza toccarla. Il limite che resta — chi
ne clonasse l'UID su un emulatore e si presentasse proprio in quel minuto
otterrebbe le chiavi di quella tessera — è scritto in SPEC.md §15: una
tessera sola, mai la master, e solo con qualcuno in casa che ha appena
premuto «Programma».
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import slugify

from .chiavi import ChiaviNtag424
from .const import TECH_NTAG424
from .models import normalize_uid, uid_bytes
from .programmazione import ErroreProgrammazione, programma
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

EVENT_TESSERA_PRONTA = "esphome.access_control_tessera_pronta"

# Come il censimento: un minuto per andare al lettore, poi la finestra si
# chiude da sola.
ATTESA_TESSERA_S = 60
# Un comando alla tessera dura qualche centesimo di secondo più il viaggio
# in WiFi. Oltre questo, il lettore non c'è più.
ATTESA_RISPOSTA_S = 3

_NOTIFICA = "access_control_programmazione"
_TITOLO = "Programmazione tessera"


class Programmatore:
    """Una programmazione alla volta, dal pannello al lettore e ritorno."""

    def __init__(
        self, hass: HomeAssistant, store: AccessStore, chiavi: ChiaviNtag424
    ) -> None:
        self.hass = hass
        self.store = store
        self.chiavi = chiavi
        self._in_corso = False

    # ── avvio ──────────────────────────────────────────────────────────────

    async def async_avvia(self, card_id: str, device_id: str = "") -> None:
        """Controlla che si possa fare, e la fa partire in sottofondo.

        I controlli stanno qui e non dentro la sequenza perché il pannello
        deve poter dire subito «non si può», invece di aprire una finestra
        che fallirà.
        """
        if self._in_corso:
            raise ValueError("C'è già una programmazione in corso")
        card = self.store.card_by_id(card_id)
        if card is None:
            raise KeyError(card_id)
        if uid_bytes(card.uid) != 7:
            raise ValueError(
                "Solo una tessera con UID di 7 byte può essere una NTAG 424"
            )
        if self.chiavi.illeggibile:
            raise ValueError(
                "La master NTAG 424 è illeggibile: sistemala prima di programmare"
            )

        device_id = device_id or self._lettore_unico()
        device = await self.store.async_autofill_services(device_id)
        if not device.get("program_service") or not device.get("apdu_service"):
            raise ValueError(
                "Il lettore non ha ancora il firmware che sa programmare: "
                "aggiornalo da ESPHome"
            )

        self._in_corso = True
        self.hass.async_create_background_task(
            self._async_esegui(card_id, device_id, dict(device)),
            "access_control: programmazione tessera",
        )

    def _lettore_unico(self) -> str:
        lettori = list(self.store.devices)
        if not lettori:
            raise ValueError("Nessun lettore registrato")
        if len(lettori) > 1:
            raise ValueError("C'è più di un lettore: indica quale usare")
        return lettori[0]

    # ── la programmazione ──────────────────────────────────────────────────

    async def _async_esegui(
        self, card_id: str, device_id: str, device: dict[str, Any]
    ) -> None:
        nome_nodo = self._nome_nodo(device_id)
        pronta: asyncio.Future[str] = self.hass.loop.create_future()

        @callback
        def _su_pronta(event: Event) -> None:
            if pronta.done():
                return
            if slugify(str(event.data.get("lettore") or "")) != nome_nodo:
                return
            pronta.set_result(str(event.data.get("uid") or ""))

        # In ascolto PRIMA di aprire il tramite: una tessera già appoggiata
        # viene trattenuta subito, e il suo avviso non deve andare perso.
        smetti = self.hass.bus.async_listen(EVENT_TESSERA_PRONTA, _su_pronta)
        riuscita = False
        try:
            await self._servizio(device["program_service"], {"attiva": True})
            self._avvisa(
                "Appoggia la tessera al lettore entro un minuto e tienila ferma "
                "finché non senti i due bip."
            )
            try:
                uid_letto = await asyncio.wait_for(pronta, ATTESA_TESSERA_S)
            except TimeoutError as err:
                raise ErroreProgrammazione(
                    "nessuna tessera appoggiata entro un minuto"
                ) from err

            card = self.store.card_by_id(card_id)
            if card is None:
                raise ErroreProgrammazione(
                    "nel frattempo la tessera è stata tolta dal registro"
                )
            if normalize_uid(uid_letto) != card.uid:
                raise ErroreProgrammazione(
                    "al lettore è arrivata un'altra tessera, e non l'ho toccata"
                )

            master = await self.chiavi.async_master()
            esito = await programma(
                self._invia(device["apdu_service"]),
                bytes.fromhex(card.uid.replace("-", "")),
                master,
            )

            card.technology = TECH_NTAG424
            card.sdm_counter = esito.contatore
            await self.store.async_save_and_notify()
            riuscita = True
            _LOGGER.warning(
                "%s programmata con le chiavi dell'impianto: da ora è forte",
                card.label,
            )
            self._avvisa(
                f"{card.label} programmata con le chiavi dell'impianto. Da ora "
                "è forte, e apre solo presentando il suo messaggio firmato."
            )
        except ErroreProgrammazione as err:
            _LOGGER.warning("Programmazione non riuscita: %s", err)
            self._avvisa(
                f"Programmazione non riuscita: {err}. Si può riprovare: una "
                "programmazione interrotta riparte da dove serve."
            )
        except Exception:
            _LOGGER.exception("Programmazione interrotta da un errore")
            self._avvisa(
                "Programmazione interrotta da un errore del modulo: i dettagli "
                "sono nel log di Home Assistant."
            )
        finally:
            smetti()
            try:
                await self._servizio(device["program_service"], {"attiva": False})
            except Exception:
                _LOGGER.warning("Tramite non richiuso sul lettore", exc_info=True)
            await self._esito_al_lettore(device, riuscita)
            self._in_corso = False

    def _invia(self, servizio: str):
        """La funzione che manda un comando alla tessera attraverso il lettore."""
        dominio, _, nome = servizio.partition(".")

        async def invia(comando: bytes) -> bytes:
            try:
                risposta = await asyncio.wait_for(
                    self.hass.services.async_call(
                        dominio,
                        nome,
                        {"comando": comando.hex().upper()},
                        blocking=True,
                        return_response=True,
                    ),
                    ATTESA_RISPOSTA_S,
                )
            except (TimeoutError, HomeAssistantError) as err:
                raise ErroreProgrammazione("il lettore non ha risposto") from err

            testo = _risposta(risposta)
            if not testo:
                raise ErroreProgrammazione(
                    "la tessera si è allontanata dal lettore"
                )
            try:
                return bytes.fromhex(testo)
            except ValueError as err:
                raise ErroreProgrammazione(
                    "il lettore ha mandato una risposta illeggibile"
                ) from err

        return invia

    # ── contorno ───────────────────────────────────────────────────────────

    def _nome_nodo(self, device_id: str) -> str:
        device = dr.async_get(self.hass).async_get(device_id)
        return slugify(device.name) if device and device.name else ""

    async def _servizio(self, servizio: str, dati: dict[str, Any]) -> None:
        dominio, _, nome = servizio.partition(".")
        await self.hass.services.async_call(dominio, nome, dati, blocking=True)

    async def _esito_al_lettore(self, device: dict[str, Any], riuscita: bool) -> None:
        """Due bip se è andata, il bip lungo se no: chi è al lettore lo sente."""
        servizio = device.get("reader_service") or ""
        if "." not in servizio:
            return
        dominio, _, nome = servizio.partition(".")
        valore = (
            device.get("reader_ok_value", "ok")
            if riuscita
            else device.get("reader_ko_value", "ko")
        )
        try:
            await self.hass.services.async_call(
                dominio,
                nome,
                {device.get("reader_field") or "esito": valore},
                blocking=True,
            )
        except Exception:
            _LOGGER.debug("Esito della programmazione non suonato", exc_info=True)

    def _avvisa(self, testo: str) -> None:
        persistent_notification.async_create(
            self.hass, testo, title=_TITOLO, notification_id=_NOTIFICA
        )


def _risposta(risposta: Any) -> str:
    """Il campo `risposta` dell'azione del lettore, dovunque Home Assistant lo metta.

    Di norma è in cima; si guarda anche un livello sotto, perché il formato
    delle risposte delle azioni ESPHome è giovane e un annidamento in più
    non deve diventare «la tessera si è allontanata».
    """
    if not isinstance(risposta, dict):
        return ""
    valore = risposta.get("risposta")
    if isinstance(valore, str):
        return valore
    for interno in risposta.values():
        if isinstance(interno, dict) and isinstance(interno.get("risposta"), str):
            return interno["risposta"]
    return ""
