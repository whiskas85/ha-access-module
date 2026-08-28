"""Persistenza di Controllo Accessi.

Tiene impostazioni, registro tessere, lettori, varchi, finestre, notifiche e
registro accessi. È l'unico posto che scrive su disco.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CARD_ACTIVE,
    CARD_BLACKLISTED,
    CARD_DISABLED,
    CONF_CARDS,
    CONF_DEVICES,
    CONF_GATES,
    CONF_LOG,
    CONF_PEOPLE,
    CONF_NOTIFICATIONS,
    CONF_SETTINGS,
    CONF_WINDOWS,
    DEFAULT_DEVICE,
    DEFAULT_GATE,
    DEFAULT_NOTIFICATIONS,
    DEFAULT_SETTINGS,
    DEFAULT_WINDOW,
    ESPHOME_DOMAIN,
    EVENT_UPDATED,
    LOCAL_PERSON_PREFIX,
    RESULT_ALARM,
    RESULT_BLACKLIST,
    RESULT_DENIED,
    ROLE_NONE,
    ROLES,
    SECURITY_ALARM,
    SECURITY_NORMAL,
    SIGNAL_STATE_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUFFIX_ENABLE_SWITCH,
    SUFFIX_ENROLL_SERVICE,
    SUFFIX_READER_SERVICE,
    SUFFIX_TAMPER_SENSOR,
)
from .models import AccessEvent, Card, detect_technology, normalize_uid

_LOGGER = logging.getLogger(__name__)


def _prefisso_nodo(hass: HomeAssistant, device_id: str) -> str:
    """Il nome del nodo ESPHome come compare nei suoi servizi.

    `rfid-ingresso` espone `esphome.rfid_ingresso_esito_accesso`: e' il nome
    del dispositivo con i trattini sostituiti. Si passa dal nome e non
    dall'identificativo perche' il device_id di Home Assistant non contiene
    nessuna traccia del nome del nodo.
    """
    device = dr.async_get(hass).async_get(device_id)
    nome = getattr(device, "name", "") if device else ""
    return slugify(nome) if nome else ""


def _nuovo_id() -> str:
    return uuid.uuid4().hex[:8]


class AccessStore:
    """Stato condiviso fra entità, pannello e motore di valutazione."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.notifications: dict[str, Any] = _copia_notifiche(DEFAULT_NOTIFICATIONS)
        self.cards: dict[str, Card] = {}
        # Le persone create qui dentro, per chi non e' un'entita' di HA.
        self.people: dict[str, dict[str, Any]] = {}
        self.gates: dict[str, dict[str, Any]] = {}
        self.windows: dict[str, dict[str, Any]] = {}
        self.log: list[AccessEvent] = []

        # Stato di AUTORIZZAZIONE, scritto dal coordinator.
        self.system_state: str = ""
        self.state_reason: str = ""

        # Stato di SICUREZZA, scritto dal motore. Si esce solo a mano, quindi
        # è persistito: un riavvio non deve regalare un impianto riaperto.
        self.security_state: str = SECURITY_NORMAL
        self.alarm_reason: str = ""
        self.alarm_since: str | None = None
        self.failure_streak: int = 0

        # Due elenchi distinti, e la distinzione conta.
        # `readers` è ciò che si è OSSERVATO: chi ha emesso una lettura.
        self.readers: dict[str, dict[str, Any]] = {}
        # `devices` è ciò che è stato REGISTRATO: i lettori dell'impianto.
        self.devices: dict[str, dict[str, Any]] = {}

        # Modalità di apprendimento, non persistite di proposito: se Home
        # Assistant riparte mentre una è aperta, deve ripartire chiusa.
        self.enrollment_until = None
        self.enrollment_device: str = ""
        self.device_learning_until = None

    # ── caricamento e salvataggio ──────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}

        # Le impostazioni si fondono con i default invece di sostituirli: un
        # aggiornamento che aggiunge una chiave non deve lasciare None in giro
        # per le installazioni esistenti.
        self.settings = {**DEFAULT_SETTINGS, **(data.get(CONF_SETTINGS) or {})}
        self.notifications = _fondi_notifiche(data.get(CONF_NOTIFICATIONS) or {})

        self.cards = {}
        for raw in data.get(CONF_CARDS) or []:
            try:
                card = Card.from_dict(raw)
            except (TypeError, ValueError):
                _LOGGER.warning("Tessera illeggibile nello store, ignorata: %s", raw)
                continue
            if card.uid:
                self.cards[card.id] = card

        self.people = {
            p["id"]: p for p in (data.get(CONF_PEOPLE) or []) if p.get("id")
        }

        self.gates = {
            g["id"]: {**DEFAULT_GATE, **g}
            for g in (data.get(CONF_GATES) or [])
            if g.get("id")
        }
        self.windows = {
            w["id"]: {**DEFAULT_WINDOW, **w}
            for w in (data.get(CONF_WINDOWS) or [])
            if w.get("id")
        }

        self.devices = {
            k: {**DEFAULT_DEVICE, **v}
            for k, v in (data.get(CONF_DEVICES) or {}).items()
        }
        self.readers = dict(data.get("readers") or {})
        self.log = [AccessEvent.from_dict(r) for r in (data.get(CONF_LOG) or [])]

        sicurezza = data.get("security") or {}
        self.security_state = sicurezza.get("stato", SECURITY_NORMAL)
        self.alarm_reason = sicurezza.get("motivo", "")
        self.alarm_since = sicurezza.get("dal")
        self.failure_streak = int(sicurezza.get("fallimenti") or 0)

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                CONF_SETTINGS: self.settings,
                CONF_NOTIFICATIONS: self.notifications,
                CONF_CARDS: [c.to_dict() for c in self.cards.values()],
                CONF_PEOPLE: list(self.people.values()),
                CONF_GATES: list(self.gates.values()),
                CONF_WINDOWS: list(self.windows.values()),
                CONF_DEVICES: self.devices,
                CONF_LOG: [e.to_dict() for e in self.log],
                "readers": self.readers,
                "security": {
                    "stato": self.security_state,
                    "motivo": self.alarm_reason,
                    "dal": self.alarm_since,
                    "fallimenti": self.failure_streak,
                },
            }
        )

    async def async_save_and_notify(self) -> None:
        await self.async_save()
        self.notify()

    def notify(self) -> None:
        """Sveglia chi guarda: entità e pannello leggono lo stesso stato.

        Due canali perché i destinatari stanno in due mondi diversi. Il
        dispatcher arriva alle entità, che sono qui dentro. Il pannello no:
        vive nel browser, e senza l'evento sul bus può solo richiedere lo
        stato a intervalli — cioè mostrare per qualche secondo un mondo che
        non esiste più, proprio mentre chi guarda ha appena passato la
        tessera e aspetta di vedere l'effetto.
        """
        async_dispatcher_send(self.hass, SIGNAL_STATE_CHANGED)
        self.hass.bus.async_fire(EVENT_UPDATED)

    # ── impostazioni ───────────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        self.settings.update(changes)
        await self.async_save_and_notify()

    async def async_update_notifications(self, changes: dict[str, Any]) -> None:
        if "master" in changes:
            self.notifications["master"] = bool(changes["master"])
        if "service" in changes:
            self.notifications["service"] = changes["service"]
        for tipo, conf in (changes.get("tipi") or {}).items():
            if tipo in self.notifications["tipi"]:
                self.notifications["tipi"][tipo].update(conf)
        await self.async_save_and_notify()

    async def async_add_person(self, nome: str, note: str = "") -> dict[str, Any]:
        """Crea una persona che non esiste in Home Assistant.

        Serve a chi ha le chiavi ma non l'app: la nonna, chi viene a fare le
        pulizie. Da qui in poi vale come qualunque altro titolare — prende un
        ruolo, e le finestre la fanno entrare in base a quello.

        L'identificativo e' inventato qui e non cambia mai piu': e' quello che
        le tessere e il registro si portano dietro, e rinominare una persona
        non deve far perdere il filo di chi e' entrato l'anno scorso.
        """
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("Serve un nome")

        persona = {
            "id": f"{LOCAL_PERSON_PREFIX}{_nuovo_id()}",
            "nome": nome,
            "note": note.strip(),
            "creata": dt_util.utcnow().isoformat(),
        }
        self.people[persona["id"]] = persona
        await self.async_save_and_notify()
        return persona

    async def async_update_person(
        self, person_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        persona = self.people.get(person_id)
        if persona is None:
            raise KeyError(person_id)
        for campo in ("nome", "note"):
            if campo in changes:
                persona[campo] = str(changes[campo]).strip()
        if not persona["nome"]:
            raise ValueError("Serve un nome")
        await self.async_save_and_notify()
        return persona

    async def async_remove_person(self, person_id: str) -> None:
        """Toglie una persona creata qui, e libera le sue tessere.

        Le tessere non si cancellano: tornano senza titolare, che e' uno stato
        gia' previsto e ben visibile. Cancellarle silenziosamente sarebbe il
        modo piu' rapido per perdere il ricordo di una tessera che sta ancora
        in giro in una tasca.
        """
        if self.people.pop(person_id, None) is None:
            raise KeyError(person_id)

        for card in self.cards.values():
            if card.person == person_id:
                card.person = ""

        ruoli = dict(self.settings.get("person_roles") or {})
        if ruoli.pop(person_id, None) is not None:
            self.settings["person_roles"] = ruoli

        await self.async_save_and_notify()

    def person_name(self, person_id: str) -> str:
        """Il nome di una persona creata qui, se e' una di quelle."""
        return (self.people.get(person_id) or {}).get("nome", "")

    def role_of(self, person: str) -> str:
        """Ruolo del titolare, stringa vuota se non è stato assegnato.

        Non si torna un ruolo di comodo per chi non è configurato. Trattare un
        titolare sconosciuto come adulto sarebbe fail-open: gli darebbe i
        permessi più ampi proprio perché nessuno ha detto chi è.
        """
        return (self.settings.get("person_roles") or {}).get(person) or ROLE_NONE

    async def async_set_person_role(self, person: str, role: str) -> None:
        if role and role not in ROLES:
            raise ValueError(f"Ruolo non valido: {role}")
        roles = dict(self.settings.get("person_roles") or {})
        if role:
            roles[person] = role
        else:
            roles.pop(person, None)
        self.settings["person_roles"] = roles
        await self.async_save_and_notify()

    # ── registro tessere ───────────────────────────────────────────────────

    def card_by_uid(self, uid: str) -> Card | None:
        target = normalize_uid(uid)
        if not target:
            return None
        for card in self.cards.values():
            if card.uid == target:
                return card
        return None

    def card_by_id(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    async def async_add_card(
        self,
        uid: str,
        name: str = "",
        person: str = "",
        technology: str = "",
        note: str = "",
    ) -> Card:
        """Censisce una tessera. Se l'UID esiste già ne aggiorna i dati."""
        normalized = normalize_uid(uid)
        if not normalized:
            raise ValueError("UID vuoto")

        existing = self.card_by_uid(normalized)
        if existing is not None:
            existing.name = name or existing.name
            existing.person = person or existing.person
            existing.technology = technology or existing.technology
            existing.note = note or existing.note
            await self.async_save_and_notify()
            return existing

        card = Card(
            uid=normalized,
            name=name or f"Tessera {normalized[-5:]}",
            person=person,
            technology=technology or detect_technology(normalized),
            note=note,
        )
        self.cards[card.id] = card
        await self.async_save_and_notify()
        return card

    async def async_update_card(self, card_id: str, changes: dict[str, Any]) -> Card:
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        for key in ("name", "person", "technology", "note"):
            if key in changes:
                setattr(card, key, changes[key])
        if "state" in changes:
            await self.async_set_card_state(card_id, changes["state"], save=False)
        await self.async_save_and_notify()
        return card

    async def async_set_card_state(
        self, card_id: str, state: str, *, save: bool = True
    ) -> Card:
        """Attiva / disabilita / mette in blacklist una tessera."""
        if state not in (CARD_ACTIVE, CARD_DISABLED, CARD_BLACKLISTED):
            raise ValueError(f"Stato tessera non valido: {state}")
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.state = state
        if save:
            await self.async_save_and_notify()
        return card

    async def async_assign_person(self, card_id: str, person: str) -> Card:
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.person = person or ""
        await self.async_save_and_notify()
        return card

    async def async_remove_card(self, card_id: str) -> None:
        if self.cards.pop(card_id, None) is not None:
            await self.async_save_and_notify()

    # ── varchi ─────────────────────────────────────────────────────────────

    def gate(self, gate_id: str) -> dict[str, Any] | None:
        return self.gates.get(gate_id)

    async def async_upsert_gate(self, gate: dict[str, Any]) -> dict[str, Any]:
        gate_id = gate.get("id") or _nuovo_id()
        current = {**DEFAULT_GATE, **self.gates.get(gate_id, {}), **gate}
        current["id"] = gate_id
        self.gates[gate_id] = current
        await self.async_save_and_notify()
        return current

    async def async_remove_gate(self, gate_id: str) -> None:
        if self.gates.pop(gate_id, None) is not None:
            await self.async_save_and_notify()

    # ── finestre ───────────────────────────────────────────────────────────

    async def async_upsert_window(self, window: dict[str, Any]) -> dict[str, Any]:
        window_id = window.get("id") or _nuovo_id()
        current = {**DEFAULT_WINDOW, **self.windows.get(window_id, {}), **window}
        current["id"] = window_id
        self.windows[window_id] = current
        await self.async_save_and_notify()
        return current

    async def async_remove_window(self, window_id: str) -> None:
        if self.windows.pop(window_id, None) is not None:
            await self.async_save_and_notify()

    # ── lettori: osservati e registrati ────────────────────────────────────

    async def async_note_reader(self, device_id: str) -> bool:
        """Registra che questo dispositivo ha letto qualcosa.

        È l'unico criterio sensato per dire "qui c'è un lettore NFC": né
        l'integrazione né il modello lo dichiarano. Chi legge è un lettore.
        """
        if not device_id:
            return False
        ora = dt_util.utcnow().isoformat()
        nuovo = device_id not in self.readers
        voce = self.readers.setdefault(
            device_id, {"prima": ora, "ultima": ora, "letture": 0}
        )
        voce["ultima"] = ora
        voce["letture"] = int(voce.get("letture") or 0) + 1
        # `_and_notify`, non il solo salvataggio: il contatore delle letture e
        # l'ora dell'ultima sono in mezzo alla pagina, e sono la prima cosa
        # che si guarda dopo aver passato una tessera. Salvarli senza dirlo a
        # nessuno li lasciava fermi sullo schermo fino al giro successivo.
        await self.async_save_and_notify()
        return nuovo

    def seed_readers(self, coppie: list[tuple[str, str | None]]) -> None:
        """Semina i lettori dai tag già esistenti, senza aspettare una lettura."""
        for device_id, quando in coppie:
            if not device_id or device_id in self.readers:
                continue
            ora = quando or dt_util.utcnow().isoformat()
            self.readers[device_id] = {"prima": ora, "ultima": ora, "letture": 0}

    async def async_register_device(
        self, device_id: str, nome: str = "", note: str = ""
    ) -> bool:
        if not device_id:
            raise ValueError("device_id vuoto")
        nuovo = device_id not in self.devices
        voce = self.devices.setdefault(
            device_id, {**DEFAULT_DEVICE, "aggiunto": dt_util.utcnow().isoformat()}
        )
        if nome:
            voce["nome"] = nome
        if note:
            voce["note"] = note
        await self.async_save_and_notify()
        return nuovo

    async def async_autofill_services(self, device_id: str) -> dict[str, Any]:
        """Indovina i servizi del lettore, se non sono ancora stati scelti.

        Il modulo risponde SEMPRE al lettore, anche negando: se tace, chi e'
        alla porta sente il pattern "non raggiungibile" e crede che il sistema
        sia guasto quando invece aveva solo deciso di no. Quella risposta pero'
        passa da un campo di configurazione che nasce vuoto, e un campo
        obbligatorio vuoto prima o poi si dimentica — col sintomo peggiore
        possibile, perche' non somiglia affatto a una dimenticanza.

        Qui il vuoto si riempie da solo: fra le azioni ESPHome esposte a Home
        Assistant si cerca quella che finisce col suffisso giusto. Se ce n'e'
        una sola, e' quella. Se ce n'e' piu' d'una si sceglie il nodo il cui
        nome corrisponde al dispositivo, e nel dubbio non si tocca niente:
        indovinare il lettore sbagliato manderebbe l'esito di una porta a
        un'altra.

        Vale per tutti i campi che collegano il modulo al lettore: la
        risposta acustica, la spia del censimento, l'interruttore di lettura
        che l'allarme spegne e il contatto di manomissione. Nessuno ha un
        default sensato, e tutti falliscono in silenzio.

        I primi due sono azioni e si cercano fra i servizi; gli altri due sono
        entita' e si cercano fra le entita' di QUEL dispositivo, dove
        l'omonimia non esiste e non c'e' niente da indovinare.

        Non sovrascrive mai un valore gia' scritto: se qualcuno ha configurato
        il campo a mano, ha ragione lui.
        """
        device = self.devices.get(device_id)
        if device is None:
            return {}

        mancanti = [
            (campo, suffisso)
            for campo, suffisso in (
                ("reader_service", SUFFIX_READER_SERVICE),
                ("enroll_service", SUFFIX_ENROLL_SERVICE),
            )
            if not device.get(campo)
        ]
        cambiato = False

        # L'interruttore di lettura e' un'entita' e non un'azione, quindi si
        # cerca fra le entita' di QUESTO dispositivo: li' dentro l'omonimia
        # non esiste, e non serve indovinare niente.
        da_cercare = [
            ("enable_switch", "switch.", SUFFIX_ENABLE_SWITCH),
            ("tamper_sensor", "binary_sensor.", SUFFIX_TAMPER_SENSOR),
        ]
        if any(not device.get(campo) for campo, _, _ in da_cercare):
            voci = er.async_entries_for_device(er.async_get(self.hass), device_id)
            for campo, dominio, suffisso in da_cercare:
                if device.get(campo):
                    continue
                candidati = [
                    voce.entity_id
                    for voce in voci
                    if voce.entity_id.startswith(dominio)
                    and voce.entity_id.endswith(suffisso)
                ]
                if len(candidati) == 1:
                    device[campo] = candidati[0]
                    cambiato = True
                    _LOGGER.info(
                        "Lettore %s: %s impostato a %s",
                        device_id,
                        campo,
                        candidati[0],
                    )

        if not mancanti:
            if cambiato:
                await self.async_save_and_notify()
            return device

        disponibili = list(
            self.hass.services.async_services().get(ESPHOME_DOMAIN, {})
        )
        atteso = _prefisso_nodo(self.hass, device_id)

        for campo, suffisso in mancanti:
            candidati = [s for s in disponibili if s.endswith(suffisso)]
            scelto = ""
            if atteso:
                scelto = next(
                    (s for s in candidati if s == f"{atteso}{suffisso}"), ""
                )
            if not scelto and len(candidati) == 1:
                scelto = candidati[0]
            if scelto:
                device[campo] = f"{ESPHOME_DOMAIN}.{scelto}"
                cambiato = True
                _LOGGER.info(
                    "Lettore %s: %s impostato a %s",
                    device_id,
                    campo,
                    device[campo],
                )

        if cambiato:
            await self.async_save_and_notify()
        return device

    async def async_update_device(
        self, device_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        device = self.devices.get(device_id)
        if device is None:
            raise KeyError(device_id)
        device.update(changes)
        await self.async_save_and_notify()
        return device

    async def async_unregister_device(self, device_id: str) -> None:
        if self.devices.pop(device_id, None) is not None:
            await self.async_save_and_notify()

    # ── apprendimento ──────────────────────────────────────────────────────

    @property
    def enrollment_active(self) -> bool:
        return bool(
            self.enrollment_until and dt_util.utcnow() < self.enrollment_until
        )

    @property
    def enrollment_seconds_left(self) -> int:
        if not self.enrollment_active:
            return 0
        return max(0, int((self.enrollment_until - dt_util.utcnow()).total_seconds()))

    def start_enrollment(self, seconds: int, device_id: str = "") -> None:
        # Le due modalità si escludono: una lettura non può essere insieme
        # "censisci questa tessera" e "scarta questa tessera, mi serve il
        # lettore".
        self.device_learning_until = None
        self.enrollment_device = device_id
        self.enrollment_until = dt_util.utcnow() + timedelta(seconds=seconds)
        self.notify()

    def cancel_enrollment(self) -> None:
        self.enrollment_until = None
        self.enrollment_device = ""
        self.notify()

    def enrollment_accepts(self, device_id: str) -> bool:
        """Questa lettura va censita, o valutata normalmente?

        Solo da un lettore **registrato**: una lettura da un dispositivo che
        non fa parte dell'impianto non deve poter aggiungere credenziali.
        """
        if not self.enrollment_active or device_id not in self.devices:
            return False
        return not self.enrollment_device or self.enrollment_device == device_id

    @property
    def device_learning_active(self) -> bool:
        return bool(
            self.device_learning_until
            and dt_util.utcnow() < self.device_learning_until
        )

    @property
    def device_learning_seconds_left(self) -> int:
        if not self.device_learning_active:
            return 0
        return max(
            0, int((self.device_learning_until - dt_util.utcnow()).total_seconds())
        )

    def start_device_learning(self, seconds: int) -> None:
        self.enrollment_until = None
        self.enrollment_device = ""
        self.device_learning_until = dt_util.utcnow() + timedelta(seconds=seconds)
        self.notify()

    def cancel_device_learning(self) -> None:
        self.device_learning_until = None
        self.notify()

    # ── sicurezza ──────────────────────────────────────────────────────────

    @property
    def in_alarm(self) -> bool:
        return self.security_state == SECURITY_ALARM

    async def async_register_failure(self) -> int:
        self.failure_streak += 1
        await self.async_save_and_notify()
        return self.failure_streak

    async def async_reset_failures(self) -> None:
        if self.failure_streak:
            self.failure_streak = 0
            await self.async_save_and_notify()

    async def async_raise_alarm(self, motivo: str) -> bool:
        """Porta il sistema in allarme. Ritorna False se c'era già.

        Non si rialza un allarme già alzato: il motivo originale è quello che
        conta, ed è quello che si vuole ritrovare quando si va a guardare.
        """
        if self.in_alarm:
            return False
        self.security_state = SECURITY_ALARM
        self.alarm_reason = motivo
        self.alarm_since = dt_util.utcnow().isoformat()
        await self.async_save_and_notify()
        return True

    async def async_clear_alarm(self) -> None:
        self.security_state = SECURITY_NORMAL
        self.alarm_reason = ""
        self.alarm_since = None
        self.failure_streak = 0
        await self.async_save_and_notify()

    # ── registro accessi ───────────────────────────────────────────────────

    async def async_append_log(self, event: AccessEvent) -> None:
        self.log.insert(0, event)
        cap = int(self.settings.get("log_max_entries") or 500)
        if len(self.log) > cap:
            del self.log[cap:]
        await self.async_save_and_notify()

    async def async_clear_log(self) -> None:
        self.log = []
        await self.async_save_and_notify()

    def denied_today(self) -> int:
        """Quanti tentativi sono stati rifiutati oggi.

        Si elenca cosa conta invece di negare tutto ciò che non è `granted`:
        un esito nuovo non deve finire fra i rifiuti per il solo fatto di
        essere nuovo — è così che un censimento finiva contato come diniego.
        """
        rifiuti = (RESULT_DENIED, RESULT_BLACKLIST, RESULT_ALARM)
        today = dt_util.now().date()
        count = 0
        for event in self.log:
            when = event.when
            if when is None:
                continue
            if dt_util.as_local(when).date() != today:
                # Il log è ordinato dal più recente: appena si scende sotto
                # oggi non c'è più nulla da contare.
                break
            if event.result in rifiuti:
                count += 1
        return count


def _copia_notifiche(base: dict[str, Any]) -> dict[str, Any]:
    return {
        "master": base["master"],
        "service": base["service"],
        "tipi": {k: dict(v) for k, v in base["tipi"].items()},
    }


def _fondi_notifiche(salvate: dict[str, Any]) -> dict[str, Any]:
    """Fonde le notifiche salvate coi default, tipo per tipo.

    Un tipo nuovo introdotto da un aggiornamento deve comparire configurato,
    non mancare; e un tipo salvato non deve perdere i campi che il default ha
    guadagnato nel frattempo.
    """
    fuse = _copia_notifiche(DEFAULT_NOTIFICATIONS)
    if "master" in salvate:
        fuse["master"] = bool(salvate["master"])
    if salvate.get("service"):
        fuse["service"] = salvate["service"]
    for tipo, conf in (salvate.get("tipi") or {}).items():
        if tipo in fuse["tipi"] and isinstance(conf, dict):
            fuse["tipi"][tipo].update(conf)
    return fuse
