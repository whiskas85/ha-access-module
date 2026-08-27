# Modulo Controllo Accessi — Specifica di implementazione

Documento di specifica per la costruzione di un modulo Home Assistant per il
controllo accessi di casa, sul modello del modulo irrigazione (`sprinkler_*`)
già esistente e funzionante.

---

## 1. Obiettivo

Permettere l'accesso autonomo a casa a un bambino di 10 anni che rientra da
scuola da solo, senza consegnargli le chiavi e senza che possieda un telefono.

Il sistema deve inoltre servire gli adulti della famiglia come metodo di
accesso alternativo alle chiavi.

**Vincolo primario: la sicurezza di casa viene prima della comodità.** Qualsiasi
scelta implementativa che semplifichi l'uso a scapito della sicurezza va
segnalata e non adottata senza conferma esplicita.

---

## 2. Principio architetturale non negoziabile

Separazione netta fra **credenziale**, **decisione** e **attuazione**:

| Livello | Dove sta | Cosa fa |
|---|---|---|
| Credenziale | Lettore esterno (ESP32) | Legge, non decide, non attua |
| Decisione | Home Assistant (dentro casa) | Valuta e autorizza |
| Attuazione | Relè già esistenti dentro casa | Apre |

Conseguenze operative:

- L'ESP32 esterno **non deve mai pilotare un relè** collegato a un varco.
  Nessuna eccezione, nemmeno "per comodità" o "solo come fallback".
- Un attaccante che compromette completamente il dispositivo esterno ottiene
  la capacità di *dichiarare* "ho letto il codice X", non di aprire.
- Le chiavi crittografiche (future, per NTAG424) stanno in HA, mai nell'ESP32.

---

## 3. Convenzioni

Seguire le convenzioni già in uso nel modulo irrigazione.

