"""Motore di valutazione: decide, risponde, traccia, esegue le azioni.

Il tag valida l'accesso, il lettore decide l'azione. Qui si stabilisce se la
lettura è valida; cosa succede poi è la sequenza di azioni configurata su quel
lettore, eseguita da Home Assistant.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .actions import async_run_device_actions
from .const import (
    ALARM_BLACKLIST,
    ALARM_DISABLED_CARD,
    ALARM_FAILED_READS,
    ALARM_LABELS,
    CARD_ACTIVE,
    CARD_BLACKLISTED,
    CARD_UNKNOWN,
    DOMAIN,
    EVENT_ACCESS,
    EVENT_ALARM,
    EVENT_DEVICE_REGISTERED,
    EVENT_ENROLLED,
    NOTIFY_ACCESS_KO,
    NOTIFY_ACCESS_OK,
    NOTIFY_BLACKLIST,
    NOTIFY_DEVICE,
    NOTIFY_ENROLLED,
    REASON_ALARM_ACTIVE,
    REASON_CARD_BLACKLISTED,
    REASON_CARD_DISABLED,
    REASON_CLOSED,
    REASON_DEVICE_NOT_REGISTERED,
    REASON_LABELS,
    REASON_MASTER_OFF,
    REASON_NO_ACTIONS,
    REASON_NO_PERSON,
    REASON_RATE_LIMIT,
    REASON_ROLE_NOT_ALLOWED,
    REASON_ROLE_NOT_ASSIGNED,
    REASON_UNKNOWN_CARD,
    RESULT_ALARM,
    RESULT_BLACKLIST,
    RESULT_DENIED,
    RESULT_ENROLLED,
    RESULT_GRANTED,
    SECURITY_UNKNOWN,
)
from .coordinator import AccessCoordinator
from .enrollment import EnrollmentManager
from .models import AccessEvent, Card, normalize_uid, uid_bytes
from .nomi import nome_dispositivo, nome_persona
from .notifier import async_notify, async_notify_alarm_with_open
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)


class Decision:
    """Esito della valutazione, prima che venga attuato qualcosa."""

    def __init__(
        self,
        result: str,
        reason: str = "",
        card: Card | None = None,
        role: str = "",
        finestra: str = "",
    ) -> None:
        self.result = result
        self.reason = reason
        self.card = card
        self.role = role
        self.finestra = finestra

    @property
    def granted(self) -> bool:
        return self.result == RESULT_GRANTED


class AccessEvaluator:
    """Valuta le credenziali e orchestra azioni, log, eventi e notifiche."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: AccessStore,
        coordinator: AccessCoordinator,
        enrollment: EnrollmentManager,
    ) -> None:
        self.hass = hass
        self.store = store
        self.coordinator = coordinator
        self.enrollment = enrollment
        # Timestamp delle letture recenti, per il rate limit lato Home
        # Assistant. Quello nel lettore non basta: un firmware sostituito lo
        # aggirerebbe, e il lettore sta fuori casa.
        self._recent: deque[float] = deque(maxlen=256)

    # ── ingresso principale ────────────────────────────────────────────────

    async def async_handle_scan(self, raw_uid: str, device_id: str = "") -> Decision:
        """Valuta una lettura e porta a termine tutto ciò che ne consegue."""
        uid = normalize_uid(raw_uid)
        # Non `devices.get`: qui i servizi del lettore, se non sono ancora
        # stati scelti, vengono indovinati. Un impianto gia' installato si
        # sistema alla prima lettura, senza che nessuno debba sapere che
        # c'era un campo da compilare.
        device = await self.store.async_autofill_services(device_id) or {}

        if device_id:
            await self.store.async_note_reader(device_id)

        # Registrazione automatica del LETTORE: scarta la tessera, qui
        # interessa solo sapere quale dispositivo ha letto.
        if self.store.device_learning_active:
            return await self._async_learn_device(device, device_id)

        # Censimento di una TESSERA, solo dal lettore su cui è aperto.
        if self.store.enrollment_accepts(device_id):
            return await self._async_enroll(uid, device, device_id)

        decision = self._decide(uid, device_id)

        # Rispondere SEMPRE, anche negando, e prima di attuare: se il modulo
        # tace, il dispositivo emette il pattern "non raggiungibile" e chi è
        # alla porta crede che il sistema sia guasto.
        await self._async_respond(device, granted=decision.granted)

        event = self._build_event(decision, uid, device_id)
        self.hass.bus.async_fire(EVENT_ACCESS, event.to_dict())
        await self.store.async_append_log(event)

        if decision.granted:
            await self.store.async_reset_failures()
            if decision.card is not None:
                decision.card.register_use()
                await self.store.async_save_and_notify()
            # Solo adesso il tag entra nel registro tag di Home Assistant.
            await self._async_publish_tag(uid, decision)
            await self._async_notify(decision, event)
            await async_run_device_actions(
                self.hass, device_id, event.to_dict()
            )
        else:
            await self._async_notify(decision, event)
            await self._async_after_failure(decision, event, device_id)

        return decision

    # ── decisione ──────────────────────────────────────────────────────────

    def _decide(self, uid: str, device_id: str) -> Decision:
        card = self.store.card_by_uid(uid)
        role = self.store.role_of(card.person) if card and card.person else ""

        # La blacklist si riconosce sempre, anche a master spento: è
        # l'informazione che interessa di più e va comunque tracciata.
        if card is not None and card.state == CARD_BLACKLISTED:
            return Decision(RESULT_BLACKLIST, REASON_CARD_BLACKLISTED, card, role)

        if self.store.in_alarm:
            return Decision(RESULT_ALARM, REASON_ALARM_ACTIVE, card, role)

        if self._rate_limited():
            return Decision(RESULT_DENIED, REASON_RATE_LIMIT, card, role)

        if device_id not in self.store.devices:
            return Decision(
                RESULT_DENIED, REASON_DEVICE_NOT_REGISTERED, card, role
            )

        if not self.coordinator.master_on:
            return Decision(RESULT_DENIED, REASON_MASTER_OFF, card, role)

        if card is None:
            return Decision(RESULT_DENIED, REASON_UNKNOWN_CARD)

        if card.state != CARD_ACTIVE:
            return Decision(RESULT_DENIED, REASON_CARD_DISABLED, card, role)

        if not card.person:
            return Decision(RESULT_DENIED, REASON_NO_PERSON, card, role)

        # Titolare senza ruolo: non è un adulto per default, è una decisione
        # che manca. Si nega e si dice quale, invece di indovinare.
        if not role:
            return Decision(RESULT_DENIED, REASON_ROLE_NOT_ASSIGNED, card, role)

        ammesso, finestra = self.coordinator.allows(role, device_id)
        if not ammesso:
            motivo = (
                REASON_CLOSED
                if not self.coordinator.open_roles()
                else REASON_ROLE_NOT_ALLOWED
            )
            return Decision(RESULT_DENIED, motivo, card, role)

        if not (self.store.devices.get(device_id) or {}).get("azioni"):
            # Consentito ma non c'è niente da fare: va detto, perché da fuori
            # sembra identico a un diniego e si cercherebbe il problema nella
            # tessera invece che nella configurazione del lettore.
            return Decision(RESULT_DENIED, REASON_NO_ACTIONS, card, role, finestra)

        return Decision(RESULT_GRANTED, "", card, role, finestra)

    def _rate_limited(self) -> bool:
        window = float(self.store.settings.get("rate_limit_window_s") or 10)
        maximum = int(self.store.settings.get("rate_limit_max") or 3)
        now = time.monotonic()
        while self._recent and now - self._recent[0] > window:
            self._recent.popleft()
        self._recent.append(now)
        return len(self._recent) > maximum

    # ── conseguenze di un fallimento ───────────────────────────────────────

    async def _async_after_failure(
        self, decision: Decision, event: AccessEvent, device_id: str
    ) -> None:
        """Conta i fallimenti e, se serve, porta il sistema in allarme."""
        settings = self.store.settings

        if decision.result == RESULT_BLACKLIST and settings.get("alarm_on_blacklist"):
            await self._async_raise_alarm(ALARM_BLACKLIST, event)
            return

        if decision.reason == REASON_CARD_DISABLED and settings.get(
            "alarm_on_disabled_card"
        ):
            await self._async_raise_alarm(ALARM_DISABLED_CARD, event)
            return

        # Un rifiuto mentre l'allarme è già attivo non conta: sarebbe un
        # contatore che sale da solo mentre l'impianto è già fermo.
        if self.store.in_alarm:
            return

        streak = await self.store.async_register_failure()
        soglia = int(settings.get("alarm_threshold") or 3)
        if streak >= soglia:
            await self._async_raise_alarm(ALARM_FAILED_READS, event)

    async def async_raise_alarm(self, motivo: str, lettore: str = "") -> None:
        """Porta il sistema in allarme dall'esterno (tamper, o a mano)."""
        await self._async_raise_alarm(
            motivo, AccessEvent(result=RESULT_ALARM, reason=motivo, gate=lettore)
        )

    async def _async_raise_alarm(self, motivo: str, event: AccessEvent) -> None:
        if not await self.store.async_raise_alarm(motivo):
            return

        _LOGGER.warning("Sistema in allarme: %s", ALARM_LABELS.get(motivo, motivo))
        self.hass.bus.async_fire(
            EVENT_ALARM,
            {
                "motivo": motivo,
                "motivo_testo": ALARM_LABELS.get(motivo, motivo),
                "uid": event.uid,
                "lettore": event.gate,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        # I lettori smettono di leggere: è ciò che ferma l'inondazione alla
        # radice, invece di limitarsi a rifiutarla dopo averla ricevuta.
        await self.async_set_readers_enabled(False)

        # La via d'uscita: l'impianto resta bloccato, ma chi ha il telefono
        # può far entrare chi è alla porta senza sbloccare tutto.
        azioni = [
            {
                "action": f"ACCESS_OPEN_{gid.upper()}",
                "title": f"Apri {g.get('name', gid)}",
            }
            # Tre al massimo: la companion app non ne mostra di più, e la
            # terza voce serve per lo sblocco.
            for gid, g in list(self.store.gates.items())[:2]
        ]
        azioni.append({"action": "ACCESS_CLEAR_ALARM", "title": "Sblocca impianto"})
        await async_notify_alarm_with_open(
            self.hass,
            {
                "motivo": ALARM_LABELS.get(motivo, motivo),
                "lettore": self._nome_lettore(event.gate),
            },
            azioni,
            self._camera_lettore(event.gate),
        )

    async def async_set_readers_enabled(self, enabled: bool) -> None:
        """Accende o spegne la lettura su tutti i lettori registrati."""
        for device_id, device in self.store.devices.items():
            entity_id = device.get("enable_switch")
            if not entity_id or "." not in entity_id:
                continue
            servizio = "turn_on" if enabled else "turn_off"
            try:
                await self.hass.services.async_call(
                    entity_id.split(".", 1)[0],
                    servizio,
                    {"entity_id": entity_id},
                    blocking=False,
                )
            except Exception:
                _LOGGER.exception(
                    "Non sono riuscito a %s la lettura su %s", servizio, device_id
                )

    # ── risposta al lettore ────────────────────────────────────────────────

    async def _async_respond(
        self, device: dict[str, Any], *, granted: bool
    ) -> None:
        """Risponde al dispositivo.

        Il feedback è binario e non rivela mai il motivo del diniego: tessera
        sconosciuta, disabilitata, in blacklist, valida fuori finestra e
        sistema in allarme producono tutti lo stesso `ko`. Un feedback
        differenziato direbbe a chi ha in mano una tessera trovata se quella
        tessera è censita, e se vale la pena tornare a un altro orario.
        """
        service = device.get("reader_service")
        if not service or "." not in service:
            return
        dominio, _, nome = service.partition(".")
        campo = device.get("reader_field") or "esito"
        valore = (
            device.get("reader_ok_value", "ok")
            if granted
            else device.get("reader_ko_value", "ko")
        )
        try:
            await self.hass.services.async_call(
                dominio, nome, {campo: valore}, blocking=True
            )
        except Exception:
            _LOGGER.exception("Risposta al lettore fallita (%s)", service)

    # ── registro tag di Home Assistant ─────────────────────────────────────

    async def _async_publish_tag(self, uid: str, decision: Decision) -> None:
        """Fa comparire il tag nel registro di Home Assistant.

        Solo per una lettura VALIDA, ed è il punto. Prima il nodo chiamava
        `tag_scanned` a ogni lettura e Home Assistant creava un'entità per
        ogni UID mai visto: chi passa con un Flipper e cicla centomila codici
        creava centomila entità, rendendo inservibile il registro tag e
        gonfiando il database. Ora un UID sconosciuto resta un numero in un
        contatore.
        """
        if not uid or decision.card is None:
            return
        try:
            await self.hass.services.async_call(
                "tag", "scan", {"tag_id": uid}, blocking=False
            )
        except Exception:
            _LOGGER.debug("Pubblicazione del tag %s non riuscita", uid, exc_info=True)

    # ── notifiche ──────────────────────────────────────────────────────────

    def _camera_lettore(self, device_id: str) -> str:
        return (self.store.devices.get(device_id) or {}).get("camera", "")

    async def _async_notify(self, decision: Decision, event: AccessEvent) -> None:
        valori = {
            "tessera": event.card_name or "tessera sconosciuta",
            # Il nome, non l'entita': nel registro si salva `person.marco`
            # perche' e' quello che non cambia, ma in una notifica si legge
            # «Marco».
            "titolare": nome_persona(self.hass, event.person) or "senza titolare",
            "lettore": self._nome_lettore(event.gate),
            "motivo": REASON_LABELS.get(event.reason, event.reason),
        }
        if decision.result == RESULT_BLACKLIST:
            # L'allarme va alla famiglia, non a chi ha la tessera in mano: al
            # lettore è arrivato un `ko` come tutti gli altri.
            await async_notify(
                self.hass, NOTIFY_BLACKLIST, valori, self._camera_lettore(event.gate)
            )
        elif decision.granted:
            await async_notify(
                self.hass, NOTIFY_ACCESS_OK, valori, self._camera_lettore(event.gate)
            )
        elif decision.result == RESULT_DENIED:
            await async_notify(
                self.hass, NOTIFY_ACCESS_KO, valori, self._camera_lettore(event.gate)
            )

    def _nome_lettore(self, device_id: str) -> str:
        # Senza il registro dei dispositivi qui finiva l'identificativo
        # grezzo: trentadue caratteri esadecimali in mezzo a un messaggio.
        return nome_dispositivo(self.hass, self.store, device_id) or "sconosciuto"

    # ── apprendimento ──────────────────────────────────────────────────────

    async def _async_learn_device(
        self, device: dict[str, Any], device_id: str
    ) -> Decision:
        """Registra il dispositivo che ha appena letto, e dimentica la tessera."""
        self.store.cancel_device_learning()

        if not device_id:
            _LOGGER.warning(
                "Registrazione automatica: lettura senza device_id, ignorata"
            )
            await self._async_respond(device, granted=False)
            return Decision(RESULT_DENIED, "lettura_senza_device_id")

        nuovo = await self.store.async_register_device(device_id)
        await self._async_respond(self.store.devices.get(device_id, {}), granted=True)

        self.hass.bus.async_fire(
            EVENT_DEVICE_REGISTERED,
            {
                "device_id": device_id,
                "nuovo": nuovo,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )
        await async_notify(
            self.hass, NOTIFY_DEVICE, {"lettore": self._nome_lettore(device_id)}
        )
        return Decision(RESULT_ENROLLED, "dispositivo_registrato")

    async def _async_enroll(
        self, uid: str, device: dict[str, Any], device_id: str
    ) -> Decision:
        """Censisce la tessera appena letta.

        La finestra si chiude alla prima lettura: se restasse aperta, chiunque
        passasse una tessera nei secondi successivi se la troverebbe censita.
        """
        await self.enrollment.async_close("tessera letta")

        esistente = self.store.card_by_uid(uid)
        nuova = esistente is None
        if esistente is not None:
            card, motivo = esistente, "tessera già censita"
        else:
            card = await self.store.async_add_card(uid=uid)
            motivo = f"censita come {card.technology_label}"

        # L'evento parte in tutti e due i casi, `nuova` dice quale.
        #
        # Emetterlo solo per le tessere nuove lasciava senza risposta il gesto
        # più frequente dopo il primo giro: ripassare una tessera già in
        # registro. Il modulo faceva la cosa giusta — non la duplicava — ma
        # non lo diceva a nessuno, e da fuori "già censita" e "non ha letto
        # niente" erano lo stesso schermo fermo.
        self.hass.bus.async_fire(
            EVENT_ENROLLED,
            {
                "uid": uid,
                "nuova": nuova,
                "motivo": motivo,
                "card_id": card.id,
                "card_nome": card.label,
                "tecnologia": card.technology,
                "tecnologia_label": card.technology_label,
                "sicurezza": card.security,
                "byte_uid": uid_bytes(uid),
                "lettore": device_id,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        # Il bip di conferma dice a chi è al lettore che la lettura è
        # arrivata: senza, resterebbe lì ad aspettare i bip di timeout.
        await self._async_respond(device, granted=True)

        event = AccessEvent(
            result=RESULT_ENROLLED,
            reason=motivo,
            uid=uid,
            card_id=card.id,
            card_name=card.label,
            card_state=card.state,
            card_security=card.security,
            person=card.person,
            gate=device_id,
            system_state=self.store.system_state,
        )
        self.hass.bus.async_fire(EVENT_ACCESS, event.to_dict())
        await self.store.async_append_log(event)
        await async_notify(
            self.hass,
            NOTIFY_ENROLLED,
            {"tessera": card.label, "motivo": motivo,
             "lettore": self._nome_lettore(device_id)},
        )
        return Decision(RESULT_ENROLLED, motivo, card)

    # ── costruzione dell'evento ────────────────────────────────────────────

    def _build_event(
        self, decision: Decision, uid: str, device_id: str
    ) -> AccessEvent:
        card = decision.card
        return AccessEvent(
            result=decision.result,
            reason=decision.reason,
            uid=uid,
            card_id=card.id if card else None,
            card_name=card.label if card else "",
            card_state=card.state if card else CARD_UNKNOWN,
            card_security=card.security if card else SECURITY_UNKNOWN,
            person=card.person if card else "",
            role=decision.role,
            gate=device_id,
            system_state=self.store.system_state,
        )


def async_get_evaluator(hass: HomeAssistant) -> AccessEvaluator | None:
    return hass.data.get(DOMAIN, {}).get("evaluator")
