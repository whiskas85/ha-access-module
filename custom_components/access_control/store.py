"""Persistenza di Controllo Accessi: impostazioni, registro tessere, varchi, log."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CARD_ACTIVE,
    CARD_BLACKLISTED,
    CARD_DISABLED,
    CONF_CARDS,
    CONF_DEVICES,
    CONF_GATES,
    CONF_LOG,
    CONF_SETTINGS,
    DEFAULT_GATE,
    DEFAULT_SETTINGS,
    RESULT_BLACKLIST,
    RESULT_DENIED,
    RESULT_LOCKOUT,
    ROLE_NONE,
    ROLES,
    SIGNAL_STATE_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .models import AccessEvent, Card, detect_technology, normalize_uid

_LOGGER = logging.getLogger(__name__)


class AccessStore:
    """Stato condiviso fra entità, pannello e motore di valutazione."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.cards: dict[str, Card] = {}
        self.gates: dict[str, dict[str, Any]] = {}
        self.log: list[AccessEvent] = []
        # Stato corrente della macchina a stati, scritto dal coordinator.
        self.system_state: str = ""
        self.state_reason: str = ""
        # Lockout
        self.failure_streak: int = 0
        self.locked_until: str | None = None
        # Enrollment: non persistito di proposito. Una modalità che accetta
        # tessere nuove non deve sopravvivere a un riavvio — se Home Assistant
        # riparte mentre è aperta, deve ripartire chiusa.
        self.enrollment_until = None
        # Su QUALE lettore si sta censendo. Con più varchi, aprire il
        # censimento su tutti significherebbe che una tessera passata al
        # garage mentre stai censendo all'ingresso finisce nel registro senza
        # che nessuno l'abbia voluta. Una lettura da un altro varco viene
        # valutata normalmente.
        self.enrollment_gate: str = ""
        # Due elenchi distinti, e la distinzione conta.
        #
        # `readers` è ciò che si è OSSERVATO: chi ha emesso `tag_scanned`.
        # Si popola da solo e non autorizza niente — è materiale per i
        # suggerimenti.
        # { device_id: {"prima": iso, "ultima": iso, "letture": int} }
        self.readers: dict[str, dict[str, Any]] = {}

        # `devices` è ciò che è stato REGISTRATO: i lettori che qualcuno ha
        # deciso far parte dell'impianto. Solo questi possono essere associati
        # a un varco. Un dispositivo può essere registrato senza aver mai letto
        # nulla (scelto dall'elenco), e può aver letto molto senza essere
        # registrato: sono due fatti diversi e non vanno confusi.
        self.devices: dict[str, dict[str, Any]] = {}

        # Registrazione automatica di un lettore in corso (non persistita).
        self.device_learning_until = None

    # ── caricamento e salvataggio ──────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}

        # Le impostazioni vanno fuse con i default, non sostituite: un
        # aggiornamento che aggiunge una chiave non deve lasciare `None` in
        # giro per le installazioni esistenti.
        stored_settings = data.get(CONF_SETTINGS) or {}
        self.settings = {**DEFAULT_SETTINGS, **stored_settings}

        self.cards = {}
        for raw in data.get(CONF_CARDS) or []:
            try:
                card = Card.from_dict(raw)
            except (TypeError, ValueError):
                _LOGGER.warning("Tessera illeggibile nello store, ignorata: %s", raw)
                continue
            if card.uid:
                self.cards[card.id] = card

        gates = data.get(CONF_GATES) or []
        self.gates = {g["id"]: g for g in gates if g.get("id")}
        if not self.gates:
            self.gates = {DEFAULT_GATE["id"]: dict(DEFAULT_GATE)}

        self.log = [AccessEvent.from_dict(r) for r in (data.get(CONF_LOG) or [])]

        lockout = data.get("lockout") or {}
        self.failure_streak = int(lockout.get("failure_streak") or 0)
        self.locked_until = lockout.get("locked_until")

        self.readers = dict(data.get("readers") or {})
        self.devices = dict(data.get(CONF_DEVICES) or {})

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                CONF_SETTINGS: self.settings,
                CONF_CARDS: [c.to_dict() for c in self.cards.values()],
                CONF_GATES: list(self.gates.values()),
                CONF_LOG: [e.to_dict() for e in self.log],
                "lockout": {
                    "failure_streak": self.failure_streak,
                    "locked_until": self.locked_until,
                },
                "readers": self.readers,
                CONF_DEVICES: self.devices,
            }
        )

    async def async_save_and_notify(self) -> None:
        await self.async_save()
        self.notify()

    def notify(self) -> None:
        """Sveglia le entità: pannello e entità leggono lo stesso stato."""
        async_dispatcher_send(self.hass, SIGNAL_STATE_CHANGED)

    # ── impostazioni ───────────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        self.settings.update(changes)
        await self.async_save_and_notify()

    def role_of(self, person: str) -> str:
        """Ruolo del titolare, stringa vuota se non è stato assegnato.

        Non si torna un ruolo di comodo per chi non è configurato. Trattare un
        titolare sconosciuto come adulto sarebbe fail-open: gli darebbe i
        permessi più ampi proprio perché nessuno ha detto chi è, e il sistema
        funzionerebbe senza far notare che manca una decisione. Senza ruolo la
        tessera non apre, e il registro dice esattamente perché.
        """
        roles = self.settings.get("person_roles") or {}
        return roles.get(person) or ROLE_NONE

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
        """Censisce una tessera. Se l'UID esiste già ne aggiorna i dati.

        La tecnologia, se non passata, viene rilevata dall'UID: è il caso
        normale: chi censisce non deve doverla sapere.

        L'UID è la chiave logica: due righe con lo stesso UID renderebbero il
        risultato della valutazione dipendente dall'ordine di iterazione.
        """
        normalized = normalize_uid(uid)
        if not normalized:
            raise ValueError("UID vuoto")

        rilevata = technology or detect_technology(normalized)

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
            technology=rilevata,
            note=note,
        )
        self.cards[card.id] = card
        await self.async_save_and_notify()
        return card

    async def async_assign_person(self, card_id: str, person: str) -> Card:
        """Abbina (o stacca, con person vuoto) una tessera a un titolare."""
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.person = person or ""
        await self.async_save_and_notify()
        return card

    # ── lettori riconosciuti ───────────────────────────────────────────────

    async def async_note_reader(self, device_id: str) -> bool:
        """Registra che questo dispositivo ha letto qualcosa.

        È l'unico criterio sensato per dire "qui c'è un lettore NFC": né
        l'integrazione né il modello lo dichiarano, e dedurlo dal nome
        sarebbe indovinare. Chi legge è un lettore.

        Ritorna True se è la prima volta che lo si vede.
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
        await self.async_save()
        return nuovo

    def seed_readers(self, coppie: list[tuple[str, str | None]]) -> None:
        """Semina i lettori dai tag già esistenti, senza aspettare una lettura.

        L'integrazione Tag conserva su ogni tag `last_scanned_by_device_id`:
        all'avvio è già una lista di dispositivi che hanno letto in passato,
        quindi l'elenco non parte vuoto su un impianto in cui si è già
        passata qualche tessera.
        """
        for device_id, quando in coppie:
            if not device_id or device_id in self.readers:
                continue
            ora = quando or dt_util.utcnow().isoformat()
            self.readers[device_id] = {"prima": ora, "ultima": ora, "letture": 0}

    async def async_bind_reader(self, gate_id: str, device_id: str) -> None:
        gate = self.gates.get(gate_id)
        if gate is None:
            raise KeyError(gate_id)
        gate["reader_device_id"] = device_id
        await self.async_save_and_notify()

    # ── dispositivi registrati ─────────────────────────────────────────────

    async def async_register_device(
        self, device_id: str, nome: str = "", note: str = ""
    ) -> bool:
        """Aggiunge un lettore all'impianto. Ritorna True se è nuovo."""
        if not device_id:
            raise ValueError("device_id vuoto")
        nuovo = device_id not in self.devices
        voce = self.devices.setdefault(
            device_id, {"aggiunto": dt_util.utcnow().isoformat()}
        )
        if nome:
            voce["nome"] = nome
        if note:
            voce["note"] = note
        await self.async_save_and_notify()
        return nuovo

    async def async_unregister_device(self, device_id: str) -> list[str]:
        """Toglie un lettore, e stacca i varchi che lo usavano.

        Lasciare un varco che punta a un dispositivo non più registrato
        significherebbe un varco che non riceve mai letture senza spiegare
        perché: meglio staccarlo e dirlo.
        """
        self.devices.pop(device_id, None)
        staccati = []
        for gate_id, gate in self.gates.items():
            if gate.get("reader_device_id") == device_id:
                gate["reader_device_id"] = ""
                staccati.append(gate_id)
        await self.async_save_and_notify()
        return staccati

    # ── registrazione automatica di un lettore ─────────────────────────────

    @property
    def device_learning_active(self) -> bool:
        if not self.device_learning_until:
            return False
        return dt_util.utcnow() < self.device_learning_until

    @property
    def device_learning_seconds_left(self) -> int:
        if not self.device_learning_active:
            return 0
        return max(
            0,
            int((self.device_learning_until - dt_util.utcnow()).total_seconds()),
        )

    def start_device_learning(self, seconds: int) -> None:
        # Le due modalità non possono essere aperte insieme: una lettura non
        # può essere allo stesso tempo "censisci questa tessera" e "scarta
        # questa tessera, mi serve solo il lettore".
        self.enrollment_until = None
        self.enrollment_gate = ""
        self.device_learning_until = dt_util.utcnow() + timedelta(seconds=seconds)
        self.notify()

    def cancel_device_learning(self) -> None:
        self.device_learning_until = None
        self.notify()

    # ── enrollment ─────────────────────────────────────────────────────────

    @property
    def enrollment_active(self) -> bool:
        if not self.enrollment_until:
            return False
        return dt_util.utcnow() < self.enrollment_until

    @property
    def enrollment_seconds_left(self) -> int:
        if not self.enrollment_active:
            return 0
        return max(
            0, int((self.enrollment_until - dt_util.utcnow()).total_seconds())
        )

    def start_enrollment(self, seconds: int, gate_id: str = "") -> None:
        # Vedi start_device_learning: le due modalità si escludono.
        self.device_learning_until = None
        self.enrollment_gate = gate_id or next(iter(self.gates), "")
        self.enrollment_until = dt_util.utcnow() + timedelta(seconds=seconds)
        self.notify()

    def cancel_enrollment(self) -> None:
        self.enrollment_until = None
        self.enrollment_gate = ""
        self.notify()

    def enrollment_accepts(self, gate_id: str) -> bool:
        """Questa lettura va censita, o valutata normalmente?"""
        if not self.enrollment_active:
            return False
        return not self.enrollment_gate or self.enrollment_gate == gate_id

    async def async_update_card(self, card_id: str, changes: dict[str, Any]) -> Card:
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)

        for key in ("name", "person", "technology", "note"):
            if key in changes:
                setattr(card, key, changes[key])
        if "uid" in changes:
            new_uid = normalize_uid(changes["uid"])
            clash = self.card_by_uid(new_uid)
            if new_uid and clash is not None and clash.id != card.id:
                raise ValueError(f"UID già assegnato a {clash.label}")
            card.uid = new_uid or card.uid
        if "state" in changes:
            await self.async_set_card_state(card_id, changes["state"], save=False)

        await self.async_save_and_notify()
        return card

    async def async_set_card_state(
        self, card_id: str, state: str, *, save: bool = True
    ) -> Card:
        """Attiva / disabilita / mette in blacklist una tessera.

        Disabilitata e blacklist sono cose diverse di proposito: una tessera
        riposta in un cassetto non deve generare allarmi quando qualcuno la
        prova, una tessera persa sì.
        """
        if state not in (CARD_ACTIVE, CARD_DISABLED, CARD_BLACKLISTED):
            raise ValueError(f"Stato tessera non valido: {state}")
        card = self.cards.get(card_id)
        if card is None:
            raise KeyError(card_id)
        card.state = state
        if save:
            await self.async_save_and_notify()
        return card

    async def async_remove_card(self, card_id: str) -> None:
        """Elimina una tessera dal registro.

        Dopo l'eliminazione una lettura di quell'UID risulta "sconosciuta" e
        non allarma. Se la tessera è stata persa la scelta giusta è la
        blacklist, non l'eliminazione.
        """
        if self.cards.pop(card_id, None) is not None:
            await self.async_save_and_notify()

    # ── varchi ─────────────────────────────────────────────────────────────

    def gate(self, gate_id: str) -> dict[str, Any] | None:
        return self.gates.get(gate_id)

    async def async_upsert_gate(self, gate: dict[str, Any]) -> dict[str, Any]:
        gate_id = gate.get("id")
        if not gate_id:
            raise ValueError("Varco senza id")
        current = self.gates.get(gate_id, dict(DEFAULT_GATE))
        current = {**current, **gate}
        self.gates[gate_id] = current
        await self.async_save_and_notify()
        return current

    async def async_remove_gate(self, gate_id: str) -> None:
        if self.gates.pop(gate_id, None) is not None:
            await self.async_save_and_notify()

    # ── lockout ────────────────────────────────────────────────────────────

    @property
    def is_locked_out(self) -> bool:
        if not self.locked_until:
            return False
        until = dt_util.parse_datetime(self.locked_until)
        if until is None:
            return False
        return dt_util.utcnow() < until

    async def async_register_failure(self) -> int:
        self.failure_streak += 1
        await self.async_save_and_notify()
        return self.failure_streak

    async def async_reset_failures(self) -> None:
        if self.failure_streak or self.locked_until:
            self.failure_streak = 0
            self.locked_until = None
            await self.async_save_and_notify()

    async def async_lock_readers(self, minutes: int) -> None:
        self.locked_until = (dt_util.utcnow() + timedelta(minutes=minutes)).isoformat()
        await self.async_save_and_notify()

    async def async_unlock_readers(self) -> None:
        self.locked_until = None
        self.failure_streak = 0
        await self.async_save_and_notify()

    # ── log accessi ────────────────────────────────────────────────────────

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

        Si contano solo i rifiuti veri. Un censimento non è un tentativo di
        accesso — è un'operazione voluta, che al lettore risponde `ok` — e
        contarlo qui gonfierebbe le statistiche proprio nel momento in cui si
        sta configurando il sistema, cioè quando quel numero viene guardato di
        più. Per lo stesso motivo si elenca cosa conta invece di negare tutto
        ciò che non è `granted`: un esito nuovo non deve finire fra i rifiuti
        per il solo fatto di essere nuovo.
        """
        rifiuti = (RESULT_DENIED, RESULT_BLACKLIST, RESULT_LOCKOUT)
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
