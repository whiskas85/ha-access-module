# Controllo Accessi

Integration Home Assistant per il controllo accessi di casa: gestisce le
credenziali, decide chi può entrare e quando, traccia tutto — e **non apre
niente**.

L'apertura la fanno le azioni che configuri tu, su ogni lettore.

[![Validate](https://github.com/whiskas85/ha-access-module/actions/workflows/validate.yml/badge.svg)](https://github.com/whiskas85/ha-access-module/actions/workflows/validate.yml)

---

## Il principio, in una riga

> Il tag **valida l'accesso**. Il lettore **decide l'azione**.
>
> Il lettore esterno legge, Home Assistant decide, le azioni configurate
> aprono. Nessun relè di varco sul dispositivo esterno.

Un attaccante che compromette completamente il dispositivo esterno ottiene la
capacità di *dichiarare* «ho letto il codice X» — non di aprire.

```
   lettore              MODULO                        attuazione
   ───────              ──────                        ──────────
   legge      →   identifica la tessera
   blip 25ms      finestra attiva? ruolo ammesso?
                  sistema in allarme?
                  decide
                  risponde al lettore      →   azioni del LETTORE
                  traccia                      (editor di HA:
                  emette evento                 apri varco, script,
                                                servizio, condizioni…)
```

---

## Perché una credenziale debole è accettabile

Un tag MIFARE Classic è **clonabile in trenta secondi**, e il PN532 letto via
ESPHome fornisce **solo l'UID**, senza autenticazione.

La sicurezza non viene dal tag: viene dalle **finestre**. Le credenziali sono
accettate solo quando una finestra le ammette, e ogni finestra dice quali ruoli
può far entrare, quando, e — se vuoi — da quali lettori.

**Senza finestre non entra nessuno.** Una configurazione vuota è una casa
chiusa, non una casa aperta.

Un tag clonato fuori finestra non apre nulla.

## Due macchine a stati

Sono separate di proposito: tenerle insieme renderebbe impossibile distinguere
«è notte» da «qualcuno sta provando le tessere», che sono la cosa più diversa
che ci sia.

| | Stati | Cosa la muove |
|---|---|---|
| **Autorizzazione** | `chiuso` / `aperto` | finestre orarie, presenza |
| **Sicurezza** | `normale` / `allarme` | letture rifiutate, tessere revocate, tamper |

Si apre solo quando **entrambe** dicono sì.

### L'allarme

Dopo **N letture rifiutate di fila** (default 3), o se passa una tessera
disabilitata o in blacklist, o se un lettore viene manomesso:

- i lettori **smettono di leggere** — LED rosso fisso
- si esce **solo con lo sblocco manuale**
- l'allarme **sopravvive a un riavvio**: non si esce da un blocco di sicurezza
  riavviando

> **La via d'uscita.** Il blocco totale è una difesa contro chi cicla codici
> con un Flipper, ma è anche un modo per lasciare fuori chi ha diritto di
> entrare — e il bambino non ha il telefono. Per questo la notifica di allarme
> porta con sé i pulsanti per **aprire un varco dal telefono senza sbloccare
> l'impianto**: chi è alla porta entra, la difesa resta su.

---

## Installazione

### HACS

1. HACS → Integrazioni → menu ⋮ → **Repository personalizzati**
2. URL `https://github.com/whiskas85/ha-access-module`, categoria *Integration*
3. Installa **Controllo Accessi**, poi riavvia Home Assistant
4. Impostazioni → Dispositivi e servizi → **Aggiungi integrazione** → Controllo Accessi

Nel setup si chiede solo l'essenziale. Tessere, persone, lettori, varchi, finestre,
notifiche e soglie si gestiscono dal pannello **Accessi** che compare nella barra laterale.

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

### Censire una tessera

Non si trascrive nessun UID.

1. Pannello **Accessi** → scheda **Tessere** → **Aggiungi tessera**
2. Passa la tessera al lettore entro 60 secondi
3. Viene censita da sola: UID e tipo di chip li ricava il modulo

La finestra si chiude **alla prima lettura**, o alla scadenza. Non sopravvive
a un riavvio: una modalità che accetta credenziali nuove non deve poter
restare aperta per dimenticanza.

La tessera nasce **senza titolare**, e senza titolare non apre niente.
Trascinala sul riquadro della persona per abbinarla — censire e autorizzare
restano due gesti distinti.

### Livello di sicurezza

Rilevato dalla lunghezza dell'UID, che è normata da ISO/IEC 14443-3:

| UID | Famiglia | Sicurezza |
|---|---|---|
| 4 byte | MIFARE Classic 1K/4K | debole |
| 7 byte | Ultralight / NTAG / DESFire | debole |
| — | NTAG424 con cryptogram verificato | forte |
| — | Impronta R503 | forte |

> **Oggi nessuna tessera può risultare «forte», ed è corretto così.**
>
> Il livello non descrive il chip: descrive il fatto che il modulo abbia
> **verificato crittograficamente** la credenziale. Un NTAG424 di cui si legge
> solo l'UID si clona esattamente come una MIFARE Classic — la protezione sta
> nel cryptogram AES, che oggi nessuno verifica.
>
> Per questo la rilevazione automatica non può promuovere a `forte`, e
> dichiararlo a mano non renderebbe forte la credenziale: farebbe solo credere
> al motore di autorizzazione qualcosa che nessuno ha controllato. Ci si
> arriverà con il componente NTAG424 di §12, quando ci sarà davvero qualcosa
> da verificare.
>
> Che 7 byte non distingua un NTAG213 da un NTAG424 non è quindi un problema:
> senza verifica del cryptogram contano uguale.

Serve censirla da un UID già noto? C'è ancora la via manuale:

```yaml
action: access_control.enroll_card
data:
  uid: "04-A1-B2-C3"        # in qualunque formato: 04a1b2c3, 04:A1:B2:C3, …
  name: portachiavi scuola
  person: person.luca
```

---

## Le persone

I titolari sono le `person.*` di Home Assistant **più** quelle create dal
pannello, nella scheda **Persone**.

Le seconde esistono perché non tutti quelli che entrano in una casa hanno
un'app sul telefono: la nonna e chi viene a fare le pulizie hanno bisogno
delle chiavi, non di un'entità. Da lì in poi valgono come qualunque altro
titolare — prendono un ruolo, e le finestre le fanno entrare in base a quello.

L'unica cosa che non hanno è la **presenza**: il sistema non può sapere se
sono in casa, quindi le regole che dipendono da chi c'è non le riguardano. Le
finestre orarie sì.

### I gruppi

Le persone si dividono in **gruppi**, e sono i gruppi — non le persone — che le
finestre ammettono. È quello che permette di dire «la mattina entrano i
bambini» senza rifare la regola a ogni tessera nuova.

**Bambino** e **adulto** ci sono da subito e non si tolgono: il motore li cita
per nome, «un adulto in avvicinamento ammette gli adulti» è una regola scritta
su quel gruppo. Gli altri si aggiungono dalla scheda Persone — *Pulizie*,
*Ospiti*, quello che serve — e si tolgono quando non servono più.

Togliendo un gruppo, chi ci stava resta **senza gruppo** e non apre più niente
finché non gliene viene dato un altro, e le finestre che lo ammettevano lo
perdono dall'elenco. È brusco ed è voluto: l'alternativa sarebbe spostare
quelle persone in un gruppo scelto dal modulo, cioè dare permessi che nessuno
ha deciso.

Senza gruppo le tessere di quella persona non aprono niente: non viene trattata
come adulto per comodità, che sarebbe darle i permessi più ampi proprio perché
nessuno ha detto chi è.

---

## Le azioni

Il modulo non apre. Ogni **lettore** ha **tre** sequenze di azioni, ed è
**l'editor delle automazioni di Home Assistant** — non un formato inventato
qui.

| Sequenza | Quando parte |
|---|---|
| Tessera valida | accesso consentito |
| Tessera rifiutata | ogni diniego, qualunque sia il motivo |
| Allarme | quando l'allarme si alza — **una volta sola**, non a ogni lettura successiva |

Ogni editor si può usare a riquadri o **in YAML**: una sequenza lunga si legge
tutta insieme, e una che funziona già altrove si incolla invece di ricostruirla
a mano. I due modi guardano lo stesso valore, quindi si passa dall'uno
all'altro senza perdere niente.

### Le notifiche

Ogni tipo di notifica ha due modi, scegliibili dalla sua linguetta.

**Predefinita** — titolo e messaggio, mandati dal modulo al destinatario
configurato, con priorità alta e foto se richieste.

**Personalizzata** — il modulo non manda niente per conto suo ed esegue una
sequenza di azioni, lo stesso editor dei lettori. Serve a chi vuole una
notifica fatta a modo proprio, o qualcosa che notifica non è: accendere una
luce, far parlare un altoparlante, chiamare un webhook. I dati della lettura
arrivano nella variabile `notifica`:

```yaml
- action: notify.mobile_app_telefono
  data:
    message: "{{ notifica.titolare }} è entrato alle {{ notifica.ora }}"
```

I due modi convivono nella stessa configurazione: passando a personalizzata non
si perde il testo scritto, e tornando indietro lo si ritrova.

La conseguenza è che `choose`, `if`, `delay`, `repeat` e i template funzionano
perché non sono riscritti: sono quelli veri, eseguiti dall'helper `Script`. E
quello che vedi nell'editor è letteralmente quello che viene eseguito, senza
traduzione in mezzo che possa mentire.

Nelle azioni hai la variabile `accesso`:

```yaml
- action: access_control.open_gate
  data:
    gate: porta
- action: access_control.open_gate
  data:
    gate: cancelletto
- action: notify.mobile_app_telefono
  data:
    message: "È entrato {{ accesso.person }}"
```

Lettori diversi fanno cose diverse: non è detto che il garage debba fare quello
che fa l'ingresso.

## I varchi

Un varco è un'apertura fisica — porta, garage, cancelletto, cancello —
definita **una volta** e riusabile da più lettori.

| Campo | A cosa serve |
|---|---|
| Entità | `lock.portone`, `switch.cancelletto`, `cover.garage`… |
| Servizio | vuoto = dedotto dal dominio |
| Rispegni dopo | per gli switch impulsivi |

Il servizio si deduce perché è sempre lo stesso: da `lock.` si apre con `open`
(o `unlock` se la serratura non espone lo scrocco), da `switch.` con `turn_on`,
da `cover.` con `open_cover`. Il campo serve solo quando l'ovvio non va bene.

Il **rispegni dopo** esiste perché un relè di cancello lasciato acceso è un
cancello che resta aperto.

## Gli eventi

```yaml
event_type: access_control_event
event_data:
  esito: granted | denied | blacklist | alarm | enrolled
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


## Entità esposte

| Entità | Dice |
|---|---|
| `binary_sensor.*_sistema_armato` | accetterei una credenziale in questo momento? |
| `binary_sensor.*_allarme` | sistema in allarme, col motivo negli attributi |
| `binary_sensor.*_finestra_attiva` | c'è una finestra aperta adesso |
| `sensor.*_stato` | `chiuso` / `aperto`, coi ruoli ammessi negli attributi |
| `sensor.*_motivo_stato` | perché sono in questo stato |
| `sensor.*_stato_porta` | `chiusa` / `aperta` / `in_apertura` / `incoerente` / `errore` |
| `binary_sensor.*_porta_socchiusa` | porta aperta da troppo tempo |
| `sensor.*_ultimo_accesso` | quando e con quale tessera |
| `sensor.*_tentativi_negati_oggi` | coi fallimenti consecutivi negli attributi |
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
| `access_control.open_gate` | apre un varco — è l'azione da usare nei lettori |
| `access_control.start_enrollment` | apre il censimento di una tessera |
| `access_control.start_device_learning` | riconosce un lettore, scartando la tessera |
| `access_control.scan` | valuta una lettura senza andare al varco |
| `access_control.enroll_card` | censisce a mano, da un UID già noto |
| `access_control.set_card_state` | attiva / disabilita / blacklist |
| `access_control.remove_card` | elimina dal registro |
| `access_control.clear_alarm` | sblocca l'allarme e riaccende i lettori |
| `access_control.report_tamper` | segnala una manomissione a mano, o da un sensore che non appartiene a un lettore |
| `access_control.set_reading_enabled` | accende o spegne la lettura |
| `access_control.clear_log` | svuota il registro accessi |

---

## Perché il registro tag non si può inondare

Il firmware **non chiama** `homeassistant.tag_scanned`. Quella chiamata fa
creare a Home Assistant un'entità `tag.*` per **ogni UID mai visto**: chi
arriva con un Flipper e cicla centomila codici crea centomila entità, il
registro tag diventa inservibile e il database si gonfia — e il danno resta
anche dopo che l'attaccante se n'è andato.

Il nodo manda un evento suo, che non crea niente. È il modulo, **dopo** aver
validato la tessera, a farla comparire nel registro tag. Un UID sconosciuto
resta un numero in un contatore.

E in allarme i lettori **smettono proprio di leggere**: l'inondazione si ferma
alla radice, invece di essere rifiutata dopo essere già arrivata.

## Il nodo lettore

`esphome/rfid-ingresso.yaml` — ESP32 con PN532 su I²C a 50 kHz.

| GPIO | Uso |
|---|---|
| 21 / 22 | I²C — PN532 |
| 18 | buzzer attivo |
| 25 / 26 / 27 | LED RGB di stato |
| 32 | tamper (predisposto, da cablare) |

Un **blip di 25 ms** appena legge, prima di tutto: dice «ti ho letto» mentre la
decisione è ancora in viaggio. L'**interruttore di lettura** è quello che
l'allarme spegne, e riparte acceso dopo un blackout — un lettore muto dopo un
calo di tensione è un guasto silenzioso.

Legge, non decide, non attua: **nessun GPIO di quel nodo è collegato a un relè
di un varco, e non deve esserlo mai.** Le chiavi crittografiche future stanno
in Home Assistant, non nella flash di un dispositivo raggiungibile dalla
strada.

`secrets.yaml` non è versionato. Il template è in `esphome/secrets.yaml.example`.

### Come installarlo sul nodo

**HACS aggiorna l'integration, non il nodo.** Copiando il firmware a mano ci
si ritrova prima o poi col repository aggiornato e il dispositivo fermo a una
versione precedente — e il sintomo è che una correzione «non funziona» quando
in realtà non è mai arrivata sul pezzo.

Per evitarlo, la configurazione locale del nodo può essere solo questa:

```yaml
packages:
  controllo_accessi:
    url: https://github.com/whiskas85/ha-access-module
    ref: main
    files: [esphome/rfid-ingresso.yaml]
    refresh: 0s
```

Premere **Install** in ESPHome ripesca la versione aggiornata. I segreti
restano nel `secrets.yaml` dell'add-on, che non passa dal repository.

Il file completo con le spiegazioni è in
[`esphome/nodo-locale.yaml.example`](esphome/nodo-locale.yaml.example).

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
- [`docs/DESIGN-v2.md`](docs/DESIGN-v2.md) — modello dati (storico, pre-v0.8)
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
