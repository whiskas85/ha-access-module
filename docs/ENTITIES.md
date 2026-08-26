# Mappa entità

Entità reali dell'impianto usate dal modulo, verificate su Home Assistant
2026.8.3. Da aggiornare se l'impianto cambia.

Questo documento contiene solo `entity_id` — nessun UID, nessuna coordinata,
nessuna credenziale.

---

## Attuazione (dentro casa)

| Ruolo | Entità | Note |
|---|---|---|
| Serratura blindata | `lock.portone` | Nuki Smart Lock Pro via MQTT. `supported_features: 1` → supporta `lock.open` (apre lo scrocco) |
| Cancelletto pedonale | `switch.cancelletto` | Shelly Pro 1 |
| Cancello carraio | `switch.cancello` | Shelly 1 — **non usato dal modulo** |

> Il cancelletto pedonale è `switch.cancelletto`, non `switch.cancello`. I nomi
> si somigliano e lo script preesistente `script.entra_in_casa_cancelletto`
> pilota il *cancello carraio* nonostante il nome. Verificare sempre quale dei
> due si sta comandando.

## Sensori di posizione

| Ruolo | Entità | Note |
|---|---|---|
| Reed porta blindata | `binary_sensor.contatto_porta_blindata_window` | `on` = anta aperta |
| Reed cancelletto | `binary_sensor.bthome_sensor_29e8_window` | BTHome |

## Presenza e geofence

| Ruolo | Entità |
|---|---|
| Adulti | `person.marco`, `person.andre` |
| Zona di avvicinamento | `zone.vicinanze_di_casa` (stato person: `Vicinanze di casa`) |

## Video

| Ruolo | Entità |
|---|---|
| Telecamera ingresso | `camera.ingresso_principale_live_view` (Ring, cloud) |

Le notifiche allegano `\/api\/camera_proxy\/camera.ingresso_principale_live_view`
invece di uno snapshot su file: nessuna scrittura su disco, nessuna directory da
predisporre, e l'immagine si aggiorna all'apertura della notifica. Aggira anche
la latenza di 5–10 s dello snapshot Ring.

## Lettore esterno

| Ruolo | Entità / azione |
|---|---|
| Nodo | `RFID Ingresso` — ESP32, esp-idf, area `esterno` |
| Risposta a HA | `esphome.rfid_ingresso_esito_accesso` (campo `esito`) |
| Firmware | `update.rfid_ingresso_firmware` |
| Test buzzer | `button.giardino_rfid_ingresso_buzzer_test_ok` / `_ko` / `_attesa` |

## Notifiche

Il modulo usa `notify.notify` (tutti i dispositivi registrati). Se serve
indirizzare un singolo telefono, sostituire con il `notify.mobile_app_*`
corrispondente.

---

## Scostamenti fra spec e impianto reale

Tre punti in cui la spec assume sorgenti che su questo impianto non esistono.

### 1. La serratura non espone gli stati ricchi

La spec §4 dà per disponibili gli stati **aperta / chiusa / in apertura /
maniglia azionata / errore**.

La Nuki Smart Lock Pro via MQTT espone solo:

```
lock.portone                          sensor.portone_battery
binary_sensor.portone_battery_critical   binary_sensor.portone_battery_charging
button.portone_unlatch                button.portone_lock_n_go
button.portone_lock_n_go_with_unlatch sensor.porta_blindata_firmware_version
```

Nessun sensore di stato porta, **nessun sensore maniglia**, nessun sensore di
errore dedicato.

**Conseguenze:**

- `sensor.access_door_status` funziona: le due fonti indipendenti sono
  `lock.portone` (che riporta comunque `locked`/`unlocked`/`open`/`opening`/
  `jammed`) e il reed sull'anta.
- `Access: errore serratura` funziona, agganciato a `jammed` e a `unavailable`
  prolungato.
- **`Access: maniglia azionata a casa vuota` non è implementabile.** Sostituita
  da `Access: apertura non autorizzata`, che scatta quando l'anta si apre con
  sistema in `sleep` e nessuno in casa. Copre lo stesso scenario — qualcuno sta
  entrando senza autorizzazione — con una sorgente che esiste davvero. Non apre
  nulla: notifica e snapshot.

Se si vogliono gli stati ricchi, la strada è Nuki Hub / Nuki Bridge MQTT con
`doorsensorState` e lo stato maniglia esposti come entità.

### 2. Nessuna entità per la porta garage

La spec §4 la elenca fra l'hardware già pilotabile. Su HA esistono solo entità
della *telecamera* garage (`camera.telecamera_garage_*`), nessun attuatore.

Ininfluente per questa iterazione: il secondo varco è comunque fuori scope (§12).

### 3. Nessun sensore di presenza dedicato

`binary_sensor.access_presenza_recente` è derivato dallo stato di
`person.marco` e `person.andre`. Se in futuro arrivano sensori mmWave o simili,
è l'unico punto da modificare — la macchina a stati legge solo quel sensore.

---

## Interazione con l'antifurto — da decidere

L'impianto ha **Alarmo** (`alarm_control_panel.home_alarm`).

Lo script preesistente `script.entra_in_casa_cancelletto` disarma l'antifurto
contestualmente all'apertura. **Il modulo accessi non lo fa**: la spec §9 non
lo prevede, e disarmare un antifurto è un'azione di sicurezza che non va
aggiunta di iniziativa.

Va però deciso, perché la conseguenza è concreta: se l'antifurto è inserito
quando il bambino rientra con il tag, il rientro autorizzato fa scattare
l'allarme.

Tre opzioni:

1. L'antifurto resta disinserito durante la finestra scuola (scelta
   organizzativa, nessun codice)
2. Il ramo OK dell'automazione disarma Alarmo — richiede il codice in una
   configurazione, con le implicazioni del caso
3. Alarmo in modalità che tollera l'ingresso dal varco pedonale in finestra

Nessuna delle tre è stata implementata.

---

## Nota di igiene su un repository vicino

Lo script `script.entra_in_casa_cancelletto` contiene il **codice di disarmo
dell'antifurto in chiaro** nella propria configurazione. Non è un problema di
questo modulo — nessun file di questo repo lo contiene — ma va tenuto presente
prima di esportare o condividere configurazioni di automazioni e script.

Analogamente: il repository `irrigazione-smart` contiene un file `casa.jpg`. Se
quel repo è pubblico, vale la stessa regola di §3 sulle immagini che
identificano l'abitazione.
