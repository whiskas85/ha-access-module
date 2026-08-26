# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il progetto usa [Semantic Versioning](https://semver.org/lang/it/).

Le nuove voci vanno scritte sotto la sezione *Unreleased*. Al momento del
rilascio, `scripts/bump.py` le promuove alla nuova versione con la data.

## [Unreleased]

## [0.3.0] - 2026-08-26

### Aggiunto

- **Il censimento si apre su un lettore preciso.** Un pulsante per varco, che
  dice quale — «abilita lettura» con più lettori non era un'istruzione
  completa. Una lettura che arriva da un altro varco mentre il censimento è
  aperto viene **valutata normalmente, non censita**: altrimenti una tessera
  passata al garage mentre censisci all'ingresso finirebbe nel registro senza
  che nessuno l'abbia voluta
  - Sotto ogni pulsante c'è il lettore a cui il varco è legato. Se manca e i
    varchi sono più di uno, il pannello lo segnala: senza `reader_device_id`
    ogni lettura viene attribuita al primo varco, e un censimento aperto sul
    secondo resterebbe in attesa per sempre
- **Il riepilogo tessere è raggruppato per titolare**, e ogni gruppo è la
  scheda della persona: foto, ruolo, se è in casa, quante tessere ha. La
  scheda è anche il bersaglio del trascinamento, quindi si vede dove si sta
  lasciando la tessera
- **Le tessere senza titolare hanno un gruppo tutto loro, in cima e
  evidenziato**, con scritto che non aprono. Erano la cosa più facile da
  perdere di vista, ed è proprio quella che va sistemata
- **Il nome della tessera si scrive dalla tabella.** Prima non c'era modo di
  darle un titolo dopo il censimento
- Le azioni hanno un'icona ciascuna

### Corretto

- **Un censimento veniva contato fra i tentativi negati.** Il conteggio
  sommava tutto ciò che non era `granted`, quindi gonfiava le statistiche
  proprio mentre si configurava il sistema — cioè quando quel numero viene
  guardato di più. Ora si elencano i rifiuti veri, così un esito nuovo non
  finisce fra i negati per il solo fatto di essere nuovo
- **La riga della tabella si spezzava sotto la colonna Azioni.** I pulsanti
  avevano `display:flex` sulla cella, che toglie il `<td>` dal layout della
  tabella e interrompe il bordo inferiore. Ora stanno in un contenitore dentro
  la cella
- I caratteri di tutta la pagina erano troppo piccoli per una pagina che si
  legge in piedi col telefono in mano

### Modificato

- L'evento di censimento porta con sé tutto — nome, tecnologia, livello,
  lunghezza dell'UID, varco, stato del sistema — così a valle non serve
  rileggere il registro per farci qualcosa

## [0.2.0] - 2026-08-26

### Aggiunto

- **Le tessere si censiscono passandole al lettore, non trascrivendo l'UID.**
  «Abilita lettura tessera» apre una finestra di 60 secondi: la prima lettura
  viene registrata invece che valutata, con UID e tipo di chip ricavati da
  soli. La finestra si chiude alla prima lettura o alla scadenza, quale delle
  due viene prima — una modalità che accetta credenziali nuove non deve poter
  restare aperta per dimenticanza, e non sopravvive nemmeno a un riavvio
  - La tessera nasce **senza titolare**, e senza titolare non apre niente:
    censire e autorizzare restano due gesti distinti
  - Disponibile anche come pulsante (`button.*_abilita_lettura_tessera`) e
    come azione `access_control.start_enrollment`
- **Il tipo di tessera viene rilevato, non chiesto.** Chi le compra non ha
  modo di sapere che chip ci sia dentro, e una dichiarazione sbagliata sarebbe
  diventata un permesso sbagliato. La lunghezza dell'UID è normata da
  ISO/IEC 14443-3 e distingue le due famiglie che contano: 4 byte MIFARE
  Classic, 7 byte Ultralight/NTAG/DESFire
- **Una tessera si abbina a un titolare trascinandola** sul suo riquadro. Il
  riquadro «senza titolare» stacca l'abbinamento
- **Stato della tessera con pulsanti al posto della tendina.** Con la tendina
  il cambio partiva al primo movimento della rotellina sopra il campo: su un
  elenco di tessere era un modo silenzioso per mettere in blacklist quella
  sbagliata. La blacklist chiede conferma, perché è l'unica azione che genera
  allarmi

### Corretto

- **Lo stesso UID scritto in due modi diversi finiva su due righe diverse.**
  `04A1B2C3` senza separatori non collassava su `04-A1-B2-C3`: una tessera
  censita da un lettore e riletta da un altro poteva risultare non censita.
  Il diniego che ne seguiva era indistinguibile da uno legittimo, quindi il
  sintomo sarebbe stato solo «a volte non apre». Ora i separatori vengono
  tolti tutti e rimessi a passo fisso

### Sicurezza

