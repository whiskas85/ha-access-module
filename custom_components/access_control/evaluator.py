"""Motore di valutazione: decide, risponde, traccia. Non apre.

L'apertura è delegata agli script configurati sul varco. Questo modulo si
occupa di policy e di audit, e chiama gli hook nell'ordine giusto.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CARD_ACTIVE,
    CARD_BLACKLISTED,
    CARD_DISABLED,
    CARD_UNKNOWN,
    DOMAIN,
    EVENT_ACCESS,
    EVENT_DEVICE_REGISTERED,
    EVENT_ENROLLED,
    EVENT_LOCKOUT,
    LOCKOUT_BLOCK,
    PRE_HOOK_TIMEOUT_S,
    REASON_ACTION_FAILED,
    REASON_CARD_BLACKLISTED,
    REASON_CARD_DISABLED,
    REASON_LOCKED_OUT,
    REASON_MASTER_OFF,
    REASON_NO_ACTION_SCRIPT,
    REASON_NO_PERSON,
    REASON_PRE_HOOK_VETO,
    REASON_RATE_LIMIT,
    REASON_ROLE_NOT_ALLOWED,
    REASON_ROLE_NOT_ASSIGNED,
    REASON_SYSTEM_ASLEEP,
    REASON_UNKNOWN_CARD,
    REASON_WEAK_ON_GATE,
    RESULT_BLACKLIST,
    RESULT_DENIED,
    RESULT_ENROLLED,
    RESULT_GRANTED,
    RESULT_LOCKOUT,
    SECURITY_UNKNOWN,
    SECURITY_WEAK,
    STATE_ALLOWED_ROLES,
    WEAK_ALLOWED_GATES,
)
from .coordinator import AccessCoordinator
from .models import AccessEvent, Card, normalize_uid, uid_bytes
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
    ) -> None:
        self.result = result
        self.reason = reason
        self.card = card
        self.role = role

    @property
    def granted(self) -> bool:
        return self.result == RESULT_GRANTED


class AccessEvaluator:
    """Valuta le credenziali e orchestra hook, log, eventi e notifiche."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: AccessStore,
        coordinator: AccessCoordinator,
    ) -> None:
        self.hass = hass
        self.store = store
        self.coordinator = coordinator
        # Timestamp delle letture recenti, per il rate limit lato Home
        # Assistant. Quello nel lettore non basta: un firmware sostituito lo
        # aggirerebbe inondando l'API, e il lettore sta fuori casa.
        self._recent: deque[float] = deque(maxlen=64)

    # ── ingresso principale ────────────────────────────────────────────────

    async def async_handle_scan(
        self, raw_uid: str, gate_id: str = "", device_id: str = ""
    ) -> Decision:
        """Valuta una lettura e porta a termine tutto ciò che ne consegue."""
        uid = normalize_uid(raw_uid)
        gate_id = gate_id or next(iter(self.store.gates), "ingresso")
        gate = self.store.gate(gate_id) or {}

        # Chi ha letto è un lettore: si annota sempre, anche quando la lettura
        # viene poi negata. Serve a popolare l'elenco dei lettori da cui si
        # scelgono i varchi, e non dipende dall'esito.
        if device_id:
            await self.store.async_note_reader(device_id)

        # Registrazione automatica del LETTORE. Va per prima, e soprattutto
        # **scarta la tessera**: qui interessa solo sapere quale dispositivo
        # ha letto. Chi si fa riconoscere un lettore usa la prima tessera che
        # ha in tasca, e quella tessera non deve finire nel registro né essere
        # valutata — sarebbe un censimento che nessuno ha chiesto.
        if self.store.device_learning_active:
            return await self._async_learn_device(gate, device_id)

        # In enrollment la lettura viene censita, non valutata. Si controlla
        # per primo: durante l'enrollment non ha senso negare una tessera
        # perché "non censita" — è esattamente ciò che stiamo rimediando.
        # Vale solo per il varco su cui il censimento è stato aperto: una
        # lettura da un altro lettore resta una lettura normale.
        if self.store.enrollment_accepts(gate_id):
            return await self._async_enroll(uid, gate, gate_id, device_id)

        decision = self._decide(uid, gate_id)

        # Il pre-hook partecipa alla decisione, quindi gira prima della
        # risposta al lettore — ma con un budget stretto, perché la risposta
        # deve arrivare entro il timeout del dispositivo.
        if decision.granted:
            allowed = await self._async_run_pre_hook(gate, decision, uid, gate_id)
            if not allowed:
                decision = Decision(
                    RESULT_DENIED, REASON_PRE_HOOK_VETO, decision.card, decision.role
                )

        # Rispondere SEMPRE, anche negando, e prima di attuare.
        await self._async_respond(gate, granted=decision.granted)

        event = self._build_event(decision, uid, gate_id)
        self.hass.bus.async_fire(EVENT_ACCESS, event.to_dict())
        await self.store.async_append_log(event)

        if decision.granted:
            await self.store.async_reset_failures()
            if decision.card is not None:
                decision.card.register_use()
                await self.store.async_save_and_notify()
        else:
            await self._async_after_failure(decision, event)

        await self._async_notify(decision, event)

        if decision.granted:
            # L'attuazione vera avviene qui, dopo la risposta al lettore: uno
            # script lento non deve tradursi nel pattern "non raggiungibile".
            await self._async_run_action(gate, event)

        return decision

    # ── registrazione automatica di un lettore ─────────────────────────────

    async def _async_learn_device(
        self, gate: dict[str, Any], device_id: str
    ) -> Decision:
        """Registra il dispositivo che ha appena letto, e dimentica la tessera.

        Nessuna riga nel registro accessi: non è avvenuto un accesso, né un
        tentativo. È successo che un lettore si è presentato.
        """
        self.store.cancel_device_learning()

        if not device_id:
            # Una lettura senza device_id non insegna niente: succede con
            # sorgenti che non dichiarano da dove arrivano.
            _LOGGER.warning(
                "Registrazione automatica: lettura senza device_id, ignorata"
            )
            await self._async_respond(gate, granted=False)
            await self._async_send_notification(
                "⚠️ Lettore non riconosciuto",
                "La lettura non dichiara da quale dispositivo arriva: "
                "aggiungilo dall'elenco invece che automaticamente.",
            )
            return Decision(RESULT_DENIED, "lettura_senza_device_id")

        nuovo = await self.store.async_register_device(device_id)
        await self._async_respond(gate, granted=True)

        self.hass.bus.async_fire(
            EVENT_DEVICE_REGISTERED,
            {
                "device_id": device_id,
                "nuovo": nuovo,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )
        await self._async_send_notification(
            "📟 Lettore registrato" if nuovo else "📟 Lettore già registrato",
            "Ora puoi associarlo a un varco. La tessera usata per il "
            "riconoscimento è stata ignorata.",
        )
        return Decision(RESULT_ENROLLED, "dispositivo_registrato")

    # ── enrollment ─────────────────────────────────────────────────────────

    async def _async_enroll(
        self, uid: str, gate: dict[str, Any], gate_id: str, device_id: str = ""
    ) -> Decision:
        """Censisce la tessera appena letta.

        La finestra si chiude alla prima lettura, riuscita o no: se restasse
        aperta, chiunque passasse una tessera nei secondi successivi se la
        troverebbe censita. Una modalità che accetta credenziali nuove deve
        durare il minimo indispensabile.
        """
        self.store.cancel_enrollment()

        # Il censimento NON tocca la configurazione dei lettori. Censire una
        # tessera e aggiungere un dispositivo sono due cose diverse: legare
        # qui il varco al lettore significherebbe cambiare l'impianto come
        # effetto collaterale di un gesto che riguarda una tessera. Se il
        # lettore va aggiunto, lo si fa dalla scheda Dispositivi.

        esistente = self.store.card_by_uid(uid)
        if esistente is not None:
            card, motivo = esistente, "tessera già censita"
        else:
            card = await self.store.async_add_card(uid=uid)
            motivo = f"censita come {card.technology_label}"
            # Tutto quello che serve a valle per fare qualcosa di questa
            # tessera senza doverla ricercare nel registro.
            self.hass.bus.async_fire(
                EVENT_ENROLLED,
                {
                    "uid": uid,
                    "card_id": card.id,
                    "card_nome": card.label,
                    "tecnologia": card.technology,
                    "tecnologia_label": card.technology_label,
                    "sicurezza": card.security,
                    "byte_uid": uid_bytes(uid),
                    "varco": gate_id,
                    "stato_sistema": self.store.system_state,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

        # Il bip di conferma dice a chi sta davanti al lettore che la lettura
        # è arrivata: senza, resterebbe lì ad aspettare i tre bip di timeout.
        await self._async_respond(gate, granted=True)

        event = AccessEvent(
            result=RESULT_ENROLLED,
            reason=motivo,
            uid=uid,
            card_id=card.id,
            card_name=card.label,
            card_state=card.state,
            card_security=card.security,
            person=card.person,
            gate=gate_id,
            system_state=self.store.system_state,
        )
        self.hass.bus.async_fire(EVENT_ACCESS, event.to_dict())
        await self.store.async_append_log(event)

        await self._async_send_notification(
            "🆕 Tessera censita",
            f"{card.label} — {motivo}. "
            "Non apre nulla finché non le assegni un titolare.",
        )
        return Decision(RESULT_ENROLLED, motivo, card)

    # ── decisione ──────────────────────────────────────────────────────────

    def _decide(self, uid: str, gate_id: str) -> Decision:
        card = self.store.card_by_uid(uid)
        role = self.store.role_of(card.person) if card and card.person else ""

        # Il lockout va valutato per primo, ma solo in modalità `blocca`:
        # in modalità `segnala` conta e notifica senza fermare nessuno.
        if (
            self.store.is_locked_out
            and self.store.settings.get("lockout_mode") == LOCKOUT_BLOCK
        ):
            return Decision(RESULT_LOCKOUT, REASON_LOCKED_OUT, card, role)

        if self._rate_limited():
            return Decision(RESULT_DENIED, REASON_RATE_LIMIT, card, role)

        # La blacklist si riconosce sempre, anche a master spento: è
        # l'informazione che interessa di più e va comunque tracciata.
        if card is not None and card.state == CARD_BLACKLISTED:
            return Decision(RESULT_BLACKLIST, REASON_CARD_BLACKLISTED, card, role)

        if not self.coordinator.master_on:
            return Decision(RESULT_DENIED, REASON_MASTER_OFF, card, role)

        if card is None:
            return Decision(RESULT_DENIED, REASON_UNKNOWN_CARD)

        if card.state == CARD_DISABLED:
            return Decision(RESULT_DENIED, REASON_CARD_DISABLED, card, role)
        if card.state != CARD_ACTIVE:
            return Decision(RESULT_DENIED, REASON_CARD_DISABLED, card, role)

        if not card.person:
            return Decision(RESULT_DENIED, REASON_NO_PERSON, card, role)

        if not self.coordinator.is_armed:
            return Decision(RESULT_DENIED, REASON_SYSTEM_ASLEEP, card, role)

        # Titolare senza ruolo: non è un adulto per default, è una decisione
        # che manca. Si nega e si dice quale, invece di indovinare.
        if not role:
            return Decision(RESULT_DENIED, REASON_ROLE_NOT_ASSIGNED, card, role)

        allowed_roles = STATE_ALLOWED_ROLES.get(self.store.system_state, ())
        if role not in allowed_roles:
            return Decision(RESULT_DENIED, REASON_ROLE_NOT_ALLOWED, card, role)

        # Una credenziale debole non apre ovunque: l'UID di una MIFARE Classic
        # si clona in trenta secondi, quindi vale solo sul varco pedonale.
        if (
            card.security in (SECURITY_WEAK, SECURITY_UNKNOWN)
            and gate_id not in WEAK_ALLOWED_GATES
        ):
            return Decision(RESULT_DENIED, REASON_WEAK_ON_GATE, card, role)

        return Decision(RESULT_GRANTED, "", card, role)

    def _rate_limited(self) -> bool:
        window = float(self.store.settings.get("rate_limit_window_s") or 10)
        maximum = int(self.store.settings.get("rate_limit_max") or 3)
        now = time.monotonic()
        while self._recent and now - self._recent[0] > window:
            self._recent.popleft()
        self._recent.append(now)
        return len(self._recent) > maximum

    # ── risposta al lettore ────────────────────────────────────────────────

    async def _async_respond(self, gate: dict[str, Any], *, granted: bool) -> None:
        """Risponde al dispositivo.

        Il feedback è binario e non rivela mai il motivo del diniego: tessera
        sconosciuta, disabilitata, in blacklist, valida fuori finestra e
        lettori bloccati producono tutti lo stesso `ko`. Un feedback
        differenziato direbbe a chi ha in mano una tessera trovata se quella
        tessera è censita, e se vale la pena tornare a un altro orario.
        """
        service = gate.get("reader_service")
        if not service or "." not in service:
            return

        domain, _, name = service.partition(".")
        field = gate.get("reader_field") or "esito"
        value = (
            gate.get("reader_ok_value", "ok")
            if granted
            else gate.get("reader_ko_value", "ko")
        )
        try:
            await self.hass.services.async_call(
                domain, name, {field: value}, blocking=True
            )
        except Exception:
            _LOGGER.exception("Risposta al lettore fallita (%s)", service)

    # ── hook ───────────────────────────────────────────────────────────────

    async def _async_run_pre_hook(
        self,
        gate: dict[str, Any],
        decision: Decision,
        uid: str,
        gate_id: str,
    ) -> bool:
        """Esegue il pre-hook. Ritorna False se l'apertura va vietata.

        Il veto si esprime restituendo `{"allow": false}` da uno `stop:` con
        `response_variable`. Uno script che non restituisce nulla consente.
        """
        script = gate.get("pre_hook")
        if not script:
            return True

        payload = self._build_event(decision, uid, gate_id).to_dict()
        fail_closed = bool(gate.get("pre_hook_fail_closed"))

        try:
            async with asyncio.timeout(PRE_HOOK_TIMEOUT_S):
                response = await self._async_call_script(
                    script, payload, return_response=True
                )
        except TimeoutError:
            _LOGGER.warning(
                "Pre-hook %s oltre %ss: %s",
                script,
                PRE_HOOK_TIMEOUT_S,
                "apertura vietata" if fail_closed else "ignorato",
            )
            return not fail_closed
        except Exception:
            _LOGGER.exception("Pre-hook %s fallito", script)
            return not fail_closed

        vetoed = isinstance(response, dict) and response.get("allow") is False
        return not vetoed

    async def _async_run_action(
        self, gate: dict[str, Any], event: AccessEvent
    ) -> None:
        """Chiama lo script di apertura, poi il post-hook."""
        script = gate.get("action_script")
        payload = event.to_dict()

        if not script:
            # Nessuno script configurato: il modulo non apre "di default".
            _LOGGER.error(
                "Varco %s senza script di apertura: nulla è stato aperto",
                event.gate,
            )
            await self._async_log_action_outcome(event, REASON_NO_ACTION_SCRIPT)
            return

        try:
            await self._async_call_script(script, payload)
            outcome = "ok"
        except Exception:
            _LOGGER.exception("Script di apertura %s fallito", script)
            outcome = REASON_ACTION_FAILED
            await self._async_log_action_outcome(event, outcome)

        post = gate.get("post_hook")
        if post:
            try:
                await self._async_call_script(post, {**payload, "azione": outcome})
            except Exception:
                _LOGGER.exception("Post-hook %s fallito", post)

    async def _async_call_script(
        self,
        entity_id: str,
        payload: dict[str, Any],
        *,
        return_response: bool = False,
    ) -> Any:
        """Chiama uno script passandogli l'evento come variabili.

        Si usa `script.<nome>` e non `script.turn_on` perché serve attendere
        la fine: `turn_on` ritorna subito e renderebbe impossibile sia il veto
        del pre-hook sia il rilevamento di un'apertura fallita.
        """
        name = entity_id.split(".", 1)[-1]
        return await self.hass.services.async_call(
            "script",
            name,
            {"accesso": payload},
            blocking=True,
            return_response=return_response,
        )

    async def _async_log_action_outcome(
        self, event: AccessEvent, outcome: str
    ) -> None:
        self.hass.bus.async_fire(
            EVENT_ACCESS, {**event.to_dict(), "esito_azione": outcome}
        )

    # ── conseguenze di un fallimento ───────────────────────────────────────

    async def _async_after_failure(
        self, decision: Decision, event: AccessEvent
    ) -> None:
        streak = await self.store.async_register_failure()
        threshold = int(self.store.settings.get("lockout_threshold") or 5)
        if streak < threshold or self.store.is_locked_out:
            return

        minutes = int(self.store.settings.get("lockout_duration_min") or 15)
        mode = self.store.settings.get("lockout_mode")
        await self.store.async_lock_readers(minutes)

        self.hass.bus.async_fire(
            EVENT_LOCKOUT,
            {
                "tentativi": streak,
                "modalita": mode,
                "minuti": minutes,
                "varco": event.gate,
            },
        )
        await self._async_send_notification(
            "🚨 Lettori in allarme",
            f"{streak} letture rifiutate di fila. "
            + (
                f"Lettori bloccati per {minutes} minuti."
                if mode == LOCKOUT_BLOCK
                else "Le credenziali valide continuano a funzionare."
            ),
            high_priority=True,
        )

    # ── notifiche ──────────────────────────────────────────────────────────

    async def _async_notify(self, decision: Decision, event: AccessEvent) -> None:
        settings = self.store.settings

        if decision.result == RESULT_BLACKLIST:
            # L'allarme va alla famiglia, non a chi ha la tessera in mano:
            # il feedback al lettore è rimasto un `ko` come tutti gli altri.
            await self._async_send_notification(
                "🚨 Tessera in blacklist",
                f"È stata usata {event.card_name or 'una tessera revocata'} "
                f"al varco {event.gate}.",
                high_priority=True,
            )
            return

        if decision.granted:
            if settings.get("notify_on_entry"):
                await self._async_send_notification(
                    "🔓 Accesso consentito",
                    f"{event.card_name} — {event.person or 'senza titolare'} "
                    f"({event.system_state})",
                )
            return

        if settings.get("notify_on_denied"):
            await self._async_send_notification(
                "⛔ Accesso negato",
                f"{event.card_name or 'tessera sconosciuta'} — "
                f"motivo: {event.reason}",
            )

    async def _async_send_notification(
        self, title: str, message: str, *, high_priority: bool = False
    ) -> None:
        service = self.store.settings.get("notify_service") or ""
        if "." not in service:
            return
        domain, _, name = service.partition(".")

        data: dict[str, Any] = {}
        camera = self.store.settings.get("camera_entity")
        if camera:
            data["image"] = f"/api/camera_proxy/{camera}"
        if high_priority:
            data.update({"ttl": 0, "priority": "high"})

        payload: dict[str, Any] = {"title": title, "message": message}
        if data:
            payload["data"] = data

        try:
            await self.hass.services.async_call(domain, name, payload, blocking=False)
        except Exception:
            _LOGGER.exception("Notifica fallita (%s)", service)

    # ── costruzione dell'evento ────────────────────────────────────────────

    def _build_event(
        self, decision: Decision, uid: str, gate_id: str
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
            gate=gate_id,
            system_state=self.store.system_state,
        )


def async_get_evaluator(hass: HomeAssistant) -> AccessEvaluator | None:
    return hass.data.get(DOMAIN, {}).get("evaluator")