- **Prefisso entità**: `access_` (come `sprinkler_` per l'irrigazione)
- **Nomi automazioni**: `Access: <descrizione>`
- **Dashboard**: `dashboard-accessi`, con due view
  - vista operativa (stato corrente, ultimi accessi, azioni rapide)
  - vista setup (configurazione finestre, soglie, gestione credenziali)
- **Sensore "cosa succede e perché"**: replicare il pattern
  `binary_sensor.sprinkler_will_water_today` + `sensor.sprinkler_watering_reason`,
  che si è dimostrato molto utile per il debug e la trasparenza.
- **UI consolidata**: preferire una card markdown unica che aggrega più
  informazioni rispetto a tile separati.
- Tutta la UI e i testi in **italiano**.

### Repository

Repo di riferimento: **https://github.com/whiskas85/ha-access-module**

Struttura proposta:

```
ha-access-module/
├── README.md
├── SPEC.md                      ← questo documento
├── packages/
│   └── access_control.yaml      ← package HA: helper, template, automazioni
├── esphome/
│   ├── rfid-ingresso.yaml
│   ├── rfid-garage.yaml
│   └── secrets.yaml.example     ← template, MAI i valori reali
├── dashboards/
│   └── dashboard-accessi.yaml
├── custom_components/           ← futuri componenti ESPHome custom
│   ├── ntag424/
│   └── fingerprint_grow_ext/
└── .gitignore
```

Usare un **package HA** (`packages/access_control.yaml`) invece di spargere
helper e automazioni nell'UI: rende il modulo versionabile, riproducibile e
trasferibile sul secondo varco.

#### ⚠️ Il repository è pubblico

**Primo task in assoluto, prima di qualsiasi altro file: creare il
`.gitignore`.** Il repo è vuoto, quindi non c'è ancora nulla da recuperare —
ma se il primo commit contiene per sbaglio un `secrets.yaml`, rimuoverlo dopo
non basta: resta nella storia e va riscritta con `git filter-repo`. Il
`.gitignore` va committato per primo, da solo.

Conseguenze da rispettare rigorosamente:

- `.gitignore` deve escludere `secrets.yaml`, `*.bin`, `/share/fingerprints/`
  e qualsiasi file di template biometrico
- **Nessun UID di tag reale** nel codice o nella documentazione: gli UID vanno
  in `secrets.yaml` o negli helper HA, mai versionati. Un UID pubblicato è un
  tag già clonato.
- Nessuna chiave API, password OTA, password WiFi o AP
- Nessun URL Nabu Casa, webhook o endpoint personale
- Nessuna foto o riferimento che identifichi l'abitazione

Pubblicare la *logica* del sistema è accettabile e coerente con il principio di
Kerckhoffs: la sicurezza deve stare nelle chiavi, non nella segretezza del
progetto. Pubblicare le *credenziali* no.

Se il repo dovesse contenere anche i template biometrici o gli UID reali,
renderlo privato.

---

## 4. Hardware

### Già presente e funzionante

- Home Assistant (Nabu Casa)
- Serratura blindata elettronica: apre lo scrocco su comando; espone stati
  **aperta / chiusa / in apertura / maniglia azionata / errore**
- Sensore reed sulla porta blindata (posizione anta)
- Cancelletto pedonale pilotabile da HA
- Porta garage pilotabile da HA
- Telecamera Ring esterna (integrazione cloud, snapshot con 5-10 s di latenza)

### Dispositivo esterno in sviluppo — nodo `rfid-ingresso`

- ESP32 (framework `esp-idf`), collegato via WiFi
- PN532 su I²C (GPIO21 SDA / GPIO22 SCL, 50 kHz) — **alimentato a 5V**
- Buzzer **attivo** su GPIO18 (pilotato on/off, non PWM — ignora la frequenza)
- Tag attualmente in uso per il collaudo: MIFARE Classic 1K (UID in `secrets.yaml`)

### Previsto ma non ancora implementato

- Grow R503 (impronte digitali) via UART
- Tastierino a matrice IP65 via PCF8574 sul bus I²C esistente
- Tag NTAG424 DNA con verifica cryptogram AES-128 lato HA
- Microswitch di tamper
- Secondo nodo identico per il garage (`rfid-garage`)

---

## 5. Macchina a stati

Il cuore del modulo. Le credenziali sono accettate **solo** negli stati in cui
il sistema è armato, e ogni stato ammette un sottoinsieme diverso di utenti.

| Stato | Come ci si entra | Chi è autorizzato |
|---|---|---|
| `sleep` | default; nessuna condizione soddisfatta | nessuno |
| `finestra_scuola` | giorno abilitato + orario dentro finestra | solo credenziali del bambino |
| `rientro_adulto` | geofence adulto in avvicinamento | credenziali adulti |
| `casa_occupata` | presenza rilevata in casa | tutti |

Ritorno a `sleep`: porta richiusa (reed + serratura concordi) e nessun evento
di presenza per N minuti (`input_number.access_sleep_delay`, default 10).

**Nota di design**: questa logica è ciò che rende accettabile una credenziale
debole. Un tag clonato fuori finestra non apre nulla. Non indebolire la
macchina a stati per semplificare.

---

## 6. Helper da creare

### Master e stato

- `input_boolean.access_master` — abilitazione generale del modulo
- `input_select.access_state` — `sleep` / `finestra_scuola` / `rientro_adulto` / `casa_occupata`

### Finestra scuola

- `input_datetime.access_school_start` (default 15:30, solo ora)
- `input_datetime.access_school_end` (default 16:30, solo ora)
- `input_boolean.access_school_day_monday` … `_friday`
  (replicare il pattern `input_boolean.sprinkler_day_<giorno>`)

### Comportamento

- `input_number.access_sleep_delay` — minuti prima del ritorno a sleep (default 10)
- `input_number.access_door_ajar_alert` — minuti di porta socchiusa prima della notifica (default 5)
- `input_number.access_rate_limit_window` — finestra rate limit lato HA in secondi (default 10)
- `input_number.access_rate_limit_max` — tentativi ammessi nella finestra (default 3)
- `input_boolean.access_notify_on_entry` — notifica ad ogni accesso riuscito
- `input_boolean.access_snapshot_on_entry` — allega snapshot Ring alla notifica

### Registro

- `input_datetime.access_last_entry` — data/ora ultimo accesso riuscito
- `input_text.access_last_credential` — quale credenziale ha aperto (max 255 char)
- `counter.access_denied_today` — tentativi negati, azzerato a mezzanotte

---

## 7. Sensori template

Replicare il pattern dell'irrigazione: esporre **cosa farebbe il sistema adesso
e perché**, così la logica è ispezionabile senza leggere le automazioni.

- `binary_sensor.access_armed`
  `on` se il sistema accetterebbe una credenziale in questo momento.

- `sensor.access_state_reason`
  Testo leggibile che spiega lo stato corrente. Esempi:
  - `Sleep: fuori finestra scuola, nessuno in avvicinamento`
  - `Finestra scuola attiva fino alle 16:30`
  - `Casa occupata: presenza rilevata`
  - `Master accessi spento`

- `sensor.access_door_status`
  Combina reed e stato serratura. **Sono due fonti indipendenti**: se si
  contraddicono (serratura dice chiusa, reed dice aperta) è un guasto o un
  forzamento, e va segnalato come stato distinto `incoerente`.

- `binary_sensor.access_door_ajar`
  Porta aperta da più di `access_door_ajar_alert` minuti.

### Card markdown consolidata (vista operativa)

Sul modello della card "Irrigazione" già esistente, una sola card che mostra:

```
🔓 Sistema armato   (oppure 🔒 Sistema in sleep)
Finestra scuola attiva fino alle 16:30

Ultimo accesso: 26/08/2026 - 15:42 (tag bambino)
Porta: chiusa
Tentativi negati oggi: 0
```

---

## 8. Contratto con il dispositivo ESPHome

Il nodo `rfid-ingresso` espone due azioni e genera un evento.

### In ingresso a HA

Evento `esphome.access_control_read`, con `uid` e `lettore`. **Non**
`tag_scanned`: quello fa creare a HA un'entità `tag.*` per ogni UID mai visto,
e chi cicla codici con un Flipper riempie il registro tag di spazzatura che
resta anche dopo che se n'è andato. Il tag entra nel registro solo dopo che la
lettura è stata validata.

Il dispositivo applica già un rate limiter locale (max 3 letture / 10 s)
indipendente da HA.

### In uscita da HA

```yaml
action: esphome.rfid_ingresso_esito_accesso
data:
  esito: "ok"    # oppure "ko", "allarme"
```

```yaml
action: esphome.rfid_ingresso_modo_censimento
data:
  attivo: true   # finestra di censimento aperta su questo lettore
```

La seconda è **solo una spia**: accende il colore dedicato sul LED. Il nodo
non sa che cosa sia un censimento e continua a mandare letture identiche a
sempre — a distinguerle è il modulo, non lui.

### Regole vincolanti

1. **Rispondere SEMPRE**, anche quando si nega. Se HA tace, dopo 3 secondi il
   dispositivo emette il pattern "non raggiungibile" e l'utente crede che il
   sistema sia guasto quando era solo fuori orario. Ogni ramo di ogni
   automazione deve terminare con una chiamata a `esito_accesso`.

2. **Il feedback non deve mai rivelare il motivo del diniego.** Tag
   sconosciuto, tag valido fuori finestra, tag valido con sistema disarmato →
   tutti `ko`, identico. Altrimenti chi trova un tag capisce dal feedback se
   quel tag è censito e vale la pena tornare in un altro orario. Il motivo
   reale va nel log e nella notifica, non nel buzzer.

3. **Il rate limiter deve esistere sia in HA che nell'ESP.** Quello lato HA non
   basta: un firmware sostituito lo aggirerebbe inondando l'API.

### Pattern acustici già implementati (buzzer attivo)

| Esito | Pattern |
|---|---|
| OK | due bip corti ravvicinati (60 ms on / 80 ms off / 60 ms on) |
| KO | un bip lungo (1200 ms) |
| HA non risponde | tre bip corti distanziati, dopo 3 s di attesa |

---

## 9. Automazioni da creare

### `Access: valuta credenziale ingresso`

Trigger: `tag` con l'UID censito.
Logica:
1. Verifica `input_boolean.access_master`
2. Verifica `binary_sensor.access_armed`
3. Verifica che quella credenziale sia ammessa **nello stato corrente**
   (il tag del bambino non apre alle 23:00 anche se il sistema è armato per
   il rientro di un adulto)
4. Rate limit lato HA
5. Se tutto ok → `esito: ok`, apertura cancelletto **e** blindata (i due varchi
   distano 7 m a vista, l'apertura contestuale è stata valutata accettabile),
   aggiorna `access_last_entry` e `access_last_credential`, notifica
6. Altrimenti → `esito: ko`, incrementa `counter.access_denied_today`,
   notifica con motivo reale e snapshot Ring

### `Access: macchina a stati`

Trigger: orario, geofence, presenza, chiusura porta.
Gestisce le transizioni di `input_select.access_state` secondo la tabella §5.

### `Access: porta socchiusa`

Trigger: `binary_sensor.access_door_ajar` → `on`.
Notifica con priorità alta se nessuno è in casa.

### `Access: incoerenza sensori`

Trigger: `sensor.access_door_status` → `incoerente`.
Notifica immediata: è un guasto o un forzamento.

### `Access: maniglia azionata a casa vuota`

Trigger: la serratura segnala azione sulla maniglia mentre lo stato è `sleep`.
**Non apre nulla** — genera notifica con snapshot Ring. È il segnale che
qualcuno sta provando la porta.

### `Access: errore serratura`

Trigger: la serratura riporta stato di errore.
Notifica ad alta priorità. Se siamo in `finestra_scuola`, includere nella
notifica un'azione rapida per aprire manualmente dal telefono.

---

## 10. Degradazione e fallback

Con HA nel percorso decisionale, un riavvio di HA o del router mentre il
bambino è al cancello lo lascia fuori. **Va gestito, non ignorato.**

**Fallback automatico (da implementare lato ESPHome, non HA)**
L'ESP mantiene in locale, con RTC di backup:
- la finestra oraria scuola
- una sola credenziale autorizzata (quella del bambino)

Se HA non risponde entro il timeout **e** siamo dentro la finestra, l'ESP apre
autonomamente il solo cancelletto. Superficie di attacco minima, copre il caso
quotidiano.

**Fallback manuale (fuori dal sistema)**
Key safe con combinazione, o PIN nativo della serratura. Non deve dipendere da
rete, HA o alimentazione del lettore.

---

## 11. Sicurezza — requisiti e limiti noti

### Requisiti

- Password API, OTA e AP in `secrets.yaml`, mai nel YAML versionato
- API ESPHome con cifratura Noise attiva
- Nodo esterno su VLAN/SSID IoT isolata
- Log di ogni tentativo, riuscito o negato
- Tamper switch → notifica + disarmo + snapshot, **non** cancellazione della
  flash (a dispositivo spento il firmware non gira: è teatro, non sicurezza)

### Limiti noti e accettati (per ora)

- Il tag MIFARE Classic in uso è **clonabile in trenta secondi**. È un tag da
  collaudo. La sicurezza reale viene dalla macchina a stati.
- Il PN532 letto via ESPHome fornisce **solo l'UID**, nessuna autenticazione.
- L'errore `Authentication failed - Block 0x04` nei log è atteso e innocuo:
  è ESPHome che tenta la lettura NDEF con chiave di default. L'UID è già stato
  acquisito.

### Mai fare

- Relè di apertura sull'ESP32 esterno
- Template biometrici in `/config` se versionato in git, in attributi di
  entità, o in `input_text` (finirebbero in recorder, logbook e backup)
- `ESP_LOGD` sui byte di un template biometrico
- Feedback differenziato per motivo di diniego

---

## 12. Fuori scope di questa iterazione

Da progettare in seguito, ma tenerne conto nella struttura:

- Custom component ESPHome per NTAG424 DNA (verifica cryptogram AES lato HA)
- Custom component per `UpChar`/`DownChar` su R503 — export/import dei template
  biometrici, per enrollment unico riutilizzabile su più varchi
- Storage cifrato dei template in `/share/fingerprints/`, escluso dai backup
- Secondo nodo `rfid-garage` con le stesse convenzioni
- Tastierino a matrice come fallback per l'impronta
- Accessi temporanei a scadenza (ospiti, nonni)

---

## 13. Ordine di implementazione consigliato

0. **`.gitignore` come primo commit, da solo** (vedi §3) — prima di
   qualunque altro file nel repo
1. Helper e sensori template (§6, §7) — nessuna dipendenza hardware
2. `Access: valuta credenziale ingresso` con finestra oraria fissa — chiude il
   ciclo end-to-end e rende il sistema testabile
3. Macchina a stati completa (§5)
4. Automazioni di sorveglianza (porta socchiusa, incoerenza, maniglia, errore)
5. Dashboard `dashboard-accessi`
6. Fallback locale lato ESPHome

Il punto 2 è quello che trasforma un prototipo in un sistema funzionante:
attualmente il dispositivo legge il tag, invia l'evento e non riceve risposta,
quindi emette sempre il pattern di timeout.

---
---

## 14. Censimento di una tessera

Il flusso, dall'inizio alla fine:

1. Si apre la finestra — dall'interruttore *Censimento tessera*, dal pulsante
   *Aggiungi tessera*, dal pannello o dal servizio `start_enrollment`.
2. Il lettore su cui la finestra è aperta mostra il **colore dedicato**.
   Serve perché il pulsante si preme in casa e la tessera si passa fuori: chi
   arriva al lettore deve poter vedere che la finestra è ancora valida, senza
   rientrare a controllare.
3. La prima tessera letta viene **censita invece che valutata**, con UID e
   tipo di chip rilevati da soli. Nasce senza titolare, e finché non gliene
   viene assegnato uno non apre niente.
4. Il lettore riceve l'esito affermativo — due bip e verde pieno.
5. **La finestra si chiude sulla prima lettura**, non allo scadere: se
   restasse aperta, chiunque passasse una tessera nei secondi successivi se la
   troverebbe censita.

Si chiude anche spegnendo l'interruttore, dal servizio `cancel_enrollment`, o
da sola dopo `ENROLLMENT_TIMEOUT_S` (60 s) di inattività. In tutti i casi la
spia sul lettore si spegne: una finestra chiusa che continua a farsi vedere
aperta è peggio di nessuna spia.

Il censimento è ammesso **solo da un lettore registrato**: una lettura da un
dispositivo che non fa parte dell'impianto non deve poter aggiungere
credenziali.


# Addendum — stato di implementazione

Aggiunto in fase di realizzazione. La specifica sopra resta il documento di
riferimento; questo addendum registra dove l'implementazione si discosta e
perché.

## Fatto

| § | Voce | Stato |
|---|---|---|
| 3 | `.gitignore` come primo commit, da solo | ✅ |
| 6 | Helper (master, stato, finestra, comportamento, registro) | ✅ + `counter.access_rate_limit_hits`, `timer.access_rate_limit_window` |
| 7 | Sensori template + card markdown consolidata | ✅ + `access_finestra_scuola`, `access_presenza_recente`, `access_adulto_in_avvicinamento` |
| 8 | Contratto ESPHome, tre regole vincolanti | ✅ |
| 9 | Valuta credenziale / macchina a stati / socchiusa / incoerenza / errore | ✅ |
| 5 | Macchina a stati completa | ✅ |
| — | Dashboard due viste | ✅ |

## Scostamenti

### §9 — `Access: maniglia azionata a casa vuota` → `Access: apertura non autorizzata`

La serratura non espone lo stato maniglia su questo impianto (vedi
`docs/ENTITIES.md`). Sostituita con un trigger sull'apertura dell'anta a
sistema in `sleep` e casa vuota. Stesso scenario coperto, sorgente che esiste.

### §9 — trigger `tag` → trigger `event: tag_scanned`

La spec prevede un trigger `tag` con l'UID censito. Implementato invece un
unico trigger sull'evento `tag_scanned` grezzo.

Motivo: con un trigger `tag` per credenziale, un tag **sconosciuto** non
attiverebbe alcuna automazione, non riceverebbe risposta, e il dispositivo
emetterebbe il pattern "HA non raggiungibile" — che è diverso dal pattern KO.
Sarebbe una violazione diretta di §8.2: dal feedback si capirebbe se un tag è
censito. Con un unico trigger sull'evento grezzo l'indistinguibilità è
garantita **per costruzione**.

### §6 / §3 — UID negli helper anziché in `secrets.yaml`

§3 ammette entrambi. Scelti gli helper perché il package deve caricare anche
senza chiavi di secrets preesistenti, e perché il confronto fra UID letto e UID
censito avviene in un template, che non può leggere `secrets.yaml`.

### §9.6 — snapshot Ring → `camera_proxy`

Le notifiche allegano l'URL `camera_proxy` invece di uno snapshot su file:
nessuna scrittura su disco, nessuna directory da predisporre, e aggira la
latenza di 5–10 s dello snapshot Ring citata in §4.

## Non implementato

### §10 — fallback locale lato ESPHome

**Contraddice §2, che è marcata "non negoziabile" e cita alla lettera
l'eccezione "solo come fallback".**

Non implementato. Motivo determinante: renderebbe l'apertura ottenibile
impedendo a HA di rispondere, trasformando un guasto di rete — la cosa più
facile da provocare dall'esterno — in una primitiva di apertura.

Resta valido il **fallback manuale** già previsto dalla stessa §10 (key safe o
PIN nativo della serratura), che copre lo stesso caso senza spostare
l'attuazione fuori casa.

Decisione da prendere esplicitamente, non da far scivolare dentro.

### §11 — tamper switch

Hardware non ancora presente (§4 lo elenca fra i previsti).

### §12 — tutto fuori scope come da spec