- **`forte` non è più raggiungibile dalla rilevazione automatica, ed è
  corretto così.** Il livello non descrive il chip: descrive il fatto che il
  modulo abbia *verificato crittograficamente* la credenziale. Un NTAG424 di
  cui si legge solo l'UID si clona esattamente come una MIFARE Classic — la
  protezione sta nel cryptogram AES, che oggi nessuno verifica. Dichiarare a
  mano una tessera «forte» non l'avrebbe resa tale: avrebbe solo fatto credere
  al motore di autorizzazione qualcosa che nessuno ha controllato

## [0.1.0] - 2026-08-26

### Aggiunto

- **Il modulo decide e registra, ma non apre più.** L'apertura è delegata a
  uno script configurabile per varco, con un hook prima e uno dopo. Cambiare
  *cosa* succede quando qualcuno entra — accendere le luci, disarmare
  l'antifurto, aprire solo il cancelletto di notte — non richiede più di
  toccare il modulo
  - Il **pre-hook può vietare** l'apertura restituendo `{"allow": false}`: è
    il punto di estensione per le regole che non vale la pena scrivere qui
    dentro. Gira prima della risposta al lettore, perché partecipa alla
    decisione, ma con un budget di 1,5 s — oltre quello la risposta
    arriverebbe dopo il timeout del dispositivo, e chi è alla porta sentirebbe
    "sistema guasto" invece di "no"
  - Se un varco non ha script di apertura configurato, il modulo **nega** e lo
    scrive nel registro. Non apre "di default"
- **Registro tessere con ciclo di vita.** Ogni tessera ha un titolare, una
  tecnologia e uno stato. *Disabilitata* e *blacklist* sono cose diverse di
  proposito: una tessera riposta in un cassetto non deve allarmare quando
  qualcuno la prova, una tessera persa sì
- **Il livello di sicurezza restringe cosa una tessera può fare.** L'UID di
  una MIFARE Classic si clona in trenta secondi: una credenziale debole vale
  solo sul varco pedonale, qualunque sia lo stato del sistema
  - La tecnologia va dichiarata all'enrollment. Il PN532 letto via ESPHome
    espone solo l'UID, e da quello la tecnologia non si deduce: la lunghezza
    dell'UID è un indizio, non una prova. Servirà un custom component che
    riporti SAK/ATQA perché la classificazione diventi automatica
- **Lockout dei lettori dopo N letture rifiutate**, in due modalità.
  `segnala` conta e notifica senza fermare nessuno; `blocca` rifiuta ogni
  lettura, comprese quelle valide
  - Il default è `segnala`, ed è una scelta di sicurezza e non una comodità:
    bastano N letture di una tessera qualsiasi per armare un lockout contro
    chi ha diritto di entrare, mentre il brute-force dell'UID che il blocco
    fermerebbe richiederebbe comunque secoli a tre letture ogni dieci secondi.
    Blocca l'unica persona che deve entrare e non ferma nessuno che conti
- **Eventi `access_control_event` sul bus** a ogni valutazione, con esito,
  motivo, tessera, titolare, varco e stato del sistema. Qualunque automazione
  può reagire senza toccare il modulo
- **Registro accessi con pannello dedicato.** Le righe vivono
  nell'integration, non nel recorder: un registro accessi che si autocancella
  dopo dieci giorni non è un registro accessi
- **Pannello nella barra laterale** con quattro schede — stato, tessere,
  registro, impostazioni — e un pulsante per provare una lettura senza andare
  al varco
- Macchina a stati `sleep` / `finestra_scuola` / `rientro_adulto` /
  `casa_occupata`, e i sensori che dicono **cosa farebbe il sistema adesso e
  perché**, così la logica è ispezionabile senza leggere il codice

### Sicurezza

- **Una lettura sconosciuta riceve lo stesso `ko` di una valida fuori
  orario.** Il modulo si aggancia all'evento `tag_scanned` grezzo e non a un
  trigger per tessera censita: con un aggancio per tessera, una lettura ignota
  non attiverebbe nulla, il lettore andrebbe in timeout e suonerebbe il
  pattern "non raggiungibile" — dicendo a chi ha in mano la tessera che quella
  tessera non è censita, cioè esattamente l'informazione da proteggere. Così
  l'indistinguibilità è garantita per costruzione, non per disciplina
- **La blacklist allarma la famiglia, non chi ha la tessera in mano.** Al
  lettore arriva un `ko` come tutti gli altri; la notifica ad alta priorità
  arriva sul telefono
- **Il fallback locale sull'ESP32 resta non implementato.** La specifica lo
  chiede al §10 e lo vieta al §2, che è marcata non negoziabile e cita alla
  lettera l'eccezione "solo come fallback". Vince §2: un fallback che apre
  quando Home Assistant non risponde rende l'apertura ottenibile disturbando
  la rete, che è la cosa più facile da fare dall'esterno. Resta valido il
  fallback manuale — key safe o PIN della serratura — che copre lo stesso caso
  senza spostare l'attuazione fuori casa

### Rimosso

- Il package YAML della prima iterazione, spostato in `docs/legacy-v1/`.
  Tenerlo installato accanto al componente non è neutro: si aggancia anch'esso
  a `tag_scanned`, quindi ogni lettura verrebbe valutata due volte e il lettore
  riceverebbe due risposte, potenzialmente in disaccordo fra loro
