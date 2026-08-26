# Design v2 — il modulo come policy engine

Revisione dell'architettura dopo la seconda passata di requisiti. Sostituisce
l'impostazione della prima iterazione, in cui il modulo apriva direttamente i
varchi.

---

## 1. Cambio di responsabilità

**Prima:** il modulo valutava la credenziale e chiamava `switch.turn_on` e
`lock.open`.

**Ora:** il modulo valuta, registra, notifica ed emette eventi. **Non apre.**
L'apertura è delegata a script/automazioni configurabili, con hook prima e
dopo.

```
   lettore          MODULO                        attuazione
   ───────          ──────                        ──────────
   legge     →   1. identifica la card
                 2. valuta stato card + sicurezza
                    + person + stato sistema
                 3. decide
                 4. emette evento          →   hook pre
                 5. risponde al lettore    →   script varco
                 6. traccia                →   hook post
```

Conseguenza pratica: cambiare *cosa* succede all'apertura (accendere luci,
disarmare l'antifurto, aprire solo il cancelletto di notte) non richiede più di
toccare il modulo. Si cambia lo script.

---

## 2. Registro card

### Modello

| Campo | Tipo | Note |
|---|---|---|
| `uid` | string | come lo riporta il lettore, maiuscolo con trattini |
| `nome` | string | etichetta leggibile, es. "portachiavi scuola" |
| `person` | entity_id | `person.*` — a chi è abbinata |
| `tecnologia` | enum | `mifare_classic` \| `mifare_ultralight` \| `ntag424` \| `sconosciuta` |
| `sicurezza` | enum derivato | `debole` \| `forte` |
| `stato` | enum | `attiva` \| `disabilitata` \| `blacklist` |
| `creata` | datetime | |
| `ultimo_uso` | datetime | |
| `usi` | int | |

### Ciclo di vita

```
    [lettura ignota] → enrollment → attiva ⇄ disabilitata
                                      │           │
                                      └─→ blacklist ←┘
                                             │
                                          eliminata
```

- **attiva** — valutata normalmente
- **disabilitata** — sospensione temporanea, non allarma
- **blacklist** — card persa o compromessa: se ripassa, **allarme**
- **eliminata** — rimossa dal registro; una lettura successiva è "sconosciuta"

Disabilitata e blacklist sono cose diverse di proposito: una card che ho messo
via in un cassetto non deve generare allarmi, una card che ho perso sì.

### Livello di sicurezza

Il livello **restringe** cosa la card può fare, sopra al ruolo della person e
allo stato del sistema.

| Tecnologia | Sicurezza | Perché |
|---|---|---|
| MIFARE Classic (solo UID) | debole | clonabile in trenta secondi |
| MIFARE Ultralight (solo UID) | debole | idem |
| NTAG424 DNA con cryptogram verificato | forte | AES-128 verificato lato HA |
| Impronta R503 | forte | non clonabile per presentazione |

Autorizzazione = `f(stato_card, sicurezza_card, person, stato_sistema)`.

Una card **debole** apre solo negli stati previsti per il suo titolare e solo
sul varco pedonale. Una card **forte** non ha questa restrizione aggiuntiva.

> ### ⚠️ Il livello di sicurezza oggi non è rilevabile automaticamente
>
> Il PN532 letto via ESPHome espone **solo l'UID**. Non espone SAK/ATQA, che
> sono i byte da cui si classifica la tecnologia (`SAK 0x08` = MIFARE Classic
> 1K, `SAK 0x20` = ISO14443-4, quindi DESFire/NTAG424).
>
> Quindi delle due l'una:
>
> - **ora**: la tecnologia si dichiara a mano in fase di enrollment, e il
>   livello di sicurezza ne deriva. La lunghezza dell'UID (4 vs 7 byte) è un
>   indizio, non una prova, e non va usata come tale.
> - **dopo**: un custom component ESPHome che riporta SAK/ATQA insieme all'UID
>   rende la classificazione automatica e non falsificabile dall'utente.
>
> Il modello dati è già pronto per il secondo caso: cambia solo chi scrive il
> campo `tecnologia`.

---

## 3. Lockout dei lettori dopo N letture fallite

Requisito: dopo N letture sbagliate il lettore va invalidato, come se fosse
manomesso.

### Il compromesso da vedere prima di configurarlo

Il lockout che blocca *tutto* è **banalmente armabile contro il bambino**.
Chiunque passi cinque volte una card qualsiasi davanti al lettore lo blocca, e
il bambino — che per requisito §1 non ha il telefono — resta fuori.

