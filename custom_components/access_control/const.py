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
#  Macchine a stati
#
#  Le credenziali sono accettate SOLO quando una finestra le ammette: è questa
#  logica che rende accettabile una credenziale debole, perché un tag clonato
#  fuori finestra non apre nulla.
#
#  Due macchine separate, e la separazione è il punto., e la separazione è il punto.
#
#  AUTORIZZAZIONE dice "adesso chi può entrare": dipende da orari e presenza,
#  cambia da sola durante il giorno, ed è normale che sia chiusa di notte.
#
#  SICUREZZA dice "sta succedendo qualcosa": ci si entra per attività
#  sospetta e si esce solo a mano.
#
#  Tenerle in un unico stato renderebbe la dashboard illeggibile: non si
#  distinguerebbe «è notte» da «qualcuno sta provando le tessere», che sono
#  la cosa più diversa che ci sia.
STATE_CLOSED: Final = "chiuso"
STATE_OPEN: Final = "aperto"
SYSTEM_STATES: Final = (STATE_CLOSED, STATE_OPEN)

SECURITY_NORMAL: Final = "normale"
SECURITY_ALARM: Final = "allarme"
SECURITY_STATES: Final = (SECURITY_NORMAL, SECURITY_ALARM)

ALARM_FAILED_READS: Final = "letture_errate_ripetute"
ALARM_DISABLED_CARD: Final = "tessera_disabilitata_presentata"
ALARM_BLACKLIST: Final = "tessera_in_blacklist_presentata"
ALARM_TAMPER: Final = "manomissione_lettore"

# Ruolo del titolare della card.
#
# Un titolare senza ruolo assegnato NON è un adulto: è un titolare senza
# ruolo, non compare fra i ruoli ammessi da nessuna finestra, e quindi non
# apre da nessuna parte. Il default opposto — trattarlo come adulto — sarebbe
# fail-open su una decisione di sicurezza: una persona mai configurata si
# ritroverebbe i permessi più ampi invece dei più stretti, e nessuno se ne
# accorgerebbe perché tutto funzionerebbe.
ROLE_CHILD: Final = "bambino"
ROLE_ADULT: Final = "adulto"
ROLE_NONE: Final = ""
ROLES: Final = (ROLE_CHILD, ROLE_ADULT)

# I gruppi con cui si nasce, e che non si possono togliere.
#
# Non per affezione: «adulto» ha un significato dentro il motore — la regola
# «un adulto in avvicinamento ammette gli adulti» lo cita per nome — e
# togliere il gruppo lascerebbe quell'impostazione a puntare al vuoto. Gli
# altri gruppi si aggiungono e si tolgono liberamente, perche' nessuna regola
# li conosce: valgono solo quello che le finestre dicono di loro.
GRUPPI_PREDEFINITI: Final[list[dict[str, str]]] = [
    {"id": ROLE_CHILD, "nome": "Bambino"},
    {"id": ROLE_ADULT, "nome": "Adulto"},
]

