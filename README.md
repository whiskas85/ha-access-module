# ha-access-module

Modulo Home Assistant per il controllo accessi di casa: consente il rientro
autonomo senza chiavi e senza telefono, mantenendo **decisione e attuazione
dentro il perimetro di sicurezza**.

Costruito sul modello del modulo irrigazione (`sprinkler_*`) già in esercizio:
stesse convenzioni di prefisso, stessi sensori "cosa succede e perché", stessa
card markdown consolidata.

---

## Il principio, in una riga

> Il lettore esterno **legge**. Home Assistant **decide**. I relè dentro casa
> **aprono**.

Un attaccante che compromette completamente il dispositivo esterno ottiene la
capacità di *dichiarare* «ho letto il codice X» — non di aprire.

| Livello | Dove sta | Cosa fa |
|---|---|---|
| Credenziale | Lettore esterno (ESP32) | Legge, non decide, non attua |
| Decisione | Home Assistant (dentro casa) | Valuta e autorizza |
| Attuazione | Relè già esistenti dentro casa | Apre |

---

## Perché una credenziale debole è accettabile

Il tag MIFARE Classic attualmente in uso è **clonabile in trenta secondi**, e
il PN532 letto via ESPHome fornisce **solo l'UID**, senza autenticazione.

La sicurezza non viene dal tag: viene dalla **macchina a stati**. Le credenziali
sono accettate solo negli stati in cui il sistema è armato, e ogni stato ammette
un sottoinsieme diverso di utenti. Un tag clonato fuori finestra non apre nulla.

| Stato | Come ci si entra | Chi è autorizzato |
|---|---|---|
| `sleep` | default | nessuno |
| `finestra_scuola` | giorno abilitato + orario in finestra | solo il bambino |
| `rientro_adulto` | geofence adulto in avvicinamento | solo adulti |
| `casa_occupata` | presenza rilevata in casa | tutti |

**Non indebolire la macchina a stati per semplificare l'uso.** È ciò che regge
l'intero modello di sicurezza.

---

## Struttura

```
ha-access-module/
├── .gitignore                    ← primo commit, da solo
├── README.md
├── SPEC.md                       ← specifica di riferimento
├── packages/
│   └── access_control.yaml       ← helper, template, automazioni
├── esphome/
│   ├── rfid-ingresso.yaml
│   └── secrets.yaml.example
├── dashboards/
│   └── dashboard-accessi.yaml
├── docs/
│   └── ENTITIES.md               ← mappa entità dell'impianto
└── custom_components/            ← previsti, non ancora implementati
    ├── ntag424/
    └── fingerprint_grow_ext/
```

---

## Installazione

### 1. Package Home Assistant

Copiare `packages/access_control.yaml` in `/config/packages/`, poi assicurarsi
che `configuration.yaml` contenga:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

**Controlla configurazione**, poi riavvia.

### 2. Censire le credenziali

Nessun UID di tag è presente nel repository. Vanno inseriti a mano negli helper,
dalla vista **Setup** della dashboard o da Impostazioni → Helper:

- `input_text.access_cred_bambino`
- `input_text.access_cred_adulto_1`
- `input_text.access_cred_adulto_2`

L'UID va scritto esattamente come lo riporta l'integrazione Tag (maiuscolo, con
trattini). Campo vuoto = credenziale non censita.

### 3. Impostare la finestra scuola

Dalla vista **Setup**: orario di inizio e fine, e quali giorni sono abilitati.
La finestra è chiusa di default nel weekend, a prescindere dagli helper.

### 4. Dashboard

Creare una dashboard vuota con URL `dashboard-accessi` e incollare il contenuto
di `dashboards/dashboard-accessi.yaml` nell'editor YAML.

### 5. Nodo ESPHome

Copiare `esphome/secrets.yaml.example` in `esphome/secrets.yaml`, valorizzarlo,
poi compilare `rfid-ingresso.yaml`. `secrets.yaml` è escluso dal versionamento.

---

## Il contratto con il dispositivo

**In ingresso a HA:** evento `tag_scanned` (integrazione Tag nativa) con l'UID.

**In uscita da HA:**

```yaml
action: esphome.rfid_ingresso_esito_accesso
data:
  esito: "ok"    # oppure "ko"
```

### Tre regole vincolanti

**1. Rispondere sempre, anche negando.** Se HA tace, dopo 3 secondi il
dispositivo emette il pattern «non raggiungibile» e l'utente crede che il
sistema sia guasto quando era solo fuori orario. Ogni ramo dell'automazione
termina con una chiamata a `esito_accesso` — incluso il ramo `default`.

**2. Il feedback non rivela mai il motivo del diniego.** Tag sconosciuto, tag
valido fuori finestra, tag valido con sistema disarmato: tutti `ko`, identico.
Altrimenti chi trova un tag capisce dal buzzer se quel tag è censito e vale la
pena tornare a un altro orario. Il motivo reale va nel logbook e nella notifica.

