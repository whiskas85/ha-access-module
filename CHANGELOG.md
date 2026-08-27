# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il progetto usa [Semantic Versioning](https://semver.org/lang/it/).

Le nuove voci vanno scritte sotto la sezione *Unreleased*. Al momento del
rilascio, `scripts/bump.py` le promuove alla nuova versione con la data.

## [Unreleased]

### Corretto

- `scripts/check_api.py` era stato committato con un `if` annidato che ruff
  segnala: la CI della 0.8.2 falliva sul file appena aggiunto per far passare
  la CI. Nessun effetto sul funzionamento


## [0.8.2] - 2026-08-27

### Corretto

- **Il pannello restava su «Impossibile leggere lo stato» e nessuna scheda
  funzionava.** Tre regressioni introdotte dalla 0.8.0, tutte mie:
  - `coordinator.is_armed` era stato rinominato in `is_open`, ma il pannello
    lo chiamava ancora: `AttributeError` dentro la vista HTTP, quindi 500 su
    ogni lettura di stato. Ruff non poteva vederlo — è un accesso ad
    attributo, lecito fino a runtime
  - stessa cosa per `store.async_unlock_readers()`, sostituito da
    `async_clear_alarm()`
  - `customElements.define` non era protetto. Da quando l'URL del modulo porta
    la versione, lo stesso file può essere caricato due volte nella stessa
    pagina — la copia in cache e quella nuova — e il secondo `define` solleva,
    facendo fallire l'intero modulo

### Aggiunto

- **`scripts/check_api.py`**, che confronta gli attributi usati su store,
  coordinator ed evaluator con quelli davvero definiti, e gira in CI. È il
  controllo che mancava: un rinomino lasciato a metà non rompeva né il lint né
  la compilazione, si vedeva solo come «Impossibile leggere lo stato» senza
  alcun indizio su cosa fosse stato rinominato
- La CI controlla anche la sintassi del pannello con `node --check`

## [0.8.1] - 2026-08-27

### Documentazione

- README riscritto sul modello v0.8: due macchine a stati, finestre, azioni
  per lettore, varchi, e la sezione sul perché il registro tag non si può più
  inondare. Descriveva ancora hook e lockout, che non esistono più

## [0.8.0] - 2026-08-27

### Aggiunto

- **Due macchine a stati separate, e la separazione è il punto.**
  *Autorizzazione* dice chi può entrare adesso; *Sicurezza* dice se sta
  succedendo qualcosa. Tenerle in un unico stato rendeva la dashboard
  illeggibile: non si distingueva «è notte» da «qualcuno sta provando le
  tessere», che sono la cosa più diversa che ci sia
  - Dopo **N letture rifiutate di fila** (default 3), o se passa una tessera
    disabilitata o in blacklist, o se un lettore viene manomesso, il sistema
    va in **allarme**: i lettori si spengono e si riparte solo a mano
  - L'allarme **sopravvive a un riavvio**: non si esce da un blocco di
    sicurezza riavviando
  - Un secondo allarme non sovrascrive il motivo del primo — quello che conta
    è cosa è successo per primo
- **Finestre configurabili al posto della «finestra scuola».** Ne crei quante
  vuoi: nome, orario, giorni, quali ruoli ammette e — se vuoi — su quali
  lettori soltanto. **Senza finestre non entra nessuno**: una configurazione
  vuota è una casa chiusa, non una casa aperta
  - Le opzioni di presenza («c'è qualcuno in casa», «un adulto sta
    rientrando») restano ma si **sommano** alle finestre invece di essere
    regole scritte nel codice
- **Le azioni sono l'editor delle automazioni di Home Assistant.** Non un
  formato inventato: la sequenza è quella vera, eseguita dall'helper `Script`.
  `choose`, `if`, `delay`, i template funzionano perché non sono riscritti — e
  quello che vedi nell'editor è letteralmente quello che gira
  - **Ogni lettore ha le sue**: il tag valida l'accesso, il dispositivo decide
    l'azione
  - Scorciatoie per aggiungere l'apertura di un varco con un clic