# ───────────────────────────────────────────────────────────────────────────
#  Finestre
#
#  Chi può entrare non è più una tabella scritta nel codice: sono finestre
#  che crei tu. Ognuna dice quando vale, per quali ruoli, e — se vuoi — su
#  quali lettori soltanto.
#
#  Fuori da ogni finestra attiva non entra nessuno. È il default: una
#  configurazione vuota è una casa chiusa, non una casa aperta.
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_WINDOW: Final[dict] = {
    "id": "",
    "name": "Nuova finestra",
    "enabled": True,
    "start": "15:30",
    "end": "16:30",
    # 0 = lunedì, come datetime.weekday()
    "days": [0, 1, 2, 3, 4],
    # Quali ruoli ammette. Entrambi = tutti.
    "roles": [ROLE_CHILD],
    # Vuoto = vale su tutti i lettori. Altrimenti solo su questi.
    "devices": [],
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
# La tecnologia viene RILEVATA dalla lettura, non chiesta a chi censisce: chi
# compra le tessere non ha modo di sapere che chip ci sia dentro, e una
# dichiarazione sbagliata qui diventerebbe un permesso sbagliato.
#
# Il PN532 letto via ESPHome espone solo l'UID — niente SAK/ATQA — quindi
# l'unico dato certo è la LUNGHEZZA dell'UID, che però basta per la
# distinzione che conta davvero (vedi `detect_technology` in models.py).
TECH_MIFARE_CLASSIC: Final = "mifare_classic"  # UID 4 byte
TECH_ISO14443A_7B: Final = "iso14443a_7byte"  # Ultralight / NTAG / DESFire
TECH_MIFARE_ULTRALIGHT: Final = "mifare_ultralight"
TECH_NTAG424: Final = "ntag424"
TECH_FINGERPRINT: Final = "impronta"
TECH_UNKNOWN: Final = "sconosciuta"

# ⚠️ NESSUNA tecnologia rilevabile oggi vale `forte`, ed è corretto così.
#
# `forte` non descrive il chip: descrive il fatto che il modulo abbia
# *verificato crittograficamente* la credenziale. Un NTAG424 di cui leggiamo
# solo l'UID si clona esattamente come una MIFARE Classic — la protezione sta
# nel cryptogram AES, che oggi nessuno verifica.
#
# Perciò `ntag424` e `impronta` restano in tabella ma sono irraggiungibili
# dalla rilevazione automatica: ci arriveranno i custom component di §12,
# quando ci sarà davvero qualcosa da verificare. Marcare a mano una tessera
# come "forte" significherebbe solo mentire al motore di autorizzazione.
TECHNOLOGY_SECURITY: Final[dict[str, str]] = {
    TECH_MIFARE_CLASSIC: SECURITY_WEAK,
    TECH_ISO14443A_7B: SECURITY_WEAK,
    TECH_MIFARE_ULTRALIGHT: SECURITY_WEAK,
    TECH_NTAG424: SECURITY_STRONG,
    TECH_FINGERPRINT: SECURITY_STRONG,
    TECH_UNKNOWN: SECURITY_UNKNOWN,
}

# Etichette leggibili per il pannello.
TECHNOLOGY_LABELS: Final[dict[str, str]] = {
    TECH_MIFARE_CLASSIC: "MIFARE Classic (UID 4 byte)",
    TECH_ISO14443A_7B: "Ultralight / NTAG / DESFire (UID 7 byte)",
    TECH_MIFARE_ULTRALIGHT: "MIFARE Ultralight",
    TECH_NTAG424: "NTAG424 DNA (cryptogram verificato)",
    TECH_FINGERPRINT: "Impronta digitale",
    TECH_UNKNOWN: "Non riconosciuta",
}

TECHNOLOGIES: Final = tuple(TECHNOLOGY_SECURITY)

# Una credenziale debole non apre i varchi elencati qui da un lettore
# qualsiasi: l'UID di una MIFARE Classic si clona in trenta secondi, e il
# varco veicolare non si apre con qualcosa di clonabile.
# Vuoto = nessuna restrizione aggiuntiva oltre a ruolo e finestra.
WEAK_FORBIDDEN_GATES: Final[tuple[str, ...]] = ()


# ───────────────────────────────────────────────────────────────────────────
#  Esiti e motivi
# ───────────────────────────────────────────────────────────────────────────
RESULT_GRANTED: Final = "granted"
RESULT_DENIED: Final = "denied"
RESULT_BLACKLIST: Final = "blacklist"
RESULT_ALARM: Final = "alarm"
# Lettura avvenuta in modalità enrollment: censita, non valutata.
RESULT_ENROLLED: Final = "enrolled"

REASON_MASTER_OFF: Final = "master_spento"
REASON_CLOSED: Final = "nessuna_finestra_attiva"
REASON_UNKNOWN_CARD: Final = "tessera_non_censita"
REASON_CARD_DISABLED: Final = "tessera_disabilitata"
REASON_CARD_BLACKLISTED: Final = "tessera_in_blacklist"
REASON_ROLE_NOT_ALLOWED: Final = "titolare_non_ammesso_ora"
REASON_ROLE_NOT_ASSIGNED: Final = "titolare_senza_ruolo_assegnato"
REASON_DEVICE_NOT_IN_WINDOW: Final = "lettore_escluso_dalla_finestra"
REASON_WEAK_ON_GATE: Final = "credenziale_debole_su_varco_protetto"
REASON_NO_PERSON: Final = "tessera_senza_titolare"
REASON_RATE_LIMIT: Final = "rate_limit_superato"
REASON_ALARM_ACTIVE: Final = "sistema_in_allarme"
REASON_NO_ACTIONS: Final = "nessuna_azione_configurata_sul_lettore"
REASON_DEVICE_NOT_REGISTERED: Final = "lettore_non_registrato"
REASON_ACTIONS_FAILED: Final = "azioni_del_lettore_fallite"

# Testi leggibili, per la dashboard e le notifiche. Il codice resta la chiave
# stabile su cui si scrivono le automazioni; questo è solo per gli umani.
REASON_LABELS: Final[dict[str, str]] = {
    REASON_MASTER_OFF: "il master accessi è spento",
    REASON_CLOSED: "nessuna finestra attiva in questo momento",
    REASON_UNKNOWN_CARD: "tessera non censita",
    REASON_CARD_DISABLED: "tessera disabilitata",
    REASON_CARD_BLACKLISTED: "tessera in blacklist",
    REASON_ROLE_NOT_ALLOWED: "il titolare non è ammesso in questa fascia",
    REASON_ROLE_NOT_ASSIGNED: "al titolare non è stato assegnato un ruolo",
    REASON_DEVICE_NOT_IN_WINDOW: "questo lettore è escluso dalla finestra attiva",
    REASON_WEAK_ON_GATE: "credenziale troppo debole per questo varco",
    REASON_NO_PERSON: "tessera senza titolare",
    REASON_RATE_LIMIT: "troppe letture ravvicinate",
    REASON_ALARM_ACTIVE: "sistema in allarme",
    REASON_NO_ACTIONS: "il lettore non ha azioni configurate",
    REASON_DEVICE_NOT_REGISTERED: "lettore non registrato",
    REASON_ACTIONS_FAILED: "le azioni del lettore sono fallite",
}

ALARM_LABELS: Final[dict[str, str]] = {
    ALARM_FAILED_READS: "letture errate ripetute",
    ALARM_DISABLED_CARD: "è stata presentata una tessera disabilitata",
    ALARM_BLACKLIST: "è stata presentata una tessera in blacklist",
    ALARM_TAMPER: "manomissione di un lettore",
}


# ───────────────────────────────────────────────────────────────────────────
#  Eventi sul bus
# ───────────────────────────────────────────────────────────────────────────
# Sventolato a ogni cambiamento dello stato salvato. Serve al pannello,
# che vive nel browser e non puo' sentire il dispatcher interno.
EVENT_UPDATED: Final = f"{DOMAIN}_updated"
EVENT_ACCESS: Final = f"{DOMAIN}_event"
EVENT_ALARM: Final = f"{DOMAIN}_alarm"
EVENT_ALARM_CLEARED: Final = f"{DOMAIN}_alarm_cleared"
EVENT_ENROLLED: Final = f"{DOMAIN}_enrolled"
EVENT_DEVICE_REGISTERED: Final = f"{DOMAIN}_device_registered"

# ───────────────────────────────────────────────────────────────────────────
#  Enrollment
# ───────────────────────────────────────────────────────────────────────────
# Quando è attivo, la prima lettura sconosciuta viene CENSITA invece che
# valutata. Ha una scadenza breve e non rinnovabile da sola: una modalità che
# accetta tessere nuove non deve poter restare aperta per dimenticanza.
ENROLLMENT_TIMEOUT_S: Final = 60

# Nomi delle azioni ESPHome del nodo di riferimento. Servono a indovinare i
# servizi di un lettore appena registrato: un campo obbligatorio che nasce
# vuoto si dimentica, e il sintomo di quella dimenticanza e' un lettore che
# sembra guasto — suona il pattern "nessuno ha risposto" perche' davvero
# nessuno gli ha risposto.
ESPHOME_DOMAIN: Final = "esphome"
SUFFIX_READER_SERVICE: Final = "_esito_accesso"
SUFFIX_ENROLL_SERVICE: Final = "_modo_censimento"
# Questo e' un'entita', non un'azione: si cerca fra le entita' del
# dispositivo, non fra i servizi.
SUFFIX_ENABLE_SWITCH: Final = "_lettura_abilitata"
SUFFIX_TAMPER_SENSOR: Final = "_tamper"

# Registrazione automatica di un LETTORE. Cosa diversa dal censimento di una
# tessera, e va tenuta diversa: qui interessa solo sapere quale dispositivo ha
# letto. La tessera usata per farsi riconoscere viene **scartata** — è un
# gancio, non una credenziale, e spesso è la prima che si ha in tasca.
DEVICE_LEARNING_TIMEOUT_S: Final = 60

SIGNAL_STATE_CHANGED: Final = f"{DOMAIN}_state_changed"


# ───────────────────────────────────────────────────────────────────────────
#  Impostazioni persistite (valori di default)
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS: Final[dict] = {
    "master": True,
    # Presenza e geofence: si sommano alle finestre, non le sostituiscono.
    # Restano perché erano nella specifica di partenza e servono davvero —
    # ma sono opzioni, non regole scritte nel codice.
    "person_entities": [],
    "nearby_zone": "",
    "presence_opens_all": True,
    "nearby_opens_adults": True,
    # Il ruolo appartiene alla persona, non alla tessera: due tessere dello
    # stesso titolare non possono avere autorizzazioni diverse per svista.
    # { "person.marco": "adulto", ... }
    "person_roles": {},
    # Comportamento
    "sleep_delay_min": 10,
    "door_ajar_min": 5,
    "rate_limit_window_s": 10,
    "rate_limit_max": 3,
    # Allarme
    "alarm_threshold": 3,
    "alarm_on_disabled_card": True,
    "alarm_on_blacklist": True,
    "alarm_on_tamper": True,
    # I gruppi in cui si dividono le persone. Le finestre ammettono gruppi,
    # non persone: e' quello che permette di dire «la mattina entrano i
    # bambini» senza rifare la regola a ogni tessera nuova.
    "gruppi": [dict(g) for g in GRUPPI_PREDEFINITI],
    "camera_entity": "",
    # Sensori porta
    "door_lock_entity": "",
    "door_contact_entity": "",
    # Log
    "log_max_entries": 500,
}

# ───────────────────────────────────────────────────────────────────────────
#  Varchi
#
#  Un varco è un'apertura fisica — porta, garage, cancelletto, cancello —
#  definita una volta sola e riusabile da più lettori. Aprirlo è un'azione
#  come un'altra: il modulo espone `access_control.open_gate`, che si sceglie
#  nell'editor delle azioni come qualunque altro servizio.
#
#  Il modulo non apre mai di sua iniziativa: apre solo eseguendo le azioni
#  configurate su un lettore.
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_GATE: Final[dict] = {
    "id": "porta",
    "name": "Porta",
    # L'entità che apre: lock, switch, cover, button o script.
    "entity_id": "",
    # Vuoto = si deduce dal dominio dell'entità. Si compila solo per forzare
    # un comportamento diverso da quello ovvio (es. `unlock` invece di `open`
    # su una serratura che non supporta l'apertura dello scrocco).
    "service": "",
    # Per gli switch impulsivi: dopo quanti secondi rispegnere. 0 = mai.
    # Un relè di cancello lasciato acceso è un cancello che resta aperto.
    "auto_off_s": 0,
}

# ───────────────────────────────────────────────────────────────────────────
#  Lettori
#
#  La risposta al lettore appartiene al lettore, non al varco: è il
#  dispositivo che deve suonare, e uno stesso varco può essere aperto da
#  lettori diversi che rispondono in modi diversi.
#
#  Le azioni sono una sequenza di azioni Home Assistant, la stessa cosa che
#  si scrive nell'editor delle automazioni, eseguita dall'helper `Script`.
#  Non un formato mio: così l'editor grafico è quello vero e non c'è niente
#  da tradurre fra quello che si vede e quello che gira.
# ───────────────────────────────────────────────────────────────────────────
# Prefisso degli identificativi delle persone create qui dentro.
#
# Non tutti quelli che entrano in una casa sono un'entita' di Home Assistant:
# la nonna e chi viene a fare le pulizie hanno bisogno delle chiavi e non di
# un'app sul telefono. Il prefisso li distingue dalle `person.*` senza dover
# guardare altrove, e li tiene compatibili con tutto il resto — ruoli e
# finestre lavorano su una stringa, non gli interessa da dove viene.
LOCAL_PERSON_PREFIX: Final = "locale."

DEFAULT_DEVICE: Final[dict] = {
    "nome": "",
    "note": "",
    "azioni": [],
    # Cosa fare quando la tessera NON e' valida, e cosa fare quando i dinieghi
    # di fila fanno scattare l'allarme. Vuote di default: il caso normale e'
    # che un diniego non faccia niente oltre a essere tracciato, ma chi vuole
    # accendere una luce o far suonare qualcosa deve poterlo dire qui.
    "azioni_ko": [],
    "azioni_allarme": [],
    # Risposta acustica. Va data SEMPRE, anche negando: se il modulo tace, il
    # dispositivo emette il pattern "non raggiungibile" e chi è alla porta
    # crede che il sistema sia guasto quando era solo fuori orario.
    "reader_service": "",
    "reader_field": "esito",
    "reader_ok_value": "ok",
    "reader_ko_value": "ko",
    # Spia del censimento: il lettore mostra un colore dedicato mentre la
    # finestra e' aperta. Senza, chi preme "Aggiungi tessera" in casa ed esce
    # al lettore non ha modo di sapere se la finestra e' ancora valida.
    "enroll_service": "",
    "enroll_field": "attivo",
    # Contatto di manomissione del lettore. Il nodo segnala, non decide: e'
    # il modulo a guardare questo sensore e a portare l'impianto in allarme.
    "tamper_sensor": "",
    # Telecamera che inquadra QUESTO varco, per la foto nelle notifiche.
    # Vuoto = quella generale delle impostazioni. Una casa con due porte ha
    # due telecamere, e la foto della porta sbagliata e' peggio di nessuna
    # foto: fa credere di aver visto.
    "camera": "",
    # Interruttore con cui Home Assistant spegne la lettura quando il sistema
    # va in allarme. Senza, in allarme il lettore continuerebbe a leggere e a
    # inondare l'API — che è esattamente ciò da cui l'allarme difende.
    "enable_switch": "",
}

# Quanto può durare la sequenza di azioni di un lettore prima di considerarla
# piantata. Generosa: qui dentro può esserci un `delay`, e comunque la
# risposta al lettore è già partita prima di arrivare a eseguire le azioni.
ACTION_TIMEOUT_S: Final = 120

# Servizio di apertura varco, esposto perché sia scegliibile nell'editor.
SERVICE_OPEN_GATE: Final = "open_gate"

# Servizi che aprono, per dominio dell'entità del varco.
GATE_SERVICE_BY_DOMAIN: Final[dict[str, str]] = {
    "lock": "open",
    "switch": "turn_on",
    "cover": "open_cover",
    "button": "press",
    "script": "turn_on",
    "input_boolean": "turn_on",
    "light": "turn_on",
    "scene": "turn_on",
}

# ───────────────────────────────────────────────────────────────────────────
#  Notifiche
#
#  Un master generale più un interruttore per tipo, ciascuno col proprio
#  destinatario e il proprio testo. Segnaposto disponibili:
#    {tessera} {titolare} {lettore} {motivo} {ora} {stato}
# ───────────────────────────────────────────────────────────────────────────
NOTIFY_ACCESS_OK: Final = "accesso_consentito"
NOTIFY_ACCESS_KO: Final = "accesso_negato"
NOTIFY_BLACKLIST: Final = "blacklist"
NOTIFY_ALARM: Final = "allarme"
NOTIFY_ENROLLED: Final = "tessera_censita"
NOTIFY_DEVICE: Final = "lettore_registrato"
NOTIFY_DOOR_AJAR: Final = "porta_socchiusa"
NOTIFY_DOOR_FAULT: Final = "porta_incoerente"

# Dove porta il tocco sulla notifica.
#
# Una notifica che si apre sulla pagina sbagliata costringe a rifare a mano il
# percorso che aveva gia' in mano: chi la tocca ha in testa una domanda sola
# — «quale tessera?», «quale lettore?» — e la pagina deve essere quella dove
# la risposta si vede.
#
# Gli esiti di una lettura portano tutti alla pagina principale: li' c'e' lo
# stato dell'impianto, che e' cio' che si vuole guardare dopo un accesso o un
# diniego.
NOTIFY_DESTINAZIONE: Final[dict[str, str]] = {
    NOTIFY_ACCESS_OK: "",
    NOTIFY_ACCESS_KO: "",
    NOTIFY_BLACKLIST: "",
    NOTIFY_ALARM: "",
    NOTIFY_ENROLLED: "tessere",
    NOTIFY_DEVICE: "dispositivi",
    NOTIFY_DOOR_AJAR: "varchi",
    NOTIFY_DOOR_FAULT: "varchi",
}

NOTIFY_LABELS: Final[dict[str, str]] = {
    NOTIFY_ACCESS_OK: "Accesso consentito",
    NOTIFY_ACCESS_KO: "Accesso negato",
    NOTIFY_BLACKLIST: "Tessera in blacklist",
    NOTIFY_ALARM: "Sistema in allarme",
    NOTIFY_ENROLLED: "Tessera censita",
    NOTIFY_DEVICE: "Lettore registrato",
    NOTIFY_DOOR_AJAR: "Porta socchiusa",
    NOTIFY_DOOR_FAULT: "Incoerenza sensori porta",
}

DEFAULT_NOTIFICATIONS: Final[dict] = {
    "master": True,
    "service": "notify.notify",
    "tipi": {
        NOTIFY_ACCESS_OK: {
            "attivo": False,
            "service": "",
            "alta_priorita": False,
            "immagine": False,
            "titolo": "🔓 Accesso consentito",
            "messaggio": "{tessera} — {titolare} al lettore {lettore}, ore {ora}",
        },
        NOTIFY_ACCESS_KO: {
            "attivo": True,
            "service": "",
            "alta_priorita": False,
            "immagine": True,
            "titolo": "⛔ Accesso negato",
            "messaggio": "{tessera} al lettore {lettore} — motivo: {motivo}",
        },
        NOTIFY_BLACKLIST: {
            "attivo": True,
            "service": "",
            "alta_priorita": True,
            "immagine": True,
            "titolo": "🚨 Tessera in blacklist",
            "messaggio": "È stata usata {tessera} al lettore {lettore}, ore {ora}",
        },
        NOTIFY_ALARM: {
            "attivo": True,
            "service": "",
            "alta_priorita": True,
            "immagine": True,
            "titolo": "🚨 Sistema in allarme",
            "messaggio": "Motivo: {motivo}. I lettori sono spenti finché non sblocchi.",
        },
        NOTIFY_ENROLLED: {
            "attivo": True,
            "service": "",
            "alta_priorita": False,
            "immagine": False,
            "titolo": "🆕 Tessera censita",
            "messaggio": "{tessera} — {motivo}. Assegnale un titolare per attivarla.",
        },
        NOTIFY_DEVICE: {
            "attivo": True,
            "service": "",
            "alta_priorita": False,
            "immagine": False,
            "titolo": "📟 Lettore registrato",
            "messaggio": "{lettore} è stato aggiunto all'impianto.",
        },
        NOTIFY_DOOR_AJAR: {
            "attivo": True,
            "service": "",
            "alta_priorita": True,
            "immagine": True,
            "titolo": "🚪 Porta socchiusa",
            "messaggio": "La porta è aperta da troppo tempo.",
        },
        NOTIFY_DOOR_FAULT: {
            "attivo": True,
            "service": "",
            "alta_priorita": True,
            "immagine": True,
            "titolo": "⚠️ Incoerenza sensori porta",
            "messaggio": "Anta aperta ma serratura chiusa: guasto o forzamento.",
        },
    },
}

# Ogni tipo ha due modi. In «default» il modulo manda la notifica da se', con
# il titolo e il messaggio qui sopra. In «custom» esegue una sequenza di azioni
# scritta nell'editor, e non manda niente per conto suo: serve a chi vuole una
# notifica fatta a modo proprio, o qualcosa che notifica non e' — accendere una
# luce, far parlare un altoparlante, chiamare un webhook.
#
# I due modi convivono nella stessa configurazione invece di sostituirsi:
# passando a custom non si perde il testo scritto, e tornando indietro lo si
# ritrova. Un modo che cancella l'altro costringe a ricopiare tutto per provare
# una strada e poi ripensarci.
for _tipo in DEFAULT_NOTIFICATIONS["tipi"].values():
    _tipo.setdefault("modo", "default")
    _tipo.setdefault("azioni", [])

CONF_DEVICES: Final = "devices"
CONF_PEOPLE: Final = "persone"
CONF_WINDOWS: Final = "windows"
CONF_NOTIFICATIONS: Final = "notifications"
CONF_GATES: Final = "gates"
CONF_CARDS: Final = "cards"
CONF_SETTINGS: Final = "settings"
CONF_LOG: Final = "log"
