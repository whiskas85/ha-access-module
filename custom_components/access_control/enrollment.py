"""Governo della finestra di censimento.

La finestra vive in Home Assistant e basta: il lettore non sa che cosa sia un
censimento, non decide che una lettura vada censita, e continua a mandare le
stesse letture di sempre. Qui dentro c'è solo chi la apre, chi la chiude e chi
lo racconta al LED.

Perché serva un posto suo, e non due righe nel pulsante:

- **La scadenza deve essere attiva.** Finché lo stato era un timestamp da
  confrontare, «scaduto» era una cosa che si scopriva guardando, e andava
  benissimo: nessuno doveva farci niente. Da quando il lettore mostra un
  colore dedicato, allo scadere qualcuno deve *spegnerlo* — se no la spia
  resta bianca e racconta una finestra che non c'è più.
- **I punti d'ingresso sono cinque** (interruttore, pulsante, servizio,
  pannello, prima lettura) e devono chiudere tutti allo stesso modo. Con la
  logica sparsa, prima o poi una strada dimentica di avvisare il lettore, e
  il difetto si vede solo da fuori casa.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import ENROLLMENT_TIMEOUT_S
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)


class EnrollmentManager:
    """Apre e chiude il censimento, e tiene allineata la spia del lettore."""

    def __init__(self, hass: HomeAssistant, store: AccessStore) -> None:
        self.hass = hass
        self.store = store
        self._unsub = None

    # ── apertura e chiusura ────────────────────────────────────────────────

    async def async_start(
        self, device_id: str = "", seconds: int = ENROLLMENT_TIMEOUT_S
    ) -> None:
        """Apre la finestra e accende la spia."""
        self._annulla_timer()
        self.store.start_enrollment(seconds, device_id)

        # Import locale: `homeassistant.helpers.event` tira dentro mezzo core
        # e questo modulo viene importato anche solo per il tipo.
        from homeassistant.helpers.event import async_call_later

        self._unsub = async_call_later(self.hass, seconds, self._async_scaduta)
        await self._async_segnala(True, device_id)

    async def async_close(self, motivo: str = "") -> None:
        """Chiude la finestra e spegne la spia.

        Idempotente: chiamarla a finestra già chiusa non manda niente al
        lettore. Le strade che ci arrivano sono tante e alcune si accavallano
        — la prima lettura chiude, e un istante dopo può arrivare lo spegni
        dell'interruttore.
        """
        if not self.store.enrollment_active and self._unsub is None:
            return

        self._annulla_timer()
        self.store.cancel_enrollment()
        await self._async_segnala(False)
        if motivo:
            _LOGGER.debug("Censimento chiuso: %s", motivo)

    def async_shutdown(self) -> None:
        """Chiude bottega allo scaricamento dell'integration.

        Solo il timer: qui non si tocca lo stato salvato, perche' un riavvio
        non deve cancellare una finestra che chi l'ha aperta si aspetta di
        ritrovare — e comunque scade da sola.
        """
        self._annulla_timer()

    # ── scadenza ───────────────────────────────────────────────────────────

    async def _async_scaduta(self, _now) -> None:
        self._unsub = None
        await self.async_close("nessuna tessera entro il minuto")

    def _annulla_timer(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    # ── spia sul lettore ───────────────────────────────────────────────────

    async def _async_segnala(self, attivo: bool, device_id: str = "") -> None:
        """Dice ai lettori se stanno registrando.

        Accendendo si avvisa **solo** il lettore su cui la finestra è aperta:
        far pulsare anche gli altri direbbe a chi passa davanti a un'altra
        porta che lì basta appoggiare una tessera qualsiasi, che non è vero e
        sarebbe comunque un invito. Spegnendo si avvisano tutti, perché una
        spia rimasta accesa per una finestra chiusa è il difetto peggiore dei
        due e costa solo una chiamata a vuoto.
        """
        if attivo and device_id:
            bersagli = [device_id]
        else:
            bersagli = list(self.store.devices)

        for bersaglio in bersagli:
            device = await self.store.async_autofill_services(bersaglio)
            service = device.get("enroll_service") or ""
            if "." not in service:
                continue
            dominio, _, nome = service.partition(".")
            campo = device.get("enroll_field") or "attivo"
            try:
                await self.hass.services.async_call(
                    dominio, nome, {campo: attivo}, blocking=True
                )
            except Exception:
                # Il lettore può essere spento o irraggiungibile: il
                # censimento resta valido lo stesso, si perde la spia.
                _LOGGER.warning(
                    "Spia del censimento non aggiornata su %s (%s)",
                    bersaglio,
                    service,
                    exc_info=True,
                )