- **Scheda Varchi.** Un varco è un'apertura fisica definita una volta e
  riusabile: si apre con `access_control.open_gate`, che nell'editor compare
  come un'azione qualsiasi. Il servizio si deduce dal dominio dell'entità, e
  gli switch impulsivi hanno il rispegnimento automatico — un relè di cancello
  lasciato acceso è un cancello che resta aperto
- **Scheda Notifiche.** Master generale, interruttore per tipo, destinatario e
  testo per ciascuno, con segnaposto `{tessera}` `{titolare}` `{lettore}`
  `{motivo}` `{ora}` `{stato}`. Un segnaposto scritto male resta com'è invece
  di far fallire la notifica — che per un allarme sarebbe il momento peggiore
  per scoprire un refuso
- **Dashboard di stato che racconta il sistema**: le due macchine affiancate,
  cosa le muove, e cosa succede dopo N errori

### Sicurezza

- **Il registro tag di Home Assistant non si può più inondare.** Il firmware
  non chiama più `homeassistant.tag_scanned`, che faceva creare a HA
  un'entità per **ogni UID mai visto**: chi cicla centomila codici con un
  Flipper creava centomila entità, rendendo inservibile il registro e
  gonfiando il database. Ora il nodo manda un evento suo, e il tag entra nel
  registro **solo dopo che la lettura è stata validata**
- **In allarme i lettori smettono di leggere.** Ferma l'inondazione alla
  radice invece di limitarsi a rifiutarla dopo averla ricevuta
- **La via d'uscita.** La notifica di allarme porta i pulsanti per aprire un
  varco dal telefono **senza sbloccare l'impianto**: chi è alla porta entra,
  la difesa resta su

### Modificato

- Il pre-hook e il post-hook non esistono più: erano un'astrazione che non
  serviva a niente di concreto, e l'editor di azioni copre tutto quello che
  facevano e molto altro
- Il lockout in modalità «segnala» è stato sostituito dall'allarme vero

### Firmware ESP32

- **Blip di 25 ms appena legge**, prima di tutto: dice «ti ho letto» mentre la
  decisione è ancora in viaggio
- **Interruttore di lettura** esposto a HA, che è ciò che l'allarme spegne.
  Riparte acceso dopo un blackout: un lettore muto dopo un calo di tensione è
  un guasto silenzioso
- **LED RGB** su GPIO25/26/27 — verde tenue a riposo, verde all'ok, rosso al
  ko, **rosso fisso** quando la lettura è disabilitata
- **Tamper predisposto** su GPIO32, da cablare
- Pattern acustico dedicato all'allarme

## [0.7.0] - 2026-08-26

### Aggiunto

- **Il pannello dice quando la pagina che stai guardando è vecchia.** La
  versione era già dichiarata dal pannello e tenuta allineata dal bump, ma il
  confronto non era mai stato scritto: il risultato è che sul telefono si
  poteva restare su una versione di due settimane prima senza alcun segnale,
  convinti che mancassero funzioni che invece c'erano
  - I due disallineamenti hanno cause opposte e il messaggio lo dice: pannello
    più vecchio dell'integration significa **copia in cache del browser** (e
    compare il pulsante **Ricarica**); pannello più nuovo significa **Home
    Assistant non ancora riavviato**, e lì ricaricare non serve a niente
  - Il pulsante Ricarica svuota la Cache Storage e aggiorna il service worker
    prima di ricaricare: un `location.reload()` semplice può restituire di
    nuovo proprio il file che è il problema
  - Il confronto è numerico e non alfabetico, altrimenti `0.10.0` risulterebbe
    più vecchio di `0.9.0`
- **L'URL del pannello porta la versione** (`?v=…`). È la prevenzione, non il
  rimedio: `cache_headers=False` non basta perché il frontend di Home
  Assistant ha un service worker che conserva le risorse per conto suo. A ogni
  versione l'URL cambia, quindi il browser chiede una risorsa che in cache non
  può avere

## [0.6.1] - 2026-08-26

### Corretto