E in cambio si guadagna poco: la minaccia contro cui il lockout difenderebbe è
il brute-force dell'UID, che a 3 letture ogni 10 secondi su uno spazio da 4
miliardi di UID richiede qualche secolo. È già impossibile senza lockout.

Il valore reale del lockout non è bloccare: è **segnalare**. N fallimenti
consecutivi significano che sta succedendo qualcosa, e vale la notifica.

### Come è modellato

Due comportamenti, selezionabili:

| Modalità | Cosa blocca | Default |
|---|---|---|
| `segnala` | nulla; notifica, evento, contatore | ✅ |
| `blocca` | ogni lettura, comprese le card valide | |

In modalità `segnala`, durante il lockout una card **valida della person
giusta nello stato giusto** apre comunque; tutto il resto viene rifiutato e la
famiglia riceve la notifica. Il default è `segnala` perché il requisito §1 —
il bambino deve poter entrare — pesa più di una difesa che non difende da
nulla di realmente raggiungibile.

Chi vuole `blocca` lo imposta, sapendo che serve un fallback fisico
indipendente (key safe o PIN della serratura) o il bambino resta fuori.

### Parametri

- soglia fallimenti consecutivi (default 5)
- durata lockout (default 15 min, sblocco manuale sempre disponibile)
- il contatore si azzera ad ogni accesso riuscito

---

## 4. Il feedback resta indistinguibile

Vale ancora e senza eccezioni: **card sconosciuta, card disabilitata, card in
blacklist, card valida fuori finestra, lettore in lockout → tutti `ko`
identico.**

In particolare la blacklist: l'allarme va alla famiglia, **non** a chi ha la
card in mano. Un feedback diverso per la blacklist direbbe a chi ha trovato o
rubato la card che quella card è nota e segnalata — informazione che gli serve
e a noi no.

---

## 5. Eventi emessi

Il modulo emette `access_event` sul bus di HA. Qualunque automazione può
reagire senza toccare il modulo.

```yaml
event_type: access_event
event_data:
  esito: granted | denied | blacklist | lockout
  motivo: string          # solo per denied/blacklist/lockout
  uid: string
  card_nome: string
  card_stato: attiva | disabilitata | blacklist | sconosciuta
  card_sicurezza: debole | forte | sconosciuta
  person: entity_id | null
  varco: ingresso | garage
  stato_sistema: sleep | finestra_scuola | rientro_adulto | casa_occupata
  timestamp: iso8601
```

---

## 6. Contratto degli hook

Il modulo non apre. Chiama, in ordine:

| Fase | Configurabile | Riceve | Se fallisce |
|---|---|---|---|
| **pre** | script opzionale | tutto `access_event` | l'apertura **non** procede |
| **azione** | script per varco, obbligatorio | idem | esito `ko` al lettore |
| **post** | script opzionale | idem + esito dell'azione | solo log |

Note di progetto:

- Il **pre-hook può vietare** l'apertura (es. "non aprire se la piscina è
  scoperta e il bambino è solo"). È il punto di estensione per regole che non
  vale la pena mettere nel modulo.
- Il modulo **risponde al lettore prima** di chiamare l'azione, non dopo:
  l'utente deve sentire il bip entro il timeout di 3 s, e uno script lento non
  deve tradursi in un pattern "HA non raggiungibile".
- Se non c'è script di azione configurato per un varco, il modulo **nega** e lo
  dice nel log. Non apre "di default".

---

## 7. Tracciamento

Ogni valutazione produce una riga con: timestamp, uid, nome card, person,
varco, stato sistema, esito, motivo, esito dello script di azione.

Requisito: consultabile in una tab. Le righe vanno conservate anche oltre la
finestra del recorder — un registro accessi che si autocancella dopo dieci
giorni non è un registro accessi.

---

## 8. Cosa resta valido della v1

- La macchina a stati (§5 della spec) — invariata, è il cuore
- I sensori "cosa farebbe adesso e perché"
- Il nodo ESPHome e il contratto a due regole (rispondi sempre, feedback
  indistinguibile)
- Il rate limiter su entrambi i lati
- La separazione credenziale / decisione / attuazione

## Cosa decade della v1

- I tre `input_text.access_cred_*` a slot fisso → sostituiti dal registro card
- La chiamata diretta a `switch.turn_on` / `lock.open` dentro l'automazione →
  sostituita dagli hook
