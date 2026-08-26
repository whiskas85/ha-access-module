# Controllo Accessi

Integration Home Assistant per il controllo accessi di casa: gestisce le
credenziali, decide chi può entrare e quando, traccia tutto — e **non apre
niente**.

L'apertura la fanno gli script che configuri tu.

[![Validate](https://github.com/whiskas85/ha-access-module/actions/workflows/validate.yml/badge.svg)](https://github.com/whiskas85/ha-access-module/actions/workflows/validate.yml)

---

## Il principio, in una riga

> Il lettore esterno **legge**. Home Assistant **decide**. Gli script **aprono**.

Un attaccante che compromette completamente il dispositivo esterno ottiene la
capacità di *dichiarare* «ho letto il codice X» — non di aprire.

```
   lettore              MODULO                       attuazione
   ───────              ──────                       ──────────
   legge      →   identifica la tessera
                  valuta stato + sicurezza
                  + titolare + stato sistema
                  decide
                  emette evento           →   pre-hook  (può vietare)
                  risponde al lettore     →   script del varco
                  traccia                 →   post-hook
```

---

## Perché una credenziale debole è accettabile

Un tag MIFARE Classic è **clonabile in trenta secondi**, e il PN532 letto via
ESPHome fornisce **solo l'UID**, senza autenticazione.

La sicurezza non viene dal tag: viene dalla **macchina a stati**. Le
credenziali sono accettate solo negli stati in cui il sistema è armato, e ogni
stato ammette un sottoinsieme diverso di titolari.

| Stato | Come ci si entra | Chi è autorizzato |
|---|---|---|
| `sleep` | default | nessuno |
| `finestra_scuola` | giorno abilitato + orario in finestra | solo il bambino |
| `rientro_adulto` | un adulto entra nella zona di avvicinamento | solo adulti |
| `casa_occupata` | presenza rilevata in casa | tutti |

Sopra a questo, il **livello di sicurezza della tessera** restringe ancora:
una credenziale debole vale solo sul varco pedonale, qualunque sia lo stato.

Un tag clonato fuori finestra non apre nulla. **Non indebolire la macchina a
stati per semplificare l'uso** — è ciò che regge l'intero modello.

---

## Installazione

### HACS

1. HACS → Integrazioni → menu ⋮ → **Repository personalizzati**
2. URL `https://github.com/whiskas85/ha-access-module`, categoria *Integration*
3. Installa **Controllo Accessi**, poi riavvia Home Assistant
4. Impostazioni → Dispositivi e servizi → **Aggiungi integrazione** → Controllo Accessi

Nel setup si chiede solo l'essenziale. Tessere, varchi, hook e soglie si
gestiscono dal pannello **Accessi** che compare nella barra laterale.

### Manuale

Copiare `custom_components/access_control/` in `/config/custom_components/` e
riavviare.

---

## Le tessere

Ogni tessera ha un titolare, una tecnologia e uno stato.

| Stato | Cosa fa | Quando usarlo |
|---|---|---|
| **attiva** | valutata normalmente | |
| **disabilitata** | non apre, non allarma | tessera riposta in un cassetto |
| **blacklist** | non apre, **allarma se ripassa** | tessera persa o rubata |
| *eliminata* | torna sconosciuta, non allarma | tessera dismessa davvero |

Per una tessera persa serve la **blacklist**, non l'eliminazione: una tessera
eliminata è di nuovo una sconosciuta qualsiasi, e ripassandola non succede
niente di visibile.

### Livello di sicurezza

| Tecnologia | Sicurezza | Perché |
|---|---|---|
| MIFARE Classic (solo UID) | debole | clonabile in trenta secondi |
| MIFARE Ultralight (solo UID) | debole | idem |
| NTAG424 DNA con cryptogram | forte | AES-128 verificato lato HA |
| Impronta R503 | forte | non clonabile per presentazione |

> **La tecnologia va dichiarata a mano.** Il PN532 letto via ESPHome espone
> solo l'UID: non basta a classificare la tessera, e la lunghezza dell'UID è un
> indizio, non una prova. Perché la classificazione diventi automatica e non
> falsificabile serve un custom component ESPHome che riporti SAK/ATQA
> (`0x08` = MIFARE Classic 1K, `0x20` = ISO14443-4). Il modello dati è già
> pronto: cambierebbe solo chi scrive il campo.

### Censire una tessera

Passala al lettore una volta: la lettura finisce nel registro come sconosciuta
e da lì copi l'UID. Oppure via servizio:

```yaml
action: access_control.enroll_card
data:
  uid: "04-A1-B2-C3"
  name: portachiavi scuola
  person: person.luca
  technology: mifare_classic
```

---

## Gli hook

Il modulo non apre. Chiama, in ordine:

| Fase | Obbligatorio | Se fallisce |
|---|---|---|
| **pre-hook** | no | l'apertura non procede (o procede, vedi sotto) |
| **script del varco** | **sì** | esito `ko`, tracciato nel registro |
| **post-hook** | no | solo log |

Tutti ricevono l'evento completo nella variabile `accesso`.

Il pre-hook vieta l'apertura restituendo `allow: false`:

```yaml
sequence:
  - if:
      - condition: state
        entity_id: cover.piscina
        state: open
    then:
      - stop: "Piscina scoperta"
        response_variable: esito
variables:
  esito:
    allow: false
```

**Fail-open sul pre-hook** (impostabile per varco): un pre-hook che va in
errore si comporta come se non ci fosse, perché la decisione di base ha già
superato tutta la policy. Fail-closed trasformerebbe un refuso in uno script in
un bambino chiuso fuori.

Se un varco non ha script di apertura configurato, il modulo **nega** e lo
scrive nel registro. Non apre "di default".

---

## Gli eventi

```yaml
event_type: access_control_event
event_data:
  esito: granted | denied | blacklist | lockout
  motivo: sistema_in_sleep
  uid: "04-A1-B2-C3"
  card_nome: portachiavi scuola
  card_stato: attiva
  card_sicurezza: debole
  person: person.luca
  ruolo: bambino
  varco: ingresso
  stato_sistema: finestra_scuola
  timestamp: "2026-08-26T15:42:11+00:00"
```

---

## Il feedback al lettore

Due regole, e nessuna delle due è negoziabile.

**1. Rispondere sempre, anche negando.** Se il modulo tace, dopo 3 secondi il
dispositivo emette il pattern «non raggiungibile» e chi è alla porta crede che
il sistema sia guasto quando era solo fuori orario.

**2. Il feedback non rivela mai il motivo del diniego.** Tessera sconosciuta,
disabilitata, in blacklist, valida fuori finestra, lettori bloccati: tutti
`ko`, identico. Altrimenti chi trova una tessera capisce dal buzzer se quella
tessera è censita e se vale la pena tornare a un altro orario.

> Per questo il modulo si aggancia all'evento `tag_scanned` **grezzo** e non a
> un trigger per tessera censita. Con un aggancio per tessera, una lettura
> ignota non attiverebbe nulla, il lettore andrebbe in timeout e suonerebbe il
> pattern sbagliato — rivelando proprio l'informazione da proteggere. Così
> l'indistinguibilità è garantita **per costruzione**.

La blacklist fa eccezione solo sul canale: al lettore arriva un `ko` come tutti
gli altri, e l'allarme ad alta priorità arriva sul telefono.

---

## Lockout dei lettori

Dopo N letture rifiutate consecutive, due comportamenti possibili:

| Modalità | Cosa blocca | Default |
|---|---|---|
| `segnala` | nulla — notifica, evento, contatore | ✅ |
| `blocca` | ogni lettura, comprese quelle valide | |

Il default è `segnala`, ed è una scelta di sicurezza. Un lockout che blocca
tutto è **banalmente armabile contro chi deve entrare**: bastano N letture di
una tessera qualsiasi. E in cambio difende da un brute-force dell'UID che a
tre letture ogni dieci secondi su quattro miliardi di combinazioni
richiederebbe comunque secoli. Blocca l'unica persona che deve entrare e non
ferma nessuno che conti davvero.

Chi vuole `blocca` lo imposta sapendo che serve un fallback fisico
indipendente, o il bambino resta fuori.

---

## Entità esposte

| Entità | Dice |
|---|---|
| `binary_sensor.*_sistema_armato` | accetterei una credenziale in questo momento? |
| `sensor.*_motivo_stato` | perché sono in questo stato |
| `sensor.*_stato_porta` | `chiusa` / `aperta` / `in_apertura` / `incoerente` / `errore` |
| `binary_sensor.*_porta_socchiusa` | porta aperta da troppo tempo |
| `binary_sensor.*_lettori_bloccati` | lockout in corso |
| `sensor.*_ultimo_accesso` | quando e con quale tessera |
| `sensor.*_tentativi_negati_oggi` | con i fallimenti consecutivi negli attributi |
| `switch.*_master_accessi` | abilitazione generale |

`sensor.*_stato_porta` incrocia **due fonti indipendenti** — la serratura e il
contatto sull'anta. Se si contraddicono (anta aperta mentre la serratura
dichiara chiusa a chiave) diventa `incoerente`: è un guasto o un forzamento.

Anta chiusa con serratura sbloccata **non** è incoerente: è la porta accostata
ma non mandata in sicurezza, cioè la condizione normale di casa abitata.

---

## Servizi

| Servizio | Cosa fa |
|---|---|
| `access_control.scan` | valuta una lettura senza andare al varco |
| `access_control.enroll_card` | censisce o aggiorna una tessera |
| `access_control.set_card_state` | attiva / disabilita / blacklist |
| `access_control.remove_card` | elimina dal registro |
| `access_control.unlock_readers` | azzera il lockout |
| `access_control.clear_log` | svuota il registro accessi |

---

## Il nodo lettore

`esphome/rfid-ingresso.yaml` — ESP32 con PN532 su I²C a 50 kHz e buzzer attivo.

Legge, non decide, non attua: **nessun GPIO di quel nodo è collegato a un relè
di un varco, e non deve esserlo mai.** Le chiavi crittografiche future stanno
in Home Assistant, non nella flash di un dispositivo raggiungibile dalla
strada.

`secrets.yaml` non è versionato. Il template è in `esphome/secrets.yaml.example`.

### Il fallback locale non è implementato

La specifica lo chiede al §10 e lo vieta al §2, che è marcata «non negoziabile»
e cita alla lettera l'eccezione «solo come fallback».

Vince §2. Un fallback che apre quando Home Assistant non risponde rende
l'apertura ottenibile **disturbando la rete** — la cosa più facile da fare
dall'esterno. Trasformerebbe un guasto di rete in una primitiva di apertura.

L'alternativa che copre lo stesso caso quotidiano senza spostare l'attuazione
fuori casa è il fallback manuale già previsto dalla stessa §10: key safe con
combinazione, o PIN nativo della serratura. Nessuno dei due dipende da rete, da
Home Assistant o dall'alimentazione del lettore.

---

## Documentazione

- [`SPEC.md`](SPEC.md) — specifica di riferimento, con addendum sugli scostamenti
- [`docs/DESIGN-v2.md`](docs/DESIGN-v2.md) — modello dati, hook, lockout
- [`docs/ENTITIES.md`](docs/ENTITIES.md) — mappa entità e limiti dell'impianto
- [`CHANGELOG.md`](CHANGELOG.md)

---

## Fuori scope, per ora

- Custom component ESPHome per NTAG424 DNA (cryptogram AES verificato lato HA)
- Custom component `UpChar`/`DownChar` su R503 — enrollment unico riutilizzabile
- Storage cifrato dei template biometrici, escluso dai backup
- Secondo nodo `rfid-garage`
- Tastierino a matrice come fallback per l'impronta
- Accessi temporanei a scadenza (ospiti, nonni)

## Licenza

MIT — vedi [LICENSE](LICENSE).