> Questa regola è il motivo per cui la valutazione vive in **una sola**
> automazione con trigger sull'evento `tag_scanned` grezzo, invece di una
> automazione per tag. Con un trigger `tag` per credenziale, un tag ignoto non
> attiverebbe nulla, non riceverebbe risposta, e il timeout rivelerebbe proprio
> l'informazione che stiamo proteggendo. Qui l'indistinguibilità è garantita
> **per costruzione**, non per disciplina.

**3. Il rate limiter esiste in entrambi i lati.** Quello nell'ESP (3 letture /
10 s) evita che un tag appoggiato al lettore inondi l'API. Quello in HA è quello
che conta: un firmware sostituito aggirerebbe il primo.

### Pattern acustici

| Esito | Pattern |
|---|---|
| OK | due bip corti ravvicinati (60 / 80 / 60 ms) |
| KO | un bip lungo (1200 ms) |
| HA non risponde | tre bip corti distanziati, dopo 3 s di attesa |

---

## Trasparenza: cosa farebbe il sistema adesso, e perché

Sul modello di `binary_sensor.sprinkler_will_water_today` +
`sensor.sprinkler_watering_reason`, la logica è ispezionabile senza aprire le
automazioni:

| Entità | Dice |
|---|---|
| `binary_sensor.access_armed` | accetterei una credenziale in questo momento? |
| `sensor.access_state_reason` | perché sono in questo stato |
| `sensor.access_door_status` | `chiusa` / `aperta` / `in_apertura` / `incoerente` / `errore` |
| `binary_sensor.access_door_ajar` | porta aperta da troppo tempo |
| `binary_sensor.access_finestra_scuola` | la finestra è attiva adesso |
| `binary_sensor.access_presenza_recente` | presenza, con il ritardo di sleep già applicato |

`sensor.access_door_status` incrocia **due fonti indipendenti** — la serratura e
il reed sull'anta. Se si contraddicono (anta aperta mentre la serratura dichiara
chiusa a chiave) è un guasto o un forzamento, e diventa lo stato distinto
`incoerente` con notifica immediata.

Nota: anta chiusa + serratura sbloccata **non** è incoerente. È la condizione
normale di porta accostata ma non mandata in sicurezza.

---

## Sicurezza

### Requisiti rispettati

- Password API, OTA e AP in `secrets.yaml`, mai versionate
- API ESPHome con cifratura Noise attiva
- Nodo esterno su VLAN/SSID IoT isolata
- Ogni tentativo, riuscito o negato, finisce nel logbook
- Nessun UID di tag nel repository

### Mai fare

- Relè di apertura sull'ESP32 esterno — **nemmeno come fallback** (vedi sotto)
- Template biometrici in `/config` se versionato, in attributi di entità, o in
  `input_text`: finirebbero in recorder, logbook e backup
- `ESP_LOGD` sui byte di un template biometrico
- Feedback differenziato per motivo di diniego

### Il repository è pubblico

Pubblicare la *logica* è coerente con il principio di Kerckhoffs: la sicurezza
sta nelle chiavi, non nella segretezza del progetto. Pubblicare le *credenziali*
no.

Il `.gitignore` è il primo commit del repo, da solo e prima di ogni altro file.
Se un `secrets.yaml` entrasse nella storia, rimuoverlo con un commit successivo
non basterebbe: la storia andrebbe riscritta con `git filter-repo`.

---

## Punto aperto: il fallback locale

La spec §10 chiede che l'ESP apra autonomamente il cancelletto quando HA non
risponde ed è in corso la finestra scuola. La spec §2, sotto l'intestazione
«non negoziabile», vieta esattamente questo — citando alla lettera l'eccezione
«solo come fallback».

**Le due sezioni si contraddicono, e qui vince §2.** Il fallback locale non è
implementato. Il motivo determinante: renderebbe l'apertura ottenibile
semplicemente impedendo a HA di rispondere. Un attaccante che disturba la rete —
la cosa più facile da fare dall'esterno — otterrebbe l'apertura. Si
trasformerebbe un guasto di rete in una primitiva di apertura.

L'alternativa che copre lo stesso caso quotidiano senza spostare l'attuazione
fuori casa è il **fallback manuale** già previsto dalla stessa §10: key safe con
combinazione, oppure PIN nativo della serratura. Nessuno dei due dipende da rete,
da HA o dall'alimentazione del lettore.

Se il fallback locale va comunque implementato, è una decisione da prendere
esplicitamente — non da far scivolare dentro come dettaglio implementativo.

---

## Fuori scope di questa iterazione

- Custom component ESPHome per NTAG424 DNA (verifica cryptogram AES lato HA)
- Custom component `UpChar`/`DownChar` su R503 — export/import dei template
  biometrici, per enrollment unico riutilizzabile su più varchi
- Storage cifrato dei template in `/share/fingerprints/`, escluso dai backup
- Secondo nodo `rfid-garage` con le stesse convenzioni
- Tastierino a matrice come fallback per l'impronta
- Accessi temporanei a scadenza (ospiti, nonni)