- **Il censimento offriva i varchi invece dei lettori.** Con zero lettori
  registrati mostrava comunque «Abilita lettura — Ingresso»: un pulsante che
  non poteva ricevere niente, perché nessun dispositivo era in ascolto.
  Prometteva qualcosa che non era in grado di fare
  - Ora la sezione si chiama **«Aggiungi una tessera»** e dentro si sceglie
    con quale **lettore registrato** leggerla — il lettore è la cosa fisica a
    cui ci si avvicina con la tessera in mano; il varco è un'altra cosa, e con
    un varco non si legge niente
  - Con un lettore solo il pulsante è uno e non ripete il nome. Con più
    lettori ce n'è uno per lettore
  - Senza lettori registrati non compaiono pulsanti: compare il motivo e una
    scorciatoia alla scheda Dispositivi
- **Una lettura da un lettore non registrato non può più censire una tessera**,
  nemmeno a finestra aperta. Chi vuole censire da un lettore nuovo prima lo
  registra: è un gesto separato e consapevole
- **Con più varchi, una lettura da un lettore non associato a nessuno di essi
  viene negata** invece di finire sul primo varco. Attribuirla al primo
  significava far aprire il varco sbagliato, in silenzio; ora il registro
  scrive `lettore_non_associato_a_nessun_varco`. Con un varco solo
  l'associazione resta implicita, perché chiederla sarebbe pedanteria

### Modificato

- Il pulsante «Aggiungi tessera» è uno solo e non più uno per varco: i lettori
  registrati cambiano a runtime mentre le entità si creano all'avvio, quindi
  un'entità per lettore sarebbe rimasta indietro. Non è disponibile finché non
  c'è almeno un lettore registrato

## [0.6.0] - 2026-08-26

### Aggiunto

- **Scheda «Dispositivi»: aggiungere un lettore e censire una tessera sono
  due cose diverse.** Prima erano accoppiate, e la conseguenza era che non si
  poteva registrare un lettore senza anche censire una tessera, né registrarlo
  *prima* di avere tessere
  - **Riconoscimento automatico**: premi il pulsante e passi una tessera —
    **una qualunque** — davanti al lettore da aggiungere. Il modulo prende il
    dispositivo e **scarta la tessera**: non viene censita né valutata, non
    lascia righe nel registro accessi. È un gesto per farsi riconoscere, non
    una credenziale, e di solito si usa la prima tessera che si ha in tasca
  - **Oppure lo scegli da un elenco, con barra di ricerca** su nome, marca e
    modello. L'elenco contiene *tutti* i dispositivi: non esiste un attributo
    che dica «questo ha un lettore NFC», e un filtro indovinato nasconderebbe
    proprio quello giusto. Senza ricerca vedi solo quelli che hanno già letto
    qualcosa, che di norma sono quelli che cerchi
  - Un lettore rimosso da Home Assistant resta in elenco ma **marcato**;
    rimuoverlo stacca i varchi che lo usavano, invece di lasciarli a non
    ricevere mai letture senza spiegare perché
- Solo i lettori **registrati** possono essere associati a un varco, così
  l'elenco nelle Impostazioni resta corto e fatto di scelte esplicite

### Modificato

- **Il censimento di una tessera non tocca più la configurazione dei lettori.**
  Nella 0.5.0 legava il varco al lettore come effetto collaterale: comodo, ma
  cambiava l'impianto durante un gesto che riguardava una tessera. Ora quella
  è una cosa che si fa dalla scheda Dispositivi, di proposito
- Le due modalità di apprendimento si escludono a vicenda: una lettura non può
  essere insieme «censisci questa tessera» e «scarta questa tessera, mi serve
  solo il lettore»

## [0.5.0] - 2026-08-26

### Aggiunto

- **I lettori si riconoscono da soli.** Prima il lettore di un varco si
  indicava incollando a mano un `device_id` — una stringa esadecimale da
  pescare dall'URL della pagina del dispositivo. Ora è un elenco a tendina.
  - Non esiste un modo per chiedere a Home Assistant quali dispositivi abbiano
    un lettore NFC: né l'integrazione né il modello lo dichiarano, e dedurlo
    dal nome sarebbe indovinare. Ma **chi legge è un lettore**: ogni
    `tag_scanned` porta con sé il `device_id` di chi ha letto, e da lì
    l'elenco si popola da solo
  - All'avvio l'elenco non parte vuoto: i tag già esistenti conservano
    `last_scanned_by_device_id`, cioè chi ha letto in passato
  - Un lettore poi rimosso da Home Assistant resta in elenco ma viene marcato,
    così un varco non resta legato a un fantasma senza dirlo
