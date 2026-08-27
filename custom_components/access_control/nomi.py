"""Come si chiamano le cose, quando bisogna scriverlo a un essere umano.

Un identificativo è la cosa giusta da salvare e la cosa sbagliata da mostrare:
`person.marco` e `e9dee30b185d549194a2f44f09b7fb8a` sono ottimi riferimenti e
pessime notifiche. Il registro continua a tenere gli identificativi — sono
loro a non cambiare quando qualcuno rinomina una persona o un dispositivo —
ma quello che arriva sul telefono va tradotto.

Sta in un posto solo perché il pannello e le notifiche devono chiamarle allo
stesso modo: due funzioni separate divergono, e ci si ritrova con lo stesso
lettore che è «Ingresso» a schermo e qualcos'altro nel messaggio.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


def nome_dispositivo(hass: HomeAssistant, store, device_id: str) -> str:
    """Il nome del lettore: prima quello dato qui, poi quello di HA.

    L'ordine conta. Se qualcuno ha rinominato il lettore dentro il modulo, è
    quello il nome con cui lo pensa — vince su quello del registro di Home
    Assistant, che spesso è ancora il nome di fabbrica del dispositivo.
    """
    if not device_id:
        return ""
    voce = store.devices.get(device_id) or {}
    if voce.get("nome"):
        return voce["nome"]
    device = dr.async_get(hass).async_get(device_id)
    return (device.name_by_user or device.name or device_id) if device else device_id


def nome_persona(hass: HomeAssistant, entity_id: str) -> str:
    """Il nome della persona, non la sua entità.

    Il ripiego ricava qualcosa di leggibile dall'`entity_id` invece di
    mostrarlo così com'è: capita con una persona rimossa da Home Assistant
    mentre le sue tessere sono ancora nel registro, e in quel caso «Marco» è
    comunque più utile di `person.marco` a chi legge la notifica.
    """
    if not entity_id:
        return ""
    state = hass.states.get(entity_id)
    if state:
        nome = state.attributes.get("friendly_name")
        if nome:
            return str(nome)
    return entity_id.split(".", 1)[-1].replace("_", " ").title()
