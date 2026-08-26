"""Costanti di Controllo Accessi."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "access_control"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

STORAGE_KEY: Final = f"{DOMAIN}.storage"
STORAGE_VERSION: Final = 1

# Il pannello si aggancia qui.
PANEL_URL: Final = "controllo-accessi"
PANEL_TITLE: Final = "Accessi"
PANEL_ICON: Final = "mdi:shield-key"


# ───────────────────────────────────────────────────────────────────────────
#  Macchina a stati
#
#  Le credenziali sono accettate SOLO negli stati in cui il sistema è armato,
#  e ogni stato ammette un sottoinsieme diverso di titolari. È questa logica
#  che rende accettabile una credenziale debole: un tag clonato fuori finestra
#  non apre nulla.
# ───────────────────────────────────────────────────────────────────────────
STATE_SLEEP: Final = "sleep"
STATE_SCHOOL: Final = "finestra_scuola"
STATE_ADULT_RETURN: Final = "rientro_adulto"
STATE_OCCUPIED: Final = "casa_occupata"

SYSTEM_STATES: Final = (STATE_SLEEP, STATE_SCHOOL, STATE_ADULT_RETURN, STATE_OCCUPIED)

# Ruolo del titolare della card.
ROLE_CHILD: Final = "bambino"
ROLE_ADULT: Final = "adulto"
ROLES: Final = (ROLE_CHILD, ROLE_ADULT)

# Chi può entrare in quale stato. Unica fonte della matrice §5.
STATE_ALLOWED_ROLES: Final[dict[str, tuple[str, ...]]] = {
    STATE_SLEEP: (),
    STATE_SCHOOL: (ROLE_CHILD,),
    STATE_ADULT_RETURN: (ROLE_ADULT,),
    STATE_OCCUPIED: (ROLE_CHILD, ROLE_ADULT),
}


# ───────────────────────────────────────────────────────────────────────────
#  Card
# ───────────────────────────────────────────────────────────────────────────
CARD_ACTIVE: Final = "attiva"
CARD_DISABLED: Final = "disabilitata"
CARD_BLACKLISTED: Final = "blacklist"
CARD_STATES: Final = (CARD_ACTIVE, CARD_DISABLED, CARD_BLACKLISTED)

# Card presentata ma non presente nel registro.
CARD_UNKNOWN: Final = "sconosciuta"

SECURITY_WEAK: Final = "debole"
SECURITY_STRONG: Final = "forte"
SECURITY_UNKNOWN: Final = "sconosciuta"

# Tecnologia → livello di sicurezza.
#
# Il PN532 letto via ESPHome espone solo l'UID: non basta a classificare la
# card. Finché un custom component ESPHome non riporterà SAK/ATQA, la
# tecnologia si dichiara in fase di enrollment e da lì si deriva il livello.
# La lunghezza dell'UID è un indizio, non una prova: non va usata come tale.
TECH_MIFARE_CLASSIC: Final = "mifare_classic"
TECH_MIFARE_ULTRALIGHT: Final = "mifare_ultralight"
TECH_NTAG424: Final = "ntag424"
TECH_FINGERPRINT: Final = "impronta"
TECH_UNKNOWN: Final = "sconosciuta"

TECHNOLOGY_SECURITY: Final[dict[str, str]] = {
    TECH_MIFARE_CLASSIC: SECURITY_WEAK,
    TECH_MIFARE_ULTRALIGHT: SECURITY_WEAK,
    TECH_NTAG424: SECURITY_STRONG,
    TECH_FINGERPRINT: SECURITY_STRONG,
    TECH_UNKNOWN: SECURITY_UNKNOWN,
}

TECHNOLOGIES: Final = tuple(TECHNOLOGY_SECURITY)

# Una credenziale debole apre solo su questi varchi, qualunque sia lo stato.
# Il varco veicolare non si apre mai con un UID clonabile.
WEAK_ALLOWED_GATES: Final = ("ingresso",)


# ───────────────────────────────────────────────────────────────────────────
#  Esiti e motivi
# ───────────────────────────────────────────────────────────────────────────
RESULT_GRANTED: Final = "granted"
RESULT_DENIED: Final = "denied"
RESULT_BLACKLIST: Final = "blacklist"
RESULT_LOCKOUT: Final = "lockout"

REASON_MASTER_OFF: Final = "master_off"
REASON_SYSTEM_ASLEEP: Final = "sistema_in_sleep"
REASON_UNKNOWN_CARD: Final = "card_non_censita"
REASON_CARD_DISABLED: Final = "card_disabilitata"
REASON_CARD_BLACKLISTED: Final = "card_in_blacklist"
REASON_ROLE_NOT_ALLOWED: Final = "titolare_non_ammesso_in_questo_stato"
REASON_WEAK_ON_GATE: Final = "credenziale_debole_su_varco_non_consentito"
REASON_NO_PERSON: Final = "card_senza_titolare"
REASON_RATE_LIMIT: Final = "rate_limit_superato"
REASON_LOCKED_OUT: Final = "lettori_bloccati"
REASON_NO_ACTION_SCRIPT: Final = "nessuno_script_di_apertura_configurato"
REASON_PRE_HOOK_VETO: Final = "apertura_vietata_dal_pre_hook"
REASON_ACTION_FAILED: Final = "script_di_apertura_fallito"


# ───────────────────────────────────────────────────────────────────────────
#  Lockout lettori
# ───────────────────────────────────────────────────────────────────────────
# `segnala` non blocca nulla: notifica, evento, contatore.
# `blocca` rifiuta ogni lettura, comprese le card valide.
#
# Il default è `segnala` di proposito, ed è una scelta di sicurezza, non una
# comodità: un lockout che blocca tutto è banalmente armabile contro chi deve
# entrare — bastano N letture di una card qualsiasi — e in cambio difende da
# un brute-force dell'UID che a 3 letture ogni 10 secondi richiederebbe
# comunque secoli. Blocca l'unica persona che deve entrare e non ferma
# nessuno che conti davvero.
LOCKOUT_SIGNAL: Final = "segnala"
LOCKOUT_BLOCK: Final = "blocca"
LOCKOUT_MODES: Final = (LOCKOUT_SIGNAL, LOCKOUT_BLOCK)


# ───────────────────────────────────────────────────────────────────────────
#  Eventi sul bus
# ───────────────────────────────────────────────────────────────────────────
EVENT_ACCESS: Final = f"{DOMAIN}_event"
EVENT_LOCKOUT: Final = f"{DOMAIN}_lockout"

SIGNAL_STATE_CHANGED: Final = f"{DOMAIN}_state_changed"


# ───────────────────────────────────────────────────────────────────────────
#  Impostazioni persistite (valori di default)
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS: Final[dict] = {
    "master": True,
    # Finestra scuola
    "school_start": "15:30",
    "school_end": "16:30",
    "school_days": [0, 1, 2, 3, 4],  # lun-ven, come datetime.weekday()
    # Presenza e geofence
    "person_entities": [],
    "nearby_zone": "",
    # Il ruolo appartiene alla persona, non alla tessera: due tessere dello
    # stesso titolare non possono avere autorizzazioni diverse per svista.
    # { "person.marco": "adulto", ... }
    "person_roles": {},
    # Comportamento
    "sleep_delay_min": 10,
    "door_ajar_min": 5,
    "rate_limit_window_s": 10,
    "rate_limit_max": 3,
    # Lockout
    "lockout_mode": LOCKOUT_SIGNAL,
    "lockout_threshold": 5,
    "lockout_duration_min": 15,
    # Notifiche
    "notify_service": "notify.notify",
    "notify_on_entry": True,
    "notify_on_denied": True,
    "camera_entity": "",
    # Sensori porta
    "door_lock_entity": "",
    "door_contact_entity": "",
    # Log
    "log_max_entries": 500,
}

# Un varco: nome, script di apertura, hook e come si risponde al lettore.
# Il modulo non apre mai da sé: senza `action_script` nega e lo scrive nel log.
DEFAULT_GATE: Final[dict] = {
    "id": "ingresso",
    "name": "Ingresso",
    "action_script": "",
    "pre_hook": "",
    "post_hook": "",
    # Fail-open sul pre-hook: un pre-hook che va in errore si comporta come se
    # non ci fosse, perché la decisione di base ha già superato tutta la
    # policy. Fail-closed trasformerebbe un refuso in uno script in un bambino
    # chiuso fuori. Chi vuole il contrario lo imposta per varco.
    "pre_hook_fail_closed": False,
    # Device id del lettore, per capire da quale varco arriva una lettura
    # quando i varchi sono più di uno. L'evento `tag_scanned` porta con sé
    # `device_id`: senza questa mappatura ogni lettura finirebbe sul primo
    # varco, e una tessera debole aprirebbe il varco sbagliato.
    "reader_device_id": "",
    # Risposta al lettore. Va data SEMPRE, anche negando: se il modulo tace,
    # il dispositivo emette il pattern "non raggiungibile" e chi è alla porta
    # crede che il sistema sia guasto quando era solo fuori orario.
    "reader_service": "",
    "reader_field": "esito",
    "reader_ok_value": "ok",
    "reader_ko_value": "ko",
}

# Budget per il pre-hook. Il lettore va in timeout a 3 s: oltre questo, la
# risposta arriverebbe dopo il pattern "non raggiungibile".
PRE_HOOK_TIMEOUT_S: Final = 1.5

CONF_GATES: Final = "gates"
CONF_CARDS: Final = "cards"
CONF_SETTINGS: Final = "settings"
CONF_LOG: Final = "log"
