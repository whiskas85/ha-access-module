"""Esecuzione delle azioni di un lettore, e apertura dei varchi.

Le azioni di un lettore sono una **sequenza di azioni Home Assistant**: la
stessa identica cosa che si scrive nell'editor delle automazioni. Non un
formato inventato qui.

La conseguenza è che questo modulo non contiene un interprete: costruisce uno
`Script` e lo lascia girare a Home Assistant. `choose`, `if`, `delay`,
`repeat`, `wait_for_trigger`, i template — tutto funziona perché non è
riscritto, è quello vero. E quello che si vede nell'editor è letteralmente
quello che viene eseguito, senza traduzione in mezzo che possa mentire.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.script import Script

from .const import (
    ACTION_TIMEOUT_S,
    DOMAIN,
    GATE_SERVICE_BY_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_run_device_actions(
    hass: HomeAssistant,
    device_id: str,
    variabili: dict[str, Any],
    context: Context | None = None,
) -> bool:
    """Esegue la sequenza di azioni di un lettore. Ritorna True se è andata.

    Le azioni ricevono l'evento di accesso nella variabile `accesso`, quindi
    dentro l'editor si può scrivere `{{ accesso.person }}` o
    `{{ accesso.card_nome }}` come in qualunque automazione.
    """
    store = hass.data[DOMAIN]["store"]
    device = store.devices.get(device_id) or {}
    sequenza = device.get("azioni") or []

    if not sequenza:
        # Nessuna azione configurata: non è un errore, è un lettore che ancora
        # non fa niente. Va detto, perché dall'esterno sembra un guasto.
        _LOGGER.warning(
            "Lettore %s: accesso consentito ma nessuna azione configurata, "
            "quindi non si è aperto niente",
            device.get("nome") or device_id,
        )
        return False

    nome = device.get("nome") or device_id
    script = Script(
        hass,
        sequenza,
        f"Controllo Accessi — {nome}",
        DOMAIN,
        # Le azioni possono contenere `delay` o attese: senza questo, un
        # secondo passaggio della tessera mentre la sequenza è in corso non
        # produrrebbe niente.
        script_mode="parallel",
        max_runs=5,
    )

    try:
        await script.async_run(
            {"accesso": variabili}, context=context or Context()
        )
    except Exception:
        _LOGGER.exception("Azioni del lettore %s fallite", nome)
        return False
    return True


async def async_open_gate(hass: HomeAssistant, gate_id: str) -> None:
    """Apre un varco.

    Il servizio da chiamare si deduce dal dominio dell'entità, perché è
    sempre lo stesso e chiederlo sarebbe un campo in più da sbagliare. Resta
    forzabile quando l'ovvio non va bene — per esempio una serratura che non
    supporta l'apertura dello scrocco e va solo sbloccata.
    """
    store = hass.data[DOMAIN]["store"]
    gate = store.gate(gate_id)
    if gate is None:
        raise ValueError(f"Varco inesistente: {gate_id}")

    entity_id = gate.get("entity_id")
    if not entity_id or "." not in entity_id:
        raise ValueError(f"Varco «{gate.get('name', gate_id)}» senza entità")

    dominio = entity_id.split(".", 1)[0]
    servizio = gate.get("service") or GATE_SERVICE_BY_DOMAIN.get(dominio)
    if not servizio:
        raise ValueError(
            f"Non so come si apre un'entità {dominio}: "
            "indica il servizio nella configurazione del varco"
        )

    # Una serratura che non espone l'apertura dello scrocco si sblocca e
    # basta: chiamare `open` su quella solleverebbe, e il varco non si
    # aprirebbe per un dettaglio che si può dedurre.
    if dominio == "lock" and servizio == "open":
        stato = hass.states.get(entity_id)
        feature = (stato.attributes.get("supported_features") or 0) if stato else 0
        if not bool(feature & 1):
            servizio = "unlock"

    await hass.services.async_call(
        dominio, servizio, {"entity_id": entity_id}, blocking=True
    )
    _LOGGER.debug("Varco %s aperto con %s.%s", gate_id, dominio, servizio)

    auto_off = float(gate.get("auto_off_s") or 0)
    if auto_off > 0 and dominio in ("switch", "input_boolean", "light"):
        # Un relè di cancello lasciato acceso è un cancello che resta aperto.
        # Si programma lo spegnimento invece di aspettarlo con un `sleep`, che
        # terrebbe occupata l'esecuzione.
        async def _rispegni(_now) -> None:
            await hass.services.async_call(
                dominio, "turn_off", {"entity_id": entity_id}, blocking=False
            )

        from homeassistant.helpers.event import async_call_later

        async_call_later(hass, auto_off, _rispegni)


__all__ = ["ACTION_TIMEOUT_S", "async_open_gate", "async_run_device_actions"]