- **Il censimento associa il varco al suo lettore.** Apri il censimento su un
  varco e passi una tessera a un lettore: l'associazione l'hai appena fatta tu
  con un gesto, e il modulo la registra. Si scrive **solo** se il varco non
  aveva già un lettore — una configurazione esistente non si riscrive di
  nascosto
  - Durante il censimento la lettura appartiene al varco su cui è aperto,
    qualunque cosa dica la mappatura: pretendere che il lettore fosse già
    mappato significherebbe chiedere di configurare proprio la cosa che si sta
    per imparare

## [0.4.1] - 2026-08-26

### Modificato

- **«Bambino», «adulto» e «togli» hanno un'icona.** Bambino e adulto sono la
  stessa figura, una più piccola dell'altra: accanto si leggono per confronto,
  senza dover interpretare due disegni diversi
- **Si capisce che bisogna premere qualcosa.** L'avviso sul ruolo mancante
  spiegava bene *perché*, ma stava sotto i pulsanti e non diceva *cosa fare*:
  si leggeva a scelta già fatta, o non si leggeva. Ora l'istruzione — «scegli
  qui sotto se è un bambino o un adulto» — apre il blocco, i pulsanti la
  seguono e sono grandi, perché su quella scheda sono l'unica cosa da fare
- Il messaggio del gruppo senza tessere ha un'icona contactless e dice
  entrambi i modi per riempirlo, non solo il trascinamento

## [0.4.0] - 2026-08-26

### Corretto

- **Tutti i titolari risultavano «adulto», e non era solo un'etichetta
  sbagliata.** Chi non era stato configurato riceveva il ruolo adulto per
  default, cioè i permessi **più ampi** proprio perché nessuno aveva detto chi
  fosse: fail-open su una decisione di sicurezza, e per giunta invisibile,
  perché tutto continuava a funzionare. Ora un titolare senza ruolo non è un
  adulto — è una decisione che manca: le sue tessere non aprono, il registro
  scrive `titolare_senza_ruolo_assegnato`, e il pannello lo segnala sulla
  scheda della persona
  - Il ruolo si assegna dalla scheda della persona, dove si vede a chi lo si
    sta dando. La sezione doppia nelle Impostazioni è stata tolta: erano due
    posti dove sbagliare, e il salvataggio delle impostazioni avrebbe finito
    per azzerare i ruoli scritti dall'altra
- **Il trascinamento partiva da qualunque punto della riga.** Bastava afferrare
  una cella per spostare una tessera mentre si cercava di premere un pulsante.
  Ora la riga diventa trascinabile solo mentre si tiene premuta la maniglia

### Aggiunto

- **Il pannello funziona su telefono e tablet, non solo su desktop.**
  - Il problema vero non era il CSS: **il trascinamento HTML5 non emette
    eventi sotto un dito**, quindi abbinare una tessera a una persona era
    semplicemente impossibile da telefono — cioè proprio dove questa pagina si
    usa, in piedi davanti alla porta. La maniglia è diventata un pulsante che
    apre l'elenco dei titolari; il trascinamento resta una scorciatoia per chi
    ha un mouse
  - Sotto gli 780 px le tabelle non si comprimono, si **impilano**: ogni riga
    diventa una scheda e l'intestazione di colonna torna come etichetta davanti
    al valore. Sette colonne su 375 px sarebbero illeggibili a qualunque corpo
  - Aree toccabili da 44 px, schede di navigazione che scorrono invece di
    andare a capo, campi a piena larghezza
  - Verificato a 375, 768 e 1280 px: nessuno scorrimento orizzontale della
    pagina, nessun pulsante sotto i 40 px sul formato mobile

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
