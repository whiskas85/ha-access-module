"""Sorveglianza dei contatti di manomissione.

La specifica diceva: «lato Home Assistant serve un'automazione che chiami
`access_control.report_tamper` quando il contatto passa a `on`». Il servizio
esiste ed è giusto che esista — un tamper può arrivare anche da un sensore che
non appartiene a nessun lettore — ma **pretendere l'automazione era sbagliato**.

Un impianto in cui il tamper funziona solo se qualcuno si è ricordato di
scrivere un'automazione è un impianto in cui il tamper, nel giorno che serve,
non funziona. E il modo in cui fallisce è il peggiore: aprire la scatola del
lettore non produce niente, esattamente come se il contatto non fosse mai
stato cablato. Nessun errore, nessuna traccia, nessuna differenza visibile fra
«non l'ho collegato» e «non l'ho armato».

Perciò il modulo guarda da solo il contatto di ogni lettore registrato. Il
nodo continua a limitarsi a segnalare: il sensore dice `on`, la decisione di
andare in allarme resta qui dentro.
"""

from __future__ import annotations

import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from .const import ALARM_TAMPER, SIGNAL_STATE_CHANGED
from .evaluator import AccessEvaluator
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)


class TamperWatcher:
    """Porta l'impianto in allarme quando un lettore viene aperto."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: AccessStore,
        evaluator: AccessEvaluator,
    ) -> None:
        self.hass = hass
        self.store = store
        self.evaluator = evaluator
        self._unsub_stati = None
        self._unsub_store = None
        self._sorvegliati: list[str] = []

    @callback
    def async_start(self):
        """Arma la sorveglianza e la tiene allineata ai lettori registrati."""
        self._async_riarma()

        # I lettori si aggiungono e si tolgono mentre il sistema gira, quindi
        # l'elenco dei contatti da guardare non si puo' fissare all'avvio: un
        # lettore registrato dopo resterebbe senza tamper per sempre.
        self._unsub_store = async_dispatcher_connect(
            self.hass, SIGNAL_STATE_CHANGED, self._async_riarma
        )

        @callback
        def _stop() -> None:
            if self._unsub_stati is not None:
                self._unsub_stati()
                self._unsub_stati = None
            if self._unsub_store is not None:
                self._unsub_store()
                self._unsub_store = None

        return _stop

    @callback
    def _async_riarma(self) -> None:
        entita = sorted(
            entity_id
            for device in self.store.devices.values()
            if (entity_id := device.get("tamper_sensor"))
        )
        if entita == self._sorvegliati:
            return

        if self._unsub_stati is not None:
            self._unsub_stati()
            self._unsub_stati = None

        self._sorvegliati = entita
        if not entita:
            return

        self._unsub_stati = async_track_state_change_event(
            self.hass, entita, self._async_cambiato
        )
        _LOGGER.debug("Tamper sorvegliati: %s", ", ".join(entita))

    async def _async_cambiato(self, event: Event) -> None:
        nuovo = event.data.get("new_state")
        vecchio = event.data.get("old_state")
        if nuovo is None or nuovo.state != "on":
            return

        # `unavailable` → `on` non e' una manomissione: e' il nodo che torna
        # in linea dichiarando lo stato in cui si trovava. Vale invece
        # `off` → `on`, che e' il coperchio che si apre davvero.
        if vecchio is None or vecchio.state != "off":
            return

        if not self.store.settings.get("alarm_on_tamper", True):
            _LOGGER.info(
                "Manomissione su %s, ma l'allarme da tamper e' disattivato",
                event.data.get("entity_id"),
            )
            return

        lettore = next(
            (
                device_id
                for device_id, device in self.store.devices.items()
                if device.get("tamper_sensor") == event.data.get("entity_id")
            ),
            "",
        )
        _LOGGER.warning("Manomissione rilevata su %s", event.data.get("entity_id"))
        await self.evaluator.async_raise_alarm(ALARM_TAMPER, lettore)
