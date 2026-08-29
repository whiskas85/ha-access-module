// Pannello di Controllo Accessi.
//
// Allineata da scripts/bump.py alla versione del manifest: il pannello la
// confronta con quella dell'integration in esecuzione per accorgersi che i
// file sono stati aggiornati ma Home Assistant non è ancora ripartito.
const PANEL_VERSION = "0.24.1";

const TABS = [
  { id: "stato", label: "Stato" },
  { id: "tessere", label: "Tessere" },
  { id: "persone", label: "Persone" },
  { id: "dispositivi", label: "Dispositivi" },
  { id: "varchi", label: "Varchi" },
  { id: "finestre", label: "Finestre" },
  { id: "registro", label: "Registro" },
  { id: "notifiche", label: "Notifiche" },
  { id: "impostazioni", label: "Impostazioni" },
];

const GIORNI_LUNGHI = [
  "Lunedì", "Martedì", "Mercoledì", "Giovedì",
  "Venerdì", "Sabato", "Domenica",
];

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

const ESITO_ETICHETTA = {
  granted: "consentito",
  denied: "negato",
  blacklist: "BLACKLIST",
  alarm: "ALLARME",
  // Un censimento non è un tentativo di accesso: al lettore risponde `ok` e
  // non entra nel conteggio dei rifiuti.
  enrolled: "censita",
};

const STATO_ETICHETTA = {
  chiuso: "Chiuso",
  aperto: "Aperto",
};

// Icone Material Design Icons, inline: il pannello vive in uno shadow root e
// non eredita il set di icone del frontend, quindi i path se li porta dietro.
const ICONE = {
  gruppo:
    "M12 5.5A3.5 3.5 0 1 1 8.5 9 3.5 3.5 0 0 1 12 5.5M5 8a2.5 2.5 0 1 1-2.5 2.5A2.5 2.5 0 0 1 5 8m14 0a2.5 2.5 0 1 1-2.5 2.5A2.5 2.5 0 0 1 19 8M5 13.75c0-1.24 1.79-2.25 4-2.25l.31.01A6.6 6.6 0 0 0 8 15v3H5.5A1.5 1.5 0 0 1 4 16.5v-2.75zm14 0v2.75a1.5 1.5 0 0 1-1.5 1.5H16v-3a6.6 6.6 0 0 0-1.31-3.49l.31-.01c2.21 0 4 1.01 4 2.25M12 12.5c2.67 0 4.5 1.34 4.5 3v2.25A1.25 1.25 0 0 1 15.25 19h-6.5A1.25 1.25 0 0 1 7.5 17.75V15.5c0-1.66 1.83-3 4.5-3",
  menu: "M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z",
  check:
    "M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20m-1 14.5 7-7L16.59 8 11 13.67 7.91 10.59 6.5 12z",
  pause: "M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20m1 14V8h2v8zM9 16V8h2v8z",
  block:
    "M2 12A10 10 0 0 1 12 2c2.4 0 4.6.8 6.3 2.3L4.3 18.3C2.8 16.6 2 14.4 2 12m10 10c-2.4 0-4.6-.8-6.3-2.3L19.7 5.7C21.2 7.4 22 9.6 22 12a10 10 0 0 1-10 10",
  delete:
    "M19 4h-3.5l-1-1h-5l-1 1H5v2h14M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6z",
  cardPlus:
    "M11 8h2v3h3v2h-3v3h-2v-3H8v-2h3zM20 6H4v12h16zm0-2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
  drag: "M7 19v-2h2v2zm4 0v-2h2v2zm4 0v-2h2v2zM7 15v-2h2v2zm4 0v-2h2v2zm4 0v-2h2v2zM7 11V9h2v2zm4 0V9h2v2zm4 0V9h2v2zM7 7V5h2v2zm4 0V5h2v2zm4 0V5h2v2z",
  alert: "M13 14h-2V9h2m0 9h-2v-2h2M1 21h22L12 2z",
  close:
    "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  adulto:
    "M12 4a4 4 0 0 1 4 4 4 4 0 0 1-4 4 4 4 0 0 1-4-4 4 4 0 0 1 4-4m0 10c4.42 0 8 1.79 8 4v2H4v-2c0-2.21 3.58-4 8-4",
  // Stessa figura dell'adulto, più piccola e appoggiata in basso: accanto
  // all'altra si legge come "il più piccolo" senza bisogno di un disegno
  // diverso da interpretare.
  bambino:
    '<g transform="translate(12 15.5) scale(.6) translate(-12 -12)"><path d="M12 4a4 4 0 0 1 4 4 4 4 0 0 1-4 4 4 4 0 0 1-4-4 4 4 0 0 1 4-4m0 10c4.42 0 8 1.79 8 4v2H4v-2c0-2.21 3.58-4 8-4"/></g>',
  // Tessera + onde: la lettura contactless. Le onde sono tratti, non pieni,
  // quindi vanno disegnate con stroke e non con il fill del resto.
  rfid:
    '<rect x="2" y="6" width="11" height="12" rx="2.5"/>'
    + '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">'
    + '<path d="M16.2 8.9a4.4 4.4 0 0 1 0 6.2"/>'
    + '<path d="M19.1 6.4a8.2 8.2 0 0 1 0 11.2"/></g>',
  lettore:
    "M4 3h16a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2m0 2v14h16V5zM6 7h5v5H6zm0 7h12v2H6zm7-7h5v2h-5zm0 3h5v2h-5z",
  cerca:
    "M9.5 3A6.5 6.5 0 0 1 16 9.5c0 1.61-.59 3.09-1.56 4.23l.27.27h.79l5 5-1.5 1.5-5-5v-.79l-.27-.27A6.52 6.52 0 0 1 9.5 16 6.5 6.5 0 0 1 3 9.5 6.5 6.5 0 0 1 9.5 3m0 2C7 5 5 7 5 9.5S7 14 9.5 14 14 12 14 9.5 12 5 9.5 5",
  piu:
    "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6z",
  ricarica:
    "M17.65 6.35A8 8 0 0 0 12 4a8 8 0 0 0-8 8 8 8 0 0 0 8 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18a6 6 0 0 1-6-6 6 6 0 0 1 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4z",
  varco:
    "M12 3 2 8v13h6v-6h8v6h6V8zM4 19V9.2l8-4 8 4V19h-2v-6H6v6z",
  orologio:
    "M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20m0 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16m.5 3v5.25l4.5 2.67-.75 1.23L11 13V7z",
  campana:
    "M21 19v1H3v-1l2-2v-6a7 7 0 0 1 5-6.71V4a2 2 0 1 1 4 0v.29A7 7 0 0 1 19 11v6zM10 21h4a2 2 0 0 1-4 0",
  scudo:
    "M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5zm0 2.18 7 3.11V11c0 4.52-2.98 8.69-7 9.93-4.02-1.24-7-5.41-7-9.93V6.29z",
  togliRuolo:
    "M12 4a4 4 0 0 1 4 4 4 4 0 0 1-4 4 4 4 0 0 1-4-4 4 4 0 0 1 4-4m0 10c1.2 0 2.34.13 3.36.37l-1.7 1.7c-.54-.05-1.1-.07-1.66-.07-3.09 0-6 1.29-6 2v1h5.43l-2 2H4v-2c0-2.66 5.33-4 8-4M22.11 21.46 20.7 22.87 18.5 20.68l-2.2 2.19-1.41-1.41 2.19-2.2-2.19-2.2 1.41-1.41 2.2 2.19 2.2-2.19 1.41 1.41-2.19 2.2z",
};

// Un gruppo aggiunto a mano non ha un'icona sua: prende quella generica
// invece di lasciare un buco dove gli altri hanno un simbolo.
const iconaGruppo = (id) => icona(ICONE[id] ? id : "gruppo");

const icona = (nome, cls = "") => {
  const d = ICONE[nome] || "";
  // Una voce può essere il solo `d` di un path, oppure markup già pronto
  // quando serve un gruppo con una trasformazione.
  const dentro = d.startsWith("<") ? d : `<path d="${d}"/>`;
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${dentro}</svg>`;
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );

const quando = (iso) => {
  if (!iso) return "mai";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// I controlli del frontend di Home Assistant non sono caricati finché
// qualcuno non li usa. `loadCardHelpers` costruisce una card, e costruire una
// card tira dentro `ha-selector` con tutta la sua famiglia — compreso il
// selettore `action`, che è l'editor di azioni delle automazioni.
//
// Sono API private: possono cambiare senza preavviso fra versioni di HA.
// Perciò il caricamento è dietro try/catch e chi lo usa ha un ripiego: senza,
// un aggiornamento di Home Assistant lascerebbe una pagina bianca al posto
// dell'editor, e non si capirebbe perché.
let _componentiHA = null;
let _spuntaHA = false;

// Elenco a tendina delle entita' di un dominio, con il nome leggibile.
//
// Meglio di un campo di testo dove scrivere `camera.ingresso` a memoria: un
// entity_id sbagliato di una lettera non da' nessun errore, semplicemente non
// succede niente — ed e' il modo peggiore in cui una configurazione puo'
// fallire.
function selettoreEntita(hass, attributi, valore, dominio, vuoto) {
  const stati = hass?.states || {};
  const voci = Object.keys(stati)
    .filter((e) => e.startsWith(`${dominio}.`))
    .sort();
  // Un valore configurato che non esiste piu' resta in elenco: toglierlo in
  // silenzio lo cancellerebbe al primo salvataggio, senza che nessuno abbia
  // deciso di cancellarlo.
  if (valore && !voci.includes(valore)) voci.unshift(valore);
  const nome = (e) => {
    const amichevole = stati[e]?.attributes?.friendly_name;
    return amichevole && amichevole !== e ? `${amichevole} · ${e}` : e;
  };
  return `<select ${attributi}>
      <option value="">${vuoto}</option>
      ${voci
        .map(
          (e) =>
            `<option value="${esc(e)}" ${e === valore ? "selected" : ""}>${esc(
              nome(e),
            )}</option>`,
        )
        .join("")}
    </select>`;
}

async function attendiSpunta() {
  // I due componenti arrivano nello stesso pacchetto dell'editor, ma non e'
  // detto: dipende da cosa Home Assistant ha gia' caricato per la pagina da
  // cui si arriva. Si aspettano un attimo e poi si prende quello che c'e'.
  const attesa = Promise.all([
    customElements.whenDefined("ha-checkbox"),
    customElements.whenDefined("ha-switch"),
    customElements.whenDefined("ha-formfield"),
  ]);
  const scadenza = new Promise((ok) => setTimeout(ok, 2000));
  await Promise.race([attesa, scadenza]);
  return (
    !!customElements.get("ha-checkbox") &&
    !!customElements.get("ha-switch") &&
    !!customElements.get("ha-formfield")
  );
}

// Casella di spunta: quella di Home Assistant se c'e', altrimenti quella del
// browser.
//
// Il ripiego non e' pigrizia: questi componenti si caricano da un pannello
// che non e' il nostro, e se un giorno non arrivassero la scheda
// Impostazioni resterebbe piena di caselle invisibili — cioe' inutilizzabile.
// Meglio brutta che assente.
//
// L'etichetta e' HTML e non testo, perche' alcune contengono un'icona:
// `ha-formfield` lo permette con lo slot apposito.
function spunta(attributi, attiva, etichetta) {
  const on = attiva ? "checked" : "";
  if (_spuntaHA) {
    return `<ha-formfield class="check">
              <ha-checkbox ${attributi} ${on}></ha-checkbox>
              <span slot="label">${etichetta}</span>
            </ha-formfield>`;
  }
  return `<label class="check">
            <input type="checkbox" ${attributi} ${on} /> ${etichetta}
          </label>`;
}

// Interruttore, non casella: per «acceso o spento» e' il controllo giusto,
// ed e' quello che si vede ovunque in Home Assistant.
//
// Il ripiego non e' la casella nuda del browser ma una disegnata da noi con
// le variabili del tema: i componenti di Home Assistant li prendiamo in
// prestito da un pannello che non e' il nostro e non e' garantito che ci
// siano. Meglio un interruttore fatto in casa che somiglia al resto, che una
// casella grigia in mezzo a controlli che non lo sono.
function interruttore(attributi, attiva, etichetta, aria = "") {
  const on = attiva ? "checked" : "";

  // Senza etichetta: dove il titolo della scheda dice gia' di cosa si tratta,
  // ripeterlo accanto all'interruttore e' una parola in piu' da leggere che
  // non aggiunge niente. Resta pero' per chi usa un lettore di schermo, che
  // il titolo accanto non ce l'ha.
  if (!etichetta) {
    const descrizione = esc(aria || "Attiva");
    return _spuntaHA
      ? `<ha-switch ${attributi} ${on} aria-label="${descrizione}"></ha-switch>`
      : `<label class="check interruttore" title="${descrizione}">
           <input type="checkbox" ${attributi} ${on} aria-label="${descrizione}" />
           <span class="binario"><span class="pallina"></span></span>
         </label>`;
  }

  if (_spuntaHA) {
    return `<ha-formfield class="check">
              <ha-switch ${attributi} ${on}></ha-switch>
              <span slot="label">${etichetta}</span>
            </ha-formfield>`;
  }
  return `<label class="check interruttore">
            <input type="checkbox" ${attributi} ${on} />
            <span class="binario"><span class="pallina"></span></span>
            <span>${etichetta}</span>
          </label>`;
}

// Vale per tutte le forme: `type` ce l'ha solo quella nativa.
function eSpunta(el) {
  return (
    el.type === "checkbox" ||
    el.localName === "ha-checkbox" ||
    el.localName === "ha-switch"
  );
}

async function caricaComponentiHA() {
  if (_componentiHA !== null) return _componentiHA;
  try {
    if (!customElements.get("ha-selector")) {
      const helpers = await window.loadCardHelpers();
      const card = await helpers.createCardElement({ type: "entities", entities: [] });
      if (card.constructor.getConfigElement) {
        await card.constructor.getConfigElement();
      }
      await customElements.whenDefined("ha-selector");
    }
    _componentiHA = !!customElements.get("ha-selector");
    _spuntaHA = await attendiSpunta();
  } catch (err) {
    console.warn("Controlli di Home Assistant non disponibili", err);
    _componentiHA = false;
  }
  return _componentiHA;
}

class AccessControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "stato";
    this._data = null;
    this._errore = "";
    this._caricato = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._caricato) {
      this._caricato = true;
      this._carica();
      // Si chiedono subito e non solo aprendo l'editor delle azioni: le
      // caselle di spunta di tutte le schede sono le loro, e finche' non
      // sono definite la pagina ripiega su quelle del browser.
      caricaComponentiHA().then((ok) => {
        if (ok) this._render();
      });
    }
    this._ascoltaCensimenti();
    // I selettori gia' montati vanno tenuti aggiornati a mano: sono creati
    // da noi, non li ridisegna nessun ciclo. Senza, restano con l'oggetto
    // `hass` del momento in cui sono nati — comprese le traduzioni che
    // allora non erano ancora arrivate.
    for (const sel of this._selettori || []) sel.hass = hass;
  }

  async _traduzioniEditor() {
    // Le stringhe dell'editor delle azioni stanno nel fascicolo di traduzione
    // del pannello Impostazioni, e Home Assistant lo carica solo quando apre
    // quel pannello. Qui dentro non lo apre nessuno: i componenti si
    // disegnano lo stesso, ma senza testo — il pulsante di aggiunta resta un
    // "+" muto e il menu a tre punti diventa una colonna di icone senza voci.
    //
    // `loadFragmentTranslation` e' il modo previsto per chiederlo: si passa il
    // nome del fascicolo, non le singole chiavi.
    if (this._traduzioniChieste || !this._hass?.loadFragmentTranslation) return;
    this._traduzioniChieste = true;
    try {
      await this._hass.loadFragmentTranslation("config");
    } catch (err) {
      console.warn("Traduzioni dell'editor non caricate", err);
    }
  }

  // ── censimenti ───────────────────────────────────────────────────────

  _ascoltaCensimenti() {
    // Il censimento non finisce su questa pagina: si preme il pulsante qui e
    // si passa la tessera al lettore, che sta fuori. Senza un aggancio agli
    // eventi, l'unico segnale sarebbe la comparsa di una riga nell'elenco al
    // giro di aggiornamento successivo — e per la tessera già censita, che
    // una riga nuova non la produce, nessun segnale affatto.
    if (this._iscrizione || !this._hass?.connection) return;
    this._iscrizione = this._hass.connection.subscribeEvents(
      (ev) => this._censimentoAvvenuto(ev?.data || {}),
      "access_control_enrolled",
    );
    // Ogni cambiamento dello stato salvato — una lettura, un allarme, una
    // tessera spostata, un'impostazione — arriva qui. Senza, la pagina puo'
    // solo richiedere lo stato a intervalli, e mostra per qualche secondo un
    // mondo che non esiste piu'.
    this._iscrizioneStato = this._hass.connection.subscribeEvents(
      () => this._statoCambiato(),
      "access_control_updated",
    );
  }

  _statoCambiato() {
    // Una singola lettura salva lo stato piu' volte di fila: senza smorzare,
    // sarebbero tre o quattro ricariche complete a raffica.
    clearTimeout(this._attesaRicarica);
    this._attesaRicarica = setTimeout(() => {
      if (this._puoRidisegnare()) this._carica();
    }, 250);
  }

  _censimentoAvvenuto(dati) {
    const nome = dati.card_nome || "tessera";
    this._toast(
      dati.nuova
        ? `Tessera censita: ${nome}`
        : `${nome} era già in registro: non è stata aggiunta di nuovo`,
    );
    // La finestra si è chiusa e l'elenco è cambiato: si rilegge subito
    // invece di aspettare il giro di aggiornamento. Non con l'editor delle
    // azioni aperto, però: quello un ridisegno lo azzererebbe.
    if (!this._configDisp) this._carica();
  }

  _toast(messaggio) {
    // `hass-notification` è il canale dei messaggi del frontend di Home
    // Assistant: si usa il suo, cosi' il messaggio compare dove l'utente si
    // aspetta di vederlo e non in un riquadro tutto nostro.
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message: messaggio },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Home Assistant scrive qui la parte di indirizzo dopo il pannello. E'
  // quello che rende utile il tocco su una notifica: `/controllo-accessi/
  // tessere` apre le tessere invece di lasciare a chi legge il compito di
  // ritrovare la pagina da solo.
  set route(r) {
    const sezione = (r?.path || "").replace(/^\/+/, "");
    if (!sezione || sezione === this._tab) return;
    if (!TABS.some((t) => t.id === sezione)) return;
    this._tab = sezione;
    if (this.shadowRoot?.childElementCount) this._render();
  }

  connectedCallback() {
    this._render();
    // Il registro e lo stato cambiano per conto loro — una lettura al varco
    // non passa da questa pagina — quindi la pagina si aggiorna da sola.
    this._timer = setInterval(() => {
      if (this._puoRinfrescare()) this._carica();
    }, 2000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearTimeout(this._attesaRicarica);
    for (const nome of ["_iscrizione", "_iscrizioneStato"]) {
      if (this[nome]) {
        this[nome].then((disiscrivi) => disiscrivi()).catch(() => {});
        this[nome] = null;
      }
    }
  }

  _puoRidisegnare() {
    // Un ridisegno azzera un trascinamento a metà e cancella quello che si
    // sta scrivendo in un campo: finché una delle due cose è in corso, la
    // pagina aspetta.
    if (this._dragging) return false;
    // Con l'editor delle azioni aperto non si ridisegna: un ridisegno
    // ricostruirebbe il componente e perderebbe la sequenza in modifica.
    if (this._configDisp) return false;
    // Una notifica con modifiche non salvate: vale lo stesso motivo.
    if (this._notificheSporche?.size) return false;
    // E qualunque altra modifica non salvata. Una spunta messa e non ancora
    // salvata vive solo nella pagina: un ridisegno la riporterebbe al valore
    // di prima, e chi guarda vedrebbe la propria scelta annullarsi da sola.
    if (this._modificato) return false;
    // Solo i campi, non i pulsanti: un pulsante resta col fuoco dopo che lo
    // si e' premuto, e bastarebbe un clic per bloccare gli aggiornamenti a
    // tempo indeterminato.
    const a = this.shadowRoot.activeElement;
    const campi = ["INPUT", "SELECT", "TEXTAREA", "HA-SWITCH", "HA-CHECKBOX"];
    return !(a && campi.includes(a.tagName));
  }

  _puoRinfrescare() {
    // Durante l'enrollment si rinfresca sempre: serve il conto alla rovescia,
    // e chi sta censendo è al lettore, non con le mani sulla tastiera.
    if (this._data?.enrollment?.attivo) return true;
    if (!this._puoRidisegnare()) return false;
    // Il grosso degli aggiornamenti arriva dagli eventi. Questo giro resta
    // come rete: se il collegamento agli eventi cade, la pagina invecchia di
    // dieci secondi invece di fermarsi per sempre.
    this._tick = (this._tick || 0) + 1;
    return this._tick % 5 === 0;
  }

  async _carica() {
    if (!this._hass) return;
    let prima = this._impronta;
    try {
      this._data = await this._hass.callApi("get", "access_control/state");
      this._errore = "";
    } catch (err) {
      this._errore = err?.message || "Impossibile leggere lo stato";
      prima = null; // un errore va mostrato comunque
    }

    // Si ridisegna solo se lo stato e' davvero cambiato.
    //
    // Il ridisegno ricostruisce la pagina da capo, quindi porta via tutto
    // quello che non e' ancora stato salvato: spunte messe, riquadri aperti,
    // testo scritto a meta'. Farlo a ogni giro di controllo — anche quando
    // non era cambiato niente — voleva dire vedersi disfare il lavoro sotto
    // le mani ogni pochi secondi.
    this._impronta = JSON.stringify(this._data);
    if (this._impronta === prima) return;
    this._render();
  }

  async _comando(payload) {
    // Il comando porta con se' tutto quello che c'era da salvare: da qui in
    // poi la pagina puo' tornare a rinfrescarsi.
    this._modificato = false;
    try {
      this._data = await this._hass.callApi(
        "post",
        "access_control/command",
        payload,
      );
      this._errore = "";
      // Il server puo' rispondere «salvato, pero'…»: una telecamera che non
      // scatta si salva lo stesso, ma va detto subito e non alla prima
      // notifica senza foto.
      this._impronta = JSON.stringify(this._data);
      if (this._data?.avviso) this._toast(this._data.avviso);
    } catch (err) {
      this._errore = err?.body?.message || err?.message || "Comando fallito";
    }
    this._render();
  }

  // ── rendering ────────────────────────────────────────────────────────

  _render() {
    if (!this.shadowRoot) return;
    const d = this._data;

    // Da telefono le schede scorrono in orizzontale, e ogni ridisegno
    // ricostruisce la barra da zero: senza ricordarsi dove fosse, l'elenco
    // tornava all'inizio da solo a ogni giro di aggiornamento e a ogni volta
    // che si premeva una voce — cioe' proprio mentre la si stava guardando.
    const scorrimento = this.shadowRoot.querySelector("nav")?.scrollLeft || 0;

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="wrap">
        <header>
          <div class="titolo">
            <button class="hamburger" data-menu="1"
                    aria-label="Apri il menu di Home Assistant">${icona("menu")}</button>
            <h1>Controllo Accessi</h1>
          </div>
          <nav>
            ${TABS.map(
              (t) =>
                `<button class="tab ${t.id === this._tab ? "on" : ""}" data-tab="${t.id}">${t.label}</button>`,
            ).join("")}
          </nav>
        </header>
        ${this._errore ? `<div class="err">${esc(this._errore)}</div>` : ""}
        ${this._avvisoVersione(d)}
        ${d ? this._corpo(d) : `<div class="vuoto">Caricamento…</div>`}
        <footer>pannello v${PANEL_VERSION}${
          d?.versione && d.versione !== PANEL_VERSION
            ? ` · integration v${esc(d.versione)}`
            : ""
        }</footer>
      </div>`;

    // Un pannello personalizzato disegna la propria barra, e con essa si
    // prende la responsabilita' del pulsante del menu: su schermo stretto la
    // barra laterale e' un cassetto chiuso, e senza questo pulsante da qui
    // dentro non si torna piu' da nessuna parte se non con il tasto indietro.
    // `hass-toggle-menu` e' l'evento che quel cassetto ascolta.
    const nav = this.shadowRoot.querySelector("nav");
    if (nav) nav.scrollLeft = scorrimento;

    this.shadowRoot
      .querySelector("[data-ricorda-aperto]")
      ?.addEventListener("toggle", (ev) => {
        this._spiegaAperta = ev.target.open;
      });

    this.shadowRoot.querySelectorAll("[data-menu]").forEach((el) =>
      el.addEventListener("click", () =>
        this.dispatchEvent(
          new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }),
        ),
      ),
    );

    // Il pulsante Salva compare quando c'e' qualcosa da salvare. Finche'
    // c'e', la pagina smette di ridisegnarsi da sola: un ridisegno
    // riscriverebbe i campi con i valori salvati, buttando via il testo
    // appena scritto — e la notifica di allarme e' l'ultimo posto dove si
    // vuole scoprire che una modifica non era stata presa.
    // Qualunque campo toccato mette la pagina in «sto modificando». Non
    // serve sapere quale: serve sapere che c'e' qualcosa da non buttare via.
    // Una volta sola: il ridisegno sostituisce il contenuto ma non tocca la
    // radice, quindi riagganciarli a ogni giro li accumulerebbe.
    if (!this._ascoltoModifiche) {
      this._ascoltoModifiche = true;
      const segnaModifica = () => {
        this._modificato = true;
      };
      this.shadowRoot.addEventListener("input", segnaModifica);
      this.shadowRoot.addEventListener("change", segnaModifica);
    }

    this.shadowRoot.querySelectorAll("[data-notifica]").forEach((box) => {
      const bottone = box.querySelector("[data-salva-notifica]");
      if (!bottone) return;
      const segna = () => {
        this._notificheSporche = this._notificheSporche || new Set();
        this._notificheSporche.add(box.dataset.notifica);
        bottone.hidden = false;
      };
      box.addEventListener("input", segna);
      box.addEventListener("change", segna);
    });

    this.shadowRoot.querySelectorAll("[data-sottotab]").forEach((el) =>
      el.addEventListener("click", () => {
        const [pagina, id] = el.dataset.sottotab.split("|");
        this._sotto = { ...(this._sotto || {}), [pagina]: id };
        this._modificato = false;
        this._render();
      }),
    );

    this.shadowRoot.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", () => {
        this._tab = el.dataset.tab;
        this._modificato = false;
        this._render();
        // `block: nearest` e non il centro: senza, portare in vista una
        // scheda fuori schermo trascinerebbe anche la pagina in verticale.
        this.shadowRoot
          .querySelector(".tab.on")
          ?.scrollIntoView({ inline: "center", block: "nearest" });
      }),
    );
    this._agganciaAzioni();
    this._montaEditorAzioni();
  }

  // ── disallineamento di versione ──────────────────────────────────────

  _avvisoVersione(d) {
    const server = d?.versione;
    if (!server || server === PANEL_VERSION) return "";

    // Le due direzioni hanno cause e rimedi diversi, e dire quello sbagliato
    // manda a cercare il problema dalla parte opposta.
    const vecchioIlPannello = this._minore(PANEL_VERSION, server);

    return `
      <div class="disallineata">
        ${icona("alert")}
        <div class="disallineata-testo">
          <strong>Questa pagina non è aggiornata</strong>
          ${
            vecchioIlPannello
              ? `<p>Stai vedendo il pannello <b>v${esc(PANEL_VERSION)}</b> mentre
                   l'integration installata è la <b>v${esc(server)}</b>. È una copia
                   rimasta nella cache del browser: le funzioni nuove ci sono, ma
                   questa pagina non le sa disegnare.</p>`
              : `<p>Il pannello è la <b>v${esc(PANEL_VERSION)}</b> ma l'integration in
                   esecuzione è la <b>v${esc(server)}</b>: i file sono stati aggiornati e
                   Home Assistant non è ancora ripartito. <b>Riavvia Home
                   Assistant</b>; ricaricare la pagina non basta.</p>`
          }
        </div>
        ${
          vecchioIlPannello
            ? `<button data-act="ricarica">${icona("ricarica")} Ricarica</button>`
            : ""
        }
      </div>`;
  }

  _minore(a, b) {
    // Confronto per numeri e non per stringhe: "0.10.0" < "0.9.0" solo in
    // ordine alfabetico, e sarebbe il verso sbagliato.
    const pa = String(a).split(".").map(Number);
    const pb = String(b).split(".").map(Number);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const x = pa[i] || 0;
      const y = pb[i] || 0;
      if (x !== y) return x < y;
    }
    return false;
  }

  async _ricarica() {
    // Un semplice location.reload() può rirestituire lo stesso file dalla
    // cache: è proprio quella copia il problema. Si svuota la Cache Storage
    // del frontend e si aggiorna il service worker, poi si ricarica. Le cache
    // svuotate si riempiono da sole al giro dopo.
    try {
      if (window.caches) {
        const chiavi = await caches.keys();
        await Promise.all(chiavi.map((k) => caches.delete(k)));
      }
      if (navigator.serviceWorker) {
        const reg = await navigator.serviceWorker.getRegistrations();
        await Promise.all(reg.map((r) => r.update()));
      }
    } catch (err) {
      // Se la pulizia non riesce si ricarica lo stesso: peggio di così non va.
      console.warn("Pulizia cache non riuscita", err);
    }
    location.reload();
  }

  _corpo(d) {
    if (this._tab === "stato") return this._vistaStato(d);
    if (this._tab === "tessere") return this._vistaTessere(d);
    if (this._tab === "persone") return this._vistaPersone(d);
    if (this._tab === "dispositivi") return this._vistaDispositivi(d);
    if (this._tab === "varchi") return this._vistaVarchi(d);
    if (this._tab === "finestre") return this._vistaFinestre(d);
    if (this._tab === "notifiche") return this._vistaNotifiche(d);
    if (this._tab === "registro") return this._vistaRegistro(d);
    return this._vistaImpostazioni(d);
  }

  // ── stato ────────────────────────────────────────────────────────────

  _vistaStato(d) {
    const st = d.stato;
    const sic = d.sicurezza || {};
    const ultimo = d.log.find((r) => r.esito === "granted");

    // L'allarme viene per primo e occupa spazio: quando c'è, è l'unica cosa
    // che conta, e leggere lo stato delle finestre mentre l'impianto è fermo
    // manderebbe a cercare il problema dalla parte sbagliata.
    const allarme = sic.in_allarme
      ? `<section class="card allarme">
           <div class="titolare">
             ${icona("scudo", "ico-grande")}
             <div class="chi">
               <b>Sistema in allarme</b>
               <span class="sotto">${esc(sic.motivo || "")} · dalle ${quando(sic.dal)}</span>
             </div>
           </div>
           <p class="nota">I lettori sono <b>spenti</b>: non leggono, quindi
             nessuna lettura arriva più. Si riparte solo di qui — o dal
             pulsante nella notifica, che apre un varco senza sbloccare
             l'impianto.</p>
           <button data-act="sblocca">${icona("ricarica")} Sblocca e riaccendi i lettori</button>
         </section>`
      : "";

    const ruoli = st.ruoli_ammessi || [];
    const finestre = st.finestre_attive || [];

    return `
      ${allarme}

      <section class="card">
        <div class="due-stati">
          <div class="stato-box ${st.armato ? "ok" : "off"}">
            <span class="etichetta">Autorizzazione</span>
            <b>${st.sistema === "aperto" ? "Aperto" : "Chiuso"}</b>
            <span class="sotto">${
              ruoli.length ? `ammessi: ${ruoli.map(esc).join(", ")}` : "non entra nessuno"
            }</span>
          </div>
          <div class="stato-box ${sic.in_allarme ? "male" : "ok"}">
            <span class="etichetta">Sicurezza</span>
            <b>${sic.in_allarme ? "Allarme" : "Normale"}</b>
            <span class="sotto">${
              sic.in_allarme
                ? esc(sic.motivo || "")
                : `${sic.fallimenti || 0} errori di fila su ${sic.soglia || 3}`
            }</span>
          </div>
        </div>
        <p class="motivo">${esc(st.motivo || "—")}</p>
        <div class="griglia">
          ${this._kv("Finestre attive", finestre.length ? finestre.join(", ") : "nessuna")}
          ${this._kv("Porta", st.porta)}
          ${this._kv("Ultimo accesso", ultimo ? `${quando(ultimo.timestamp)} — ${esc(ultimo.card_nome)}` : "mai")}
          ${this._kv("Negati oggi", st.negati_oggi)}
          ${this._kv("Tessere censite", d.tessere.length)}
          ${this._kv("Lettori registrati", (d.dispositivi || []).length)}
        </div>
      </section>

      <section class="card">
        <div class="intestazione-card">
          <h2>Ultime letture</h2>
          <button class="mini" data-tab="registro">${icona("orologio")}Registro completo</button>
        </div>
        ${this._ultimeLetture(d.log)}
      </section>

      <details class="card blocco-spiega" data-ricorda-aperto
        ${this._spiegaAperta ? "open" : ""}>
        <summary>Come decide il sistema</summary>
        <ul class="spiega">
          <li>${icona("orologio")}<span><b>Autorizzazione</b> — le finestre
            dicono chi può entrare e quando. Fuori da ogni finestra non entra
            nessuno: una configurazione vuota è una casa chiusa.</span></li>
          <li>${icona("scudo")}<span><b>Sicurezza</b> — dopo
            <b>${sic.soglia || 3}</b> letture rifiutate di fila, o se passa una
            tessera disabilitata o in blacklist, o se un lettore viene
            manomesso, il sistema va in <b>allarme</b>: i lettori si spengono e
            si riparte solo a mano.</span></li>
          <li>${icona("check")}<span>Si apre solo quando <b>entrambe</b>
            dicono sì. Poi è il <b>lettore</b> a decidere cosa fare: il tag
            valida l'accesso, il dispositivo esegue le sue azioni.</span></li>
        </ul>

        <p class="nota">Adesso, nel dettaglio: il master è
          <b>${st.master ? "acceso" : "spento"}</b>,
          ${
            st.presenza
              ? "c'è <b>qualcuno in casa</b>"
              : "<b>non c'è nessuno</b> in casa"
          },
          ${
            st.adulto_vicino
              ? "e un <b>adulto sta arrivando</b>"
              : "e nessun adulto sta arrivando"
          }.
          Le letture rifiutate di fila sono
          <b>${sic.fallimenti || 0}</b> su ${sic.soglia || 3}.</p>
      </details>`;
  }

  // ── ultime letture ───────────────────────────────────────────────────

  _ultimeLetture(log) {
    // Dieci: quante ne servono per capire cosa e' appena successo. Il resto e'
    // il registro, che sta nella sua scheda e non in mezzo allo stato.
    const righe = (log || []).slice(0, 10);
    if (!righe.length) {
      return `<p class="nota">${icona("rfid", "ico-grande")}
        <span>Nessuna lettura ancora. Passa una tessera a un lettore
        registrato e comparirà qui.</span></p>`;
    }

    return `
      <div class="tabella">
        <table>
          <thead><tr>
            <th>Quando</th><th>Esito</th><th>Tessera</th>
            <th>Titolare</th><th>Lettore</th>
          </tr></thead>
          <tbody>${righe
            .map(
              (r) => `
            <tr class="esito-${esc(r.esito)}">
              <td data-etichetta="Quando">${quando(r.timestamp)}</td>
              <td data-etichetta="Esito"><span class="pill e-${esc(r.esito)}">${esc(
                ESITO_ETICHETTA[r.esito] || r.esito,
              )}</span></td>
              <td data-etichetta="Tessera">${esc(r.card_nome || "sconosciuta")}
                <div class="uid">${esc(r.uid || "")}</div></td>
              <td data-etichetta="Titolare">${esc(r.person_nome || r.person || "—")}</td>
              <td data-etichetta="Lettore">${esc(r.varco_nome || r.varco || "—")}</td>
            </tr>`,
            )
            .join("")}</tbody>
        </table>
      </div>`;
  }

  // ── linguette dentro una pagina ──────────────────────────────────────
  //
  // Servono quando una scheda contiene due cose che si guardano in momenti
  // diversi — le tessere e quelle revocate, le persone e i gruppi. Impilarle
  // vorrebbe dire scorrere sempre oltre l'una per arrivare all'altra.

  _sottoAttivo(pagina, predefinito, ammessi) {
    const scelto = (this._sotto || {})[pagina];
    return scelto && (!ammessi || ammessi.includes(scelto))
      ? scelto
      : predefinito;
  }

  _linguette(pagina, voci, attiva) {
    if (voci.length < 2) return "";
    return `<nav class="sotto-nav">
      ${voci
        .map(
          (v) =>
            `<button class="tab ${v.cls || ""} ${
              v.id === attiva ? "on" : ""
            }" data-sottotab="${esc(pagina)}|${esc(v.id)}">${
              v.icona || ""
            } ${esc(v.testo)}${
              v.conteggio === undefined
                ? ""
                : `<span class="conteggio-mini">${v.conteggio}</span>`
            }</button>`,
        )
        .join("")}
    </nav>`;
  }

  _kv(k, v) {
    return `<div class="kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
  }

  // ── tessere ──────────────────────────────────────────────────────────

  _vistaTessere(d) {
    const enr = d.enrollment || {};
    const lettori = d.dispositivi || [];

    // Il censimento aggiunge una TESSERA. Il lettore è solo lo strumento con
    // cui la si legge, quindi si sceglie qui dentro fra quelli registrati —
    // non fra i varchi, che sono un'altra cosa e con cui non si legge niente.
    const boxEnrollment = enr.attivo
      ? `<div class="attesa">
           <div class="pulsa"></div>
           <div class="attesa-testo">
             <strong>Passa la tessera${
               enr.device_nome ? ` al lettore “${esc(enr.device_nome)}”` : " a un lettore registrato"
             }</strong>
             <p class="nota">La tessera viene letta e aggiunta al registro:
               UID e tipo di chip li ricava il modulo. Si chiude fra
               <b>${enr.secondi}s</b>, o alla prima lettura.</p>
           </div>
           <button class="danger" data-act="cancel-enroll">${icona("close")} Annulla</button>
         </div>`
      : lettori.length === 0
        ? `<div class="serve-ruolo">
             <p class="nota">${icona("alert")}
               <span><b>Nessun lettore registrato.</b> Per aggiungere una
               tessera serve qualcosa che la legga: registra prima il lettore
               dalla scheda <b>Dispositivi</b>, poi torna qui.</span></p>
             <button data-vai="dispositivi">${icona("lettore")} Vai a Dispositivi</button>
           </div>`
        : `<div class="enroll-avvio">
             <div class="riga">
               ${lettori
                 .map(
                   (l) => `<button data-enroll="${esc(l.device_id)}"
                             ${l.assente ? "disabled" : ""}>
                             ${icona("cardPlus")} Aggiungi tessera${
                               lettori.length > 1 ? ` — ${esc(l.nome)}` : ""
                             }
                           </button>`,
                 )
                 .join("")}
             </div>
             <p class="nota">
               ${
                 lettori.length > 1
                   ? "Scegli con quale lettore leggerla, poi passa la tessera davanti a <b>quel</b> lettore: una lettura da un altro lettore viene valutata normalmente, non aggiunta."
                   : "Premi e passa la tessera davanti al lettore."
               }
               UID e tipo di chip li ricava il modulo. La tessera nasce
               <b>senza titolare</b>, e finché non gliene assegni uno non apre
               nulla — trascinala su una persona qui sotto.
             </p>
           </div>`;

    // ── gruppi ──────────────────────────────────────────────────────────
    //
    // Le tessere in blacklist escono dal gruppo del titolare e vanno in una
    // vista loro. Non e' un vezzo: sono le uniche che, ripassando, fanno
    // scattare l'allarme, e in mezzo alle tessere buone di una persona quella
    // riga si legge come una qualsiasi. Chi apre questa pagina dopo un
    // allarme deve trovarle tutte insieme, senza cercarle persona per
    // persona.
    //
    // Orfane e blacklist compaiono solo se ce n'e': un riquadro che dice
    // «nessuna» e' rumore permanente per informare di un caso che quasi
    // sempre non esiste.
    const persone = d.persone || [];
    const inBlacklist = d.tessere.filter((c) => c.state === "blacklist");
    const buone = d.tessere.filter((c) => c.state !== "blacklist");
    const orfane = buone.filter((c) => !c.person);
    const gruppi = [this._gruppoOrfane(orfane, persone)];

    for (const p of persone) {
      gruppi.push(
        this._gruppoPersona(
          p,
          buone.filter((c) => c.person === p.entity_id),
          persone,
        ),
      );
    }

    // La blacklist e' una pagina dentro la pagina, e la linguetta per
    // arrivarci esiste solo quando c'e' qualcosa dietro. Una scheda sempre
    // presente che quasi sempre e' vuota insegna a ignorarla, e il giorno che
    // conta e' proprio quello in cui non va ignorata.
    const sotto = inBlacklist.length
      ? this._sottoAttivo("tessere", "tessere", ["tessere", "blacklist"])
      : "tessere";

    const linguette = inBlacklist.length
      ? this._linguette(
          "tessere",
          [
            { id: "tessere", testo: "Tessere", icona: icona("rfid") },
            {
              id: "blacklist",
              testo: "Blacklist",
              icona: icona("block"),
              cls: "avviso",
              conteggio: inBlacklist.length,
            },
          ],
          sotto,
        )
      : "";

    if (sotto === "blacklist") {
      return `${linguette}${this._gruppoBlacklist(inBlacklist, persone)}`;
    }

    return `
      ${linguette}

      <section class="card">
        <h2>Aggiungi una tessera</h2>
        ${boxEnrollment}
      </section>

      ${gruppi.join("")}

      <section class="card">
        <h2>Cosa fanno i tre stati</h2>
        <ul class="spiega">
          <li>${icona("pause")}<span><b>Disabilita</b> — sospensione silenziosa.
            Per una tessera riposta in un cassetto: non apre e non allarma.</span></li>
          <li>${icona("block")}<span><b>Blacklist</b> — non apre e <b>allarma se
            ripassa</b>. È quella giusta per una tessera persa o rubata.</span></li>
          <li>${icona("delete")}<span><b>Elimina</b> — la rende di nuovo
            sconosciuta, e quindi di nuovo silenziosa. Non usarla per una
            tessera persa: perderesti proprio l'allarme che ti serve.</span></li>
        </ul>
        <p class="nota">Il livello di sicurezza non descrive il chip: descrive il
          fatto che il modulo abbia <b>verificato crittograficamente</b> la
          credenziale. Un NTAG424 di cui si legge solo l'UID si clona come una
          MIFARE Classic, quindi finché non arriva il componente che verifica il
          cryptogram <b>forte</b> resta irraggiungibile — ed è corretto così: a
          reggere la sicurezza è la macchina a stati, non la tessera.</p>
      </section>`;
  }

  _gruppoOrfane(tessere, persone) {
    // Niente riquadro se non ce n'e': «nessuna tessera in sospeso» e' una
    // riga che sta li' per sempre a informare di un caso che quasi mai
    // esiste, e sposta piu' in basso quello che si e' venuti a vedere.
    if (!tessere.length) return "";
    return `
      <section class="card gruppo orfane" data-drop="">
        <header class="titolare">
          <div class="avatar avatar-orfano">${icona("alert")}</div>
          <div class="chi">
            <b>Senza titolare</b>
            <span class="sotto">${tessere.length} ${
              tessere.length === 1 ? "tessera non apre" : "tessere non aprono"
            } — assegnale a una persona</span>
          </div>
          <span class="conteggio">${tessere.length}</span>
        </header>
        ${this._tabellaTessere(tessere, persone)}
      </section>`;
  }

  _gruppoBlacklist(tessere, persone) {
    if (!tessere.length) return "";
    return `
      <section class="card gruppo in-blacklist">
        <header class="titolare">
          <div class="avatar avatar-blacklist">${icona("block")}</div>
          <div class="chi">
            <b>In blacklist</b>
            <span class="sotto">${tessere.length} ${
              tessere.length === 1 ? "tessera revocata" : "tessere revocate"
            } — non aprono, e fanno scattare l'allarme se ripassano</span>
          </div>
          <span class="conteggio">${tessere.length}</span>
        </header>
        <p class="nota">Restano nel registro apposta: e' quello che permette di
          riconoscerle. Eliminandole tornerebbero sconosciute qualsiasi, e
          ripassando non succederebbe piu' niente.</p>
        ${this._tabellaTessere(tessere, persone, true)}
      </section>`;
  }

  _avatar(p) {
    return p.foto
      ? `<img class="avatar" src="${esc(p.foto)}" alt="" />`
      : `<div class="avatar avatar-iniziali">${esc(
          p.nome.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase(),
        )}</div>`;
  }

  // ── persone ──────────────────────────────────────────────────────────

  _vistaPersone(d) {
    const persone = d.persone || [];
    const tessere = d.tessere || [];
    const gruppi = d.opzioni.gruppi || [];
    const predefiniti = ["bambino", "adulto"];

    if (!persone.length) {
      return `
        <section class="card">
          <h2>Persone</h2>
          <p class="nota">${icona("alert")}
            <span>Nessuna persona configurata in Home Assistant. Le tessere si
            assegnano a una <code>person.*</code>, quindi finché non ce n'è
            almeno una non possono aprire niente.</span></p>
        </section>`;
    }

    const schede = persone
      .map((p) => {
        const mie = tessere.filter((c) => c.person === p.entity_id);
        const dove =
          p.stato === "home" ? "in casa" : p.stato === "not_home" ? "fuori" : p.stato;

        const bottoni = gruppi
          .map(
            (g) =>
              `<button class="${p.ruolo ? "mini" : "scegli-ruolo"} ${
                p.ruolo === g.id ? "ok" : ""
              }" data-ruolo="${esc(p.entity_id)}|${esc(g.id)}">${iconaGruppo(
                g.id,
              )}${esc(g.nome)}</button>`,
          )
          .join("");

        return `
          <section class="card gruppo ${p.ruolo ? "" : "senza-ruolo"}">
            <header class="titolare">
              ${this._avatar(p)}
              <div class="chi">
                <b>${esc(p.nome)}</b>
                <span class="sotto">
                  ${
                    p.ruolo
                      ? `<span class="tag ruolo-${esc(p.ruolo)}">${esc(
                          p.ruolo_nome || p.ruolo,
                        )}</span>`
                      : `<span class="tag ruolo-mancante">${icona("alert")} ruolo da assegnare</span>`
                  }
                  ${
                    p.locale
                      ? `<span class="tag">creata qui</span>`
                      : `<span class="punto ${p.stato === "home" ? "acceso" : ""}"></span>${esc(dove)}`
                  }
                  · ${mie.length} ${mie.length === 1 ? "tessera" : "tessere"}
                </span>
              </div>
              ${
                p.locale
                  ? `<button class="mini danger" data-togli-persona="${esc(p.entity_id)}"
                       title="Rimuovi questa persona">${icona("delete")}</button>`
                  : ""
              }
              <span class="conteggio">${mie.length}</span>
            </header>
            ${
              p.ruolo
                ? `<div class="ruoli">
                     ${bottoni}
                     <button class="mini" data-ruolo="${esc(p.entity_id)}|"
                       title="Rimuovi il ruolo">${icona("togliRuolo")}togli</button>
                   </div>`
                : `<div class="serve-ruolo">
                     <p class="nota">
                       ${icona("alert")}
                       <span><b>Scegli se è un bambino o un adulto.</b>
                       Finché non ha un ruolo le sue tessere <b>non aprono
                       nulla</b>. Non viene trattata come adulto per comodità:
                       sarebbe darle i permessi più ampi proprio perché nessuno
                       ha detto chi è.</span>
                     </p>
                     <div class="ruoli">${bottoni}</div>
                   </div>`
            }
          </section>`;
      })
      .join("");

    const schedeGruppi = gruppi
      .map((g) => {
        const quante = persone.filter((p) => p.ruolo === g.id).length;
        return `
          <div class="gruppo-riga">
            ${iconaGruppo(g.id)}
            <span class="gruppo-nome">${esc(g.nome)}</span>
            <span class="uid">${quante} ${
              quante === 1 ? "persona" : "persone"
            }</span>
            ${
              predefiniti.includes(g.id)
                ? `<span class="tag">predefinito</span>`
                : `<button class="mini danger" data-togli-gruppo="${esc(g.id)}"
                     title="Togli il gruppo">${icona("delete")}</button>`
            }
          </div>`;
      })
      .join("");

    const sotto = this._sottoAttivo("persone", "persone", [
      "persone",
      "gruppi",
    ]);

    const linguette = this._linguette(
      "persone",
      [
        {
          id: "persone",
          testo: "Persone",
          icona: icona("adulto"),
          conteggio: persone.length,
        },
        {
          id: "gruppi",
          testo: "Gruppi",
          icona: icona("gruppo"),
          conteggio: gruppi.length,
        },
      ],
      sotto,
    );

    if (sotto === "gruppi") {
      return `
      ${linguette}

      <section class="card">
        <h2>Gruppi</h2>
        <p class="nota">Le finestre ammettono <b>gruppi</b>, non persone: è
          quello che permette di dire «la mattina entrano i bambini» senza
          rifare la regola a ogni tessera nuova. Una persona sta in un gruppo
          solo.</p>
        <div class="gruppi-elenco">${schedeGruppi}</div>
        <div class="riga">
          <input id="nuovo-gruppo" placeholder="Nuovo gruppo — es. «Pulizie», «Ospiti»" />
          <button data-act="aggiungi-gruppo">${icona("piu")} Aggiungi gruppo</button>
        </div>
        <p class="nota"><b>Bambino</b> e <b>adulto</b> non si possono togliere:
          il motore li cita per nome — «un adulto in avvicinamento ammette gli
          adulti» è una regola scritta su quel gruppo. Gli altri si tolgono
          quando si vuole: chi ci stava resta <b>senza gruppo</b> e non apre
          più niente finché non gliene dai un altro, e le finestre che lo
          ammettevano lo perdono dall'elenco.</p>
      </section>`;
    }

    return `
      ${linguette}

      <section class="card">
        <h2>Aggiungi una persona</h2>
        <p class="nota">Per chi ha le chiavi ma non l'app: la nonna, chi viene
          a fare le pulizie, un ospite fisso. Non serve che esista in Home
          Assistant — da qui in poi vale come qualunque altro titolare, prende
          un ruolo e le finestre la fanno entrare in base a quello.</p>
        <div class="riga">
          <input id="nuova-persona" placeholder="Nome e cognome" />
          <button data-act="aggiungi-persona">${icona("piu")} Aggiungi</button>
        </div>
        <p class="nota">Quello che non avrà: la <b>presenza</b>. Il sistema non
          può sapere se è in casa, quindi le regole che dipendono da chi c'è
          non la riguardano — le finestre orarie sì.</p>
      </section>

      <section class="card">
        <h2>Chi può entrare, e con che permessi</h2>
        <p class="nota">Il gruppo non è un'etichetta: è quello che le finestre
          orarie leggono per decidere. Una finestra dice <b>quali gruppi</b>
          ammette e quando, quindi una persona senza gruppo non rientra in
          nessuna finestra — e le sue tessere non aprono, per quante ne abbia.</p>
        <p class="nota">Chi ha un telefono da seguire conviene che sia una
          <code>person.*</code> di Home Assistant: solo quelle hanno la
          presenza, e la presenza è ciò che fa funzionare «quando c'è qualcuno
          in casa». Per tutti gli altri basta aggiungerli qui.</p>
      </section>

      ${nessuno}
      ${schede}`;
  }

  _gruppoPersona(p, tessere, persone) {
    const avatar = this._avatar(p);

    const dove =
      p.stato === "home"
        ? "in casa"
        : p.stato === "not_home"
          ? "fuori"
          : p.stato;

    const attive = p.tessere_attive;
    const dettaglio =
      tessere.length === 0
        ? "nessuna tessera"
        : `${tessere.length} ${tessere.length === 1 ? "tessera" : "tessere"}` +
          (attive < tessere.length ? ` · ${attive} attive` : "");

    // Il ruolo qui si LEGGE e basta: sceglierlo è cosa della scheda
    // Persone. Non è pignoleria — un pulsante che cambia i permessi di
    // qualcuno, messo in mezzo all'elenco delle sue tessere, si preme mentre
    // si sta facendo un'altra cosa. Resta il richiamo quando manca, perché
    // quello riguarda le tessere: finché non c'è, non aprono.
    const ruolo = p.ruolo
      ? `<span class="tag ruolo-${esc(p.ruolo)}">${esc(p.ruolo_nome || p.ruolo)}</span>`
      : `<span class="tag ruolo-mancante">${icona("alert")} ruolo da assegnare</span>`;

    const sceltaRuolo = p.ruolo
      ? ""
      : `<div class="serve-ruolo">
           <p class="nota">
             ${icona("alert")}
             <span><b>${esc(p.nome)} non ha un ruolo</b>, quindi queste
             tessere <b>non aprono nulla</b>. Il ruolo si assegna dalla
             scheda Persone.</span>
           </p>
           <div class="ruoli">
             <button data-vai="persone">${icona("adulto")} Vai a Persone</button>
           </div>
         </div>`;

    return `
      <section class="card gruppo ${p.ruolo ? "" : "senza-ruolo"}"
               data-drop="${esc(p.entity_id)}">
        <header class="titolare">
          ${avatar}
          <div class="chi">
            <b>${esc(p.nome)}</b>
            <span class="sotto">
              ${ruolo}
              ${
                p.locale
                  ? `<span class="tag">creata qui</span>`
                  : `<span class="punto ${p.stato === "home" ? "acceso" : ""}"></span>${esc(dove)}`
              }
              · ${esc(dettaglio)}
            </span>
          </div>
          <span class="conteggio">${tessere.length}</span>
        </header>
        ${sceltaRuolo}
        ${
          tessere.length
            ? this._tabellaTessere(tessere, persone)
            : `<p class="nota vuoto-gruppo">${icona("rfid", "ico-grande")}
                 <span>Nessuna tessera. Trascinane una qui con la maniglia,
                 oppure aprine l'elenco dal pulsante ⠿ della tessera.</span></p>`
        }
      </section>`;
  }

  // `conTitolare`: nella vista blacklist le tessere arrivano da persone
  // diverse, quindi il titolare va scritto. Negli altri elenchi lo dice gia'
  // il gruppo che le contiene, e ripeterlo su ogni riga sarebbe rumore.
  _tabellaTessere(tessere, persone, conTitolare = false) {
    const nomeTitolare = (c) =>
      persone.find((p) => p.entity_id === c.person)?.nome || "senza titolare";
    const azioni = (c) => {
      const b = [];
      if (c.state !== "attiva")
        b.push(`<button class="mini ok" data-set="${esc(c.id)}|attiva"
                  title="Attiva">${icona("check")}<span>Attiva</span></button>`);
      if (c.state !== "disabilitata")
        b.push(`<button class="mini" data-set="${esc(c.id)}|disabilitata"
                  title="Sospendi senza allarmi">${icona("pause")}<span>Disabilita</span></button>`);
      if (c.state !== "blacklist")
        b.push(`<button class="mini warn" data-set="${esc(c.id)}|blacklist"
                  title="Revoca e allarma se ripassa">${icona("block")}<span>Blacklist</span></button>`);
      b.push(`<button class="mini danger" data-remove-card="${esc(c.id)}"
                title="Rimuovi dal registro">${icona("delete")}<span>Elimina</span></button>`);
      return b.join("");
    };

    // Il trascinamento HTML5 non esiste su touch: `dragstart` non viene mai
    // emesso da un dito. Senza un secondo percorso, abbinare una tessera a
    // una persona sarebbe impossibile da telefono — cioè proprio dove questa
    // pagina si usa, in piedi davanti alla porta. Quindi la maniglia è un
    // pulsante che apre l'elenco dei titolari, e il trascinamento resta una
    // scorciatoia in più per chi ha un mouse.
    const scelta = (c) => {
      if (this._assegna !== c.id) return "";
      const voci = [
        `<button class="mini" data-assegna="${esc(c.id)}|">Senza titolare</button>`,
        ...persone.map(
          (p) =>
            `<button class="mini ${p.entity_id === c.person ? "ok" : ""}"
               data-assegna="${esc(c.id)}|${esc(p.entity_id)}">${esc(p.nome)}</button>`,
        ),
      ].join("");
      return `
        <tr class="riga-assegna">
          <td colspan="${conTitolare ? 7 : 6}">
            <div class="assegna">
              <span class="nota">Assegna <b>${esc(c.name)}</b> a:</span>
              <div class="azioni">${voci}</div>
              <button class="mini" data-assegna-chiudi="1">${icona("close")}Chiudi</button>
            </div>
          </td>
        </tr>`;
    };

    const righe = tessere
      .map(
        (c) => `
      <tr class="stato-${esc(c.state)}" data-card="${esc(c.id)}">
        <td class="maniglia" data-etichetta="">
          <button class="tocca-maniglia" data-scegli="${esc(c.id)}"
                  title="Assegna a una persona" aria-label="Assegna a una persona">
            ${icona("drag")}
          </button>
        </td>
        <td data-etichetta="Tessera">
          <input class="nome-tessera" data-rename="${esc(c.id)}"
                 value="${esc(c.name)}" placeholder="dai un nome a questa tessera"
                 title="Invio per salvare" />
          <div class="uid">${esc(c.uid)}</div>
        </td>
        ${
          conTitolare
            ? `<td data-etichetta="Titolare">${esc(nomeTitolare(c))}</td>`
            : ""
        }
        <td data-etichetta="Sicurezza">
          <span class="pill ${c.sicurezza === "forte" ? "forte" : "debole"}">${esc(c.sicurezza)}</span>
          <div class="uid">${esc(c.tecnologia_label)}</div>
        </td>
        <td data-etichetta="Stato"><span class="pill s-${esc(c.state)}">${esc(c.state)}</span></td>
        <td data-etichetta="Ultimo uso">${quando(c.last_used)}<div class="uid">${c.uses} usi</div></td>
        <td data-etichetta="Azioni"><div class="azioni">${azioni(c)}</div></td>
      </tr>
      ${scelta(c)}`,
      )
      .join("");

    return `
      <div class="tabella">
        <table>
          <thead><tr>
            <th></th><th>Tessera</th>${conTitolare ? "<th>Titolare</th>" : ""}
            <th>Sicurezza</th>
            <th>Stato</th><th>Ultimo uso</th><th>Azioni</th>
          </tr></thead>
          <tbody>${righe}</tbody>
        </table>
      </div>`;
  }

  // ── dispositivi ──────────────────────────────────────────────────────

  _vistaDispositivi(d) {
    const reg = d.registrazione_dispositivo || {};
    const registrati = d.dispositivi || [];

    // ── riconoscimento automatico ──────────────────────────────────────
    const auto = reg.attiva
      ? `<div class="attesa">
           <div class="pulsa"></div>
           <div class="attesa-testo">
             <strong>In attesa di una lettura da un lettore qualsiasi</strong>
             <p class="nota">Passa una tessera — <b>una qualunque</b> — davanti
               al lettore che vuoi aggiungere. La tessera viene <b>ignorata</b>:
               serve solo a far dire al dispositivo «sono io». Non viene censita
               né valutata. Si chiude fra <b>${reg.secondi}s</b>.</p>
           </div>
           <button class="danger" data-act="stop-learn">${icona("close")} Annulla</button>
         </div>`
      : `<div class="riga">
           <button data-act="start-learn">${icona("lettore")} Riconoscimento automatico</button>
           <p class="nota" style="flex:1 1 320px">
             Premi qui e poi passa una tessera qualsiasi davanti al lettore che
             vuoi aggiungere: il modulo capisce da solo quale dispositivo è.
             <b>La tessera usata non viene censita</b> — è solo un gesto per
             farsi riconoscere.
           </p>
         </div>`;

    // ── elenco registrati ──────────────────────────────────────────────
    const righe = registrati.length
      ? registrati
          .map(
            (x) => `
        <tr class="${x.assente ? "assente" : ""}">
          <td data-etichetta="Lettore">
            <b>${esc(x.nome)}</b>
            <div class="uid">${esc([x.marca, x.modello].filter(Boolean).join(" ") || x.device_id)}</div>
          </td>
          <td data-etichetta="Letture">${x.letture || 0}
            <div class="uid">${x.ultima ? "ultima " + quando(x.ultima) : "mai"}</div></td>
          <td data-etichetta="Varco">${
            x.varchi.length
              ? x.varchi.map((v) => `<span class="pill s-attiva">${esc(v)}</span>`).join(" ")
              : '<span class="uid">non associato</span>'
          }</td>
          <td data-etichetta="Stato">${
            x.assente
              ? `<span class="pill s-blacklist">${icona("alert")} non più in HA</span>`
              : '<span class="pill s-attiva">presente</span>'
          }</td>
          <td data-etichetta="Azioni"><div class="azioni">
            <button class="mini" data-config-disp="${esc(x.device_id)}">
              ${icona("varco")}<span>Configura</span></button>
            <button class="mini danger" data-togli-disp="${esc(x.device_id)}">
              ${icona("delete")}<span>Rimuovi</span></button>
          </div></td>
        </tr>`,
          )
          .join("")
      : `<tr><td colspan="5" class="vuoto">Nessun lettore registrato.</td></tr>`;

    // ── scelta dall'elenco, con ricerca ────────────────────────────────
    const q = (this._cercaDisp || "").toLowerCase().trim();
    const candidati = (d.dispositivi_ha || []).filter((x) => {
      if (x.registrato) return false;
      if (!q) return x.ha_letto; // senza ricerca si mostrano solo i plausibili
      return [x.nome, x.modello, x.marca].join(" ").toLowerCase().includes(q);
    });

    const elenco = candidati.length
      ? candidati
          .slice(0, 60)
          .map(
            (x) => `
        <button class="candidato" data-agg-disp="${esc(x.device_id)}">
          ${icona("piu")}
          <span class="cand-testo">
            <b>${esc(x.nome)}</b>
            <span class="uid">${esc([x.marca, x.modello].filter(Boolean).join(" ") || "—")}</span>
          </span>
          ${x.ha_letto ? `<span class="pill s-attiva">ha letto ${x.letture}×</span>` : ""}
        </button>`,
          )
          .join("")
      : `<p class="nota">${
          q
            ? "Nessun dispositivo trovato con questo testo."
            : "Nessun dispositivo ha ancora letto qualcosa. Scrivi qui sopra per cercarne uno per nome, oppure usa il riconoscimento automatico."
        }</p>`;

    return `
      <section class="card">
        <h2>Aggiungi un lettore</h2>
        ${auto}
      </section>

      <section class="card">
        <h2>…oppure sceglilo dall'elenco</h2>
        <div class="cerca-riga">
          ${icona("cerca")}
          <input id="cerca-disp" placeholder="Cerca un dispositivo per nome, marca o modello…"
                 value="${esc(this._cercaDisp || "")}" />
        </div>
        <p class="nota">Home Assistant non sa dire quali dispositivi abbiano un
          lettore NFC, quindi qui ci sono <b>tutti</b>: un filtro indovinato
          nasconderebbe proprio quello giusto. Senza ricerca vedi solo quelli
          che <b>hanno già letto qualcosa</b>, che di solito sono quelli che
          cerchi.</p>
        <div class="candidati">${elenco}</div>
      </section>

      <section class="card">
        <h2>Lettori registrati</h2>
        <div class="tabella">
          <table>
            <thead><tr>
              <th>Lettore</th><th>Letture</th><th>Varco</th><th>Stato</th><th>Azioni</th>
            </tr></thead>
            <tbody>${righe}</tbody>
          </table>
        </div>
        <p class="nota">Solo i lettori registrati possono essere associati a un
          varco, dalla scheda Impostazioni. Rimuovendone uno, i varchi che lo
          usavano restano senza lettore — e il pannello lo dice, invece di
          lasciarli in silenzio a non ricevere mai letture.</p>
      </section>

      ${this._configLettore(d)}`;
  }

  _configLettore(d) {
    const id = this._configDisp;
    if (!id) return "";
    const l = (d.dispositivi || []).find((x) => x.device_id === id);
    if (!l) return "";

    const varchi = d.varchi || [];

    return `
      <section class="card gruppo" data-config-lettore data-config="${esc(id)}">
        <div class="titolare">
          ${icona("lettore", "ico-grande")}
          <div class="chi">
            <b>${esc(l.nome)}</b>
            <span class="sotto">azioni, risposta acustica e interruttore di lettura</span>
          </div>
          <button class="mini" data-chiudi-config="1">${icona("close")}<span>Chiudi</span></button>
        </div>

        <h2>Cosa fa quando una tessera è valida</h2>
        <p class="nota">Il tag valida l'accesso, <b>il lettore decide
          l'azione</b>. È lo stesso editor delle automazioni: puoi aprire un
          varco, chiamare uno script, accendere una luce, mettere condizioni.
          Nelle azioni hai la variabile <code>accesso</code>, quindi
          <code>{{ accesso.person }}</code> e
          <code>{{ accesso.card_nome }}</code> funzionano.</p>
        ${
          varchi.length
            ? `<div class="riga">
                 <span class="nota" style="margin:0">Scorciatoie:</span>
                 ${varchi
                   .map(
                     (g) =>
                       `<button class="mini" data-aggiungi-apertura="${esc(id)}|${esc(g.id)}">
                          ${icona("varco")}<span>Apri ${esc(g.name)}</span></button>`,
                   )
                   .join("")}
               </div>`
            : `<p class="nota">${icona("alert")} Nessun varco definito: creane
                 uno nella scheda <b>Varchi</b> per poterlo aprire da qui.</p>`
        }
        <div class="editor-azioni" data-editor-azioni="${esc(id)}"
             data-campo="azioni"></div>

        <h2>Cosa fa quando una tessera è rifiutata</h2>
        <p class="nota">Vale per <b>ogni</b> diniego, qualunque ne sia il
          motivo — tessera sconosciuta, disabilitata, fuori orario. Il motivo
          vero ce l'hai in <code>{{ accesso.motivo }}</code>, ma al lettore non
          arriva: da fuori un rifiuto è indistinguibile dall'altro, ed è
          voluto. Lasciala vuota se un diniego deve solo essere tracciato.</p>
        <div class="editor-azioni" data-editor-azioni="${esc(id)}"
             data-campo="azioni_ko"></div>

        <h2>Cosa fa quando scatta l'allarme</h2>
        <p class="nota">Parte quando i dinieghi di fila superano la soglia, o
          per una tessera in blacklist, o per una manomissione — <b>una volta
          sola</b>, nel momento in cui l'allarme si alza. Non a ogni lettura
          successiva: a impianto già bloccato sarebbe una sirena che riparte a
          ogni tessera passata.</p>
        <div class="editor-azioni" data-editor-azioni="${esc(id)}"
             data-campo="azioni_allarme"></div>

        <h2>Risposta al lettore</h2>
        <p class="nota">Va data sempre, anche negando: se il modulo tace, il
          dispositivo emette il pattern «non raggiungibile» e chi è alla porta
          crede che il sistema sia guasto quando era solo fuori orario.</p>
        <div class="riga">
          <label>Servizio di risposta
            <input data-c="reader_service" value="${esc(l.reader_service || "")}"
                   placeholder="esphome.rfid_ingresso_esito_accesso" /></label>
          <label>Interruttore di lettura
            <input data-c="enable_switch" value="${esc(l.enable_switch || "")}"
                   placeholder="switch.rfid_ingresso_lettura_abilitata" /></label>
        </div>
        <p class="nota">L'interruttore è quello che il sistema spegne quando va
          in allarme: senza, in allarme il lettore continuerebbe a leggere e a
          inondare l'API — che è esattamente ciò da cui l'allarme difende.</p>

        <h2>Foto nelle notifiche</h2>
        <p class="nota">Quale telecamera inquadra <b>questo</b> varco. Serve
          alle notifiche che hanno «Allega telecamera» acceso: una casa con due
          porte ha due telecamere, e la foto della porta sbagliata è peggio di
          nessuna foto — fa credere di aver visto.</p>
        <div class="riga">
          <label>Telecamera del varco
            ${selettoreEntita(
              this._hass,
              'data-c="camera"',
              l.camera || "",
              "camera",
              "— usa quella generale delle impostazioni —",
            )}
          </label>
        </div>

        <button class="primario" data-salva-config="${esc(id)}">
          ${icona("check")} Salva configurazione del lettore</button>
      </section>`;
  }

  // ── editor azioni ────────────────────────────────────────────────────

  async _montaEditorAzioni() {
    const contenitori = this.shadowRoot.querySelectorAll("[data-editor-azioni]");
    if (!contenitori.length) return;

    const disponibili = await caricaComponentiHA();
    await this._traduzioniEditor();

    this._selettori = [];
    contenitori.forEach((box) => {
      const deviceId = box.dataset.editorAzioni;
      // Un lettore ha tre sequenze — consentito, negato, allarme — e ognuna
      // ha il suo editor: la chiave le tiene distinte, altrimenti si
      // sovrascriverebbero a vicenda.
      const campo = box.dataset.campo || "azioni";
      const chiave = `${deviceId}|${campo}`;
      const device = (this._data?.dispositivi || []).find(
        (x) => x.device_id === deviceId,
      );
      // Quello che si sta modificando ha la precedenza su quello salvato:
      // un rimontaggio a meta' modifica riporterebbe l'editor indietro.
      const azioni =
        this._azioniInModifica?.[chiave] ?? (device?.[campo] || []);
      box.innerHTML = "";

      if (!disponibili) {
        // Ripiego: si modifica il JSON a mano. Brutto, ma è pur sempre
        // modificabile — meglio di un riquadro vuoto senza spiegazione.
        const nota = document.createElement("p");
        nota.className = "nota";
        nota.textContent =
          "I controlli grafici di Home Assistant non si sono caricati. " +
          "Puoi comunque scrivere le azioni in JSON qui sotto.";
        const area = document.createElement("textarea");
        area.className = "json-azioni";
        area.rows = 8;
        area.value = JSON.stringify(azioni, null, 2);
        area.dataset.jsonAzioni = chiave;
        box.append(nota, area);
        return;
      }

      const sel = document.createElement("ha-selector");
      sel.hass = this._hass;
      // `action` è il selettore che rende l'editor di azioni completo:
      // sequenze, chiamate a servizio, script, condizioni, attese.
      sel.selector = { action: {} };
      sel.value = azioni;
      sel.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._azioniInModifica = this._azioniInModifica || {};
        this._azioniInModifica[chiave] = ev.detail.value;
        // `ha-selector` e' controllato: disegna quello che ha in `value` e
        // si aspetta che sia chi lo ospita a ridarglielo aggiornato. Senza
        // questa riga l'azione appena aggiunta finisce nello stato del
        // pannello ma il riquadro resta vuoto — e ricompare solo dopo il
        // salvataggio, quando il valore torna dal server.
        sel.value = ev.detail.value;
      });
      box.appendChild(sel);
      this._selettori.push(sel);
    });
  }

  _azioniCorrenti(deviceId, campo = "azioni") {
    const chiave = `${deviceId}|${campo}`;
    if (this._azioniInModifica && chiave in this._azioniInModifica) {
      return this._azioniInModifica[chiave];
    }
    const area = this.shadowRoot.querySelector(
      `[data-json-azioni="${chiave}"]`,
    );
    if (area) {
      try {
        return JSON.parse(area.value || "[]");
      } catch {
        throw new Error("Il JSON delle azioni non è valido");
      }
    }
    const device = (this._data?.dispositivi || []).find(
      (x) => x.device_id === deviceId,
    );
    return device?.[campo] || [];
  }

  // ── varchi ───────────────────────────────────────────────────────────

  _vistaVarchi(d) {
    const varchi = d.varchi || [];
    const righe = varchi.length
      ? varchi
          .map(
            (g) => `
        <div class="varco" data-varco="${esc(g.id)}">
          <div class="titolare">
            ${icona("varco", "ico-grande")}
            <div class="chi">
              <input class="nome-tessera" data-v="name" value="${esc(g.name || "")}"
                     placeholder="Nome del varco" />
              <span class="sotto">
                <code>${esc(g.id)}</code>
                ${
                  g.entita_presente
                    ? `<span class="pill s-attiva">${esc(g.entita_stato)}</span>`
                    : g.entity_id
                      ? `<span class="pill s-blacklist">${icona("alert")} entità assente</span>`
                      : `<span class="pill s-disabilitata">nessuna entità</span>`
                }
                ${
                  g.usato_da && g.usato_da.length
                    ? `· lo apre: ${g.usato_da.map(esc).join(", ")}`
                    : "· non usato da nessun lettore"
                }
              </span>
            </div>
            <button class="mini danger" data-togli-varco="${esc(g.id)}">
              ${icona("delete")}<span>Elimina</span></button>
          </div>
          <div class="riga">
            <label>Entità che apre
              <input data-v="entity_id" value="${esc(g.entity_id || "")}"
                     placeholder="lock.portone · switch.cancelletto · cover.garage" /></label>
            <label>Servizio (vuoto = dedotto)
              <input data-v="service" value="${esc(g.service || "")}"
                     placeholder="open · turn_on · open_cover" /></label>
            <label>Rispegni dopo (s, 0 = mai)
              <input type="number" data-v="auto_off_s" min="0"
                     value="${esc(g.auto_off_s || 0)}" /></label>
          </div>
          <button data-salva-varco="${esc(g.id)}">${icona("check")} Salva varco</button>
        </div>`,
          )
          .join("")
      : `<p class="nota vuoto-gruppo">${icona("varco", "ico-grande")}
           <span>Nessun varco. Aggiungine uno: è l'apertura fisica — porta,
           cancelletto, garage — che poi i lettori aprono con le loro azioni.</span></p>`;

    return `
      <section class="card">
        <h2>Varchi</h2>
        <p class="nota">Un varco è un'apertura fisica, definita una volta e
          riusabile da più lettori. Per farlo aprire, un lettore chiama
          l'azione <code>access_control.open_gate</code> — che nell'editor
          delle azioni compare come «Apri un varco».</p>
        <div class="riga">
          <input id="nuovo-varco" placeholder="Nome del nuovo varco (es. Cancelletto)" />
          <button data-act="aggiungi-varco">${icona("piu")} Aggiungi varco</button>
        </div>
      </section>

      <section class="card">${righe}</section>

      <section class="card">
        <h2>Il servizio si deduce</h2>
        <p class="nota">Da <code>lock.</code> si apre con <b>open</b> (o
          <b>unlock</b> se la serratura non espone lo scrocco), da
          <code>switch.</code> con <b>turn_on</b>, da <code>cover.</code> con
          <b>open_cover</b>. Il campo servizio serve solo quando l'ovvio non va
          bene. Il «rispegni dopo» esiste perché un relè di cancello lasciato
          acceso è un cancello che resta aperto.</p>
      </section>`;
  }

  // ── finestre ─────────────────────────────────────────────────────────

  _vistaFinestre(d) {
    const finestre = d.finestre || [];
    const lettori = d.dispositivi || [];

    const righe = finestre.length
      ? finestre
          .map(
            (w) => `
        <div class="varco ${w.attiva ? "attiva-ora" : ""}" data-finestra="${esc(w.id)}">
          <div class="titolare">
            ${icona("orologio", "ico-grande")}
            <div class="chi">
              <input class="nome-tessera" data-w="name" value="${esc(w.name || "")}"
                     placeholder="Nome della finestra" />
              <span class="sotto">
                ${
                  w.attiva
                    ? `<span class="pill s-attiva">attiva adesso</span>`
                    : `<span class="pill s-disabilitata">non attiva</span>`
                }
                ${
                  w.enabled
                    ? ""
                    : `<span class="pill s-blacklist">disabilitata</span>`
                }
              </span>
            </div>
            <button class="mini danger" data-togli-finestra="${esc(w.id)}">
              ${icona("delete")}<span>Elimina</span></button>
          </div>

          <div class="riga">
            <label>Dalle <input type="time" data-w="start" value="${esc(w.start)}" /></label>
            <label>Alle <input type="time" data-w="end" value="${esc(w.end)}" /></label>
            ${spunta('data-w="enabled"', w.enabled, "Abilitata")}
          </div>

          <div>
            <span class="etichetta">Giorni</span>
            <div class="giorni">
              ${GIORNI.map(
                (g, i) =>
                  spunta(
                    `data-giorno-w="${i}"`,
                    (w.days || []).includes(i),
                    g,
                  ),
              ).join("")}
            </div>
          </div>

          <div>
            <span class="etichetta">Chi può entrare</span>
            <div class="ruoli">
              ${(d.opzioni.gruppi || [])
                .map((g) =>
                  spunta(
                    `data-ruolo-w="${esc(g.id)}"`,
                    (w.roles || []).includes(g.id),
                    `${iconaGruppo(g.id)} ${esc(g.nome)}`,
                  ),
                )
                .join("")}
            </div>
          </div>

          <div>
            <span class="etichetta">Su quali lettori (nessuno spuntato = tutti)</span>
            <div class="ruoli">
              ${
                lettori.length
                  ? lettori
                      .map(
                        (l) =>
                          spunta(
                            `data-lettore-w="${esc(l.device_id)}"`,
                            (w.devices || []).includes(l.device_id),
                            esc(l.nome),
                          ),
                      )
                      .join("")
                  : `<span class="nota">Nessun lettore registrato.</span>`
              }
            </div>
          </div>

          <button data-salva-finestra="${esc(w.id)}">${icona("check")} Salva finestra</button>
        </div>`,
          )
          .join("")
      : `<p class="nota vuoto-gruppo">${icona("orologio", "ico-grande")}
           <span><b>Nessuna finestra: non entra nessuno.</b> È il default
           voluto — una configurazione vuota è una casa chiusa, non una casa
           aperta. Aggiungi la prima qui sopra.</span></p>`;

    return `
      <section class="card">
        <h2>Finestre</h2>
        <p class="nota">Ogni finestra dice <b>quando</b> vale, <b>chi</b>
          ammette e, se vuoi, <b>su quali lettori</b>. Fuori da ogni finestra
          attiva non entra nessuno.</p>
        <div class="riga">
          <input id="nuova-finestra" placeholder="Nome (es. Rientro da scuola)" />
          <button data-act="aggiungi-finestra">${icona("piu")} Aggiungi finestra</button>
        </div>
      </section>

      <section class="card">${righe}</section>

      <section class="card">
        <h2>Oltre alle finestre</h2>
        <div class="riga">
          ${spunta(
            'id="set-presence_opens_all"',
            d.impostazioni.presence_opens_all,
            "Quando c'è qualcuno in casa, ammetti tutti",
          )}
          ${spunta(
            'id="set-nearby_opens_adults"',
            d.impostazioni.nearby_opens_adults,
            "Quando un adulto è in avvicinamento, ammetti gli adulti",
          )}
        </div>
        <p class="nota">Si <b>sommano</b> alle finestre, non le scavalcano:
          sono scorciatoie per i casi che valgono sempre.</p>
        <button class="primario" data-act="salva-presenza">${icona("check")} Salva</button>
      </section>`;
  }

  // ── notifiche ────────────────────────────────────────────────────────

  _vistaNotifiche(d) {
    const n = d.notifiche || {};
    const tipi = d.opzioni.tipi_notifica || {};
    const servizi = Object.keys(this._hass?.services?.notify || {})
      .map((k) => `notify.${k}`)
      .sort();

    const selettore = (id, valore, vuoto) => `
      <select ${id}>
        <option value="">${vuoto}</option>
        ${servizi
          .map(
            (sv) =>
              `<option value="${esc(sv)}" ${sv === valore ? "selected" : ""}>${esc(sv)}</option>`,
          )
          .join("")}
      </select>`;

    // La foto si allega solo se una telecamera e' stata scelta — su questo
    // lettore o in generale. Senza, spuntare la casella non produce niente di
    // visibile e il difetto sembra dell'allegato: va detto dove si preme, non
    // solo nel log.
    const conTelecamera =
      !!(d.impostazioni || {}).camera_entity ||
      (d.dispositivi || []).some((l) => l.camera);

    const blocchi = Object.entries(tipi)
      .map(([chiave, etichetta]) => {
        const t = (n.tipi || {})[chiave] || {};
        return `
        <div class="varco" data-notifica="${esc(chiave)}">
          <div class="titolare">
            ${icona("campana", "ico-grande")}
            <div class="chi">
              <b>${esc(etichetta)}</b>
              <span class="sotto"><code>${esc(chiave)}</code></span>
            </div>
            ${interruttore(
              'data-n="attivo"',
              t.attivo,
              "",
              `Attiva la notifica ${etichetta}`,
            )}
          </div>
          <div class="riga">
            <label>Destinatario
              ${selettore('data-n="service"', t.service || "", "— usa quello generale —")}
            </label>
            ${spunta('data-n="alta_priorita"', t.alta_priorita, "Alta priorità")}
            ${spunta('data-n="immagine"', t.immagine, "Allega telecamera")}
          </div>
          ${
            t.immagine && !conTelecamera
              ? `<p class="nota avviso">${icona("alert")}
                   <span><b>Nessuna telecamera scelta</b>, quindi la foto non
                   viene allegata. Si sceglie sul singolo lettore, in
                   <b>Dispositivi → Configura</b>, oppure una per tutti in
                   <b>Impostazioni → Presenza e sensori</b>.
                   <button class="mini" data-vai="dispositivi">Vai ai lettori</button></span></p>`
              : ""
          }
          <label>Titolo
            <input data-n="titolo" value="${esc(t.titolo || "")}" /></label>
          <label>Messaggio
            <textarea data-n="messaggio" rows="2"
              placeholder="Testo della notifica">${esc(t.messaggio || "")}</textarea></label>
          <button data-salva-notifica="${esc(chiave)}"
            ${this._notificheSporche?.has(chiave) ? "" : "hidden"}>${icona(
              "check",
            )} Salva</button>
        </div>`;
      })
      .join("");

    return `
      <section class="card ${n.master ? "" : "spento"}">
        <div class="intestazione-card">
          <h2>Master notifiche</h2>
          ${interruttore(
            'id="notif-master"',
            n.master,
            "",
            "Attiva tutte le notifiche",
          )}
        </div>
        <div class="riga">
          <label>Destinatario generale
            ${selettore('id="notif-service"', n.service || "", "— nessuno —")}
          </label>
          <button data-act="salva-master-notifiche">${icona("check")} Salva</button>
        </div>
        <p class="nota">${
          n.master
            ? "Con il master spento non parte nessuna notifica, qualunque sia l'interruttore del singolo tipo."
            : "<b>Master spento: non parte nessuna notifica</b>, nemmeno quelle di allarme."
        }</p>
      </section>

      <section class="card">
        <h2>Segnaposto disponibili</h2>
        <p class="nota">Nei testi puoi usare
          <code>{tessera}</code> <code>{titolare}</code> <code>{lettore}</code>
          <code>{motivo}</code> <code>{ora}</code> <code>{stato}</code>.
          Un segnaposto scritto male resta com'è invece di far fallire la
          notifica — che nel caso dell'allarme sarebbe il momento peggiore per
          scoprire un refuso.</p>
      </section>

      <section class="card">${blocchi}</section>`;
  }

  // ── registro ─────────────────────────────────────────────────────────

  _vistaRegistro(d) {
    const righe = d.log.length
      ? d.log
          .map(
            (r) => `
        <tr class="esito-${esc(r.esito)}">
          <td data-etichetta="Quando">${quando(r.timestamp)}</td>
          <td data-etichetta="Esito"><span class="pill e-${esc(r.esito)}">${esc(ESITO_ETICHETTA[r.esito] || r.esito)}</span></td>
          <td data-etichetta="Tessera">${esc(r.card_nome || "sconosciuta")}<div class="uid">${esc(r.uid)}</div></td>
          <td data-etichetta="Titolare">${esc(r.person_nome || r.person || "—")}</td>
          <td data-etichetta="Stato">${esc(STATO_ETICHETTA[r.stato_sistema] || r.stato_sistema)}</td>
          <td data-etichetta="Varco">${esc(r.varco_nome || r.varco || "—")}</td>
          <td data-etichetta="Motivo" class="motivo-cella">${esc(r.motivo || "")}</td>
        </tr>`,
          )
          .join("")
      : `<tr><td colspan="7" class="vuoto">Nessun accesso registrato.</td></tr>`;

    return `
      <section class="card">
        <h2>Registro accessi</h2>
        <p class="nota">Conservato dall'integration, non dal recorder: resta
          consultabile anche oltre la finestra di storico di Home Assistant.</p>
        <div class="tabella">
          <table>
            <thead><tr>
              <th>Quando</th><th>Esito</th><th>Tessera</th><th>Titolare</th>
              <th>Stato</th><th>Varco</th><th>Motivo</th>
            </tr></thead>
            <tbody>${righe}</tbody>
          </table>
        </div>
        <button class="danger" data-act="clear-log">Svuota registro</button>
      </section>`;
  }

  // ── impostazioni ─────────────────────────────────────────────────────

  _vistaImpostazioni(d) {
    const st = d.impostazioni;
    const sic = d.sicurezza || {};

    return `
      <section class="card">
        <h2>Comportamento</h2>
        <div class="riga">
          <label>Ritardo ritorno a chiuso (min)
            <input type="number" id="set-sleep_delay_min" min="1"
                   value="${esc(st.sleep_delay_min)}" /></label>
          <label>Porta socchiusa (min)
            <input type="number" id="set-door_ajar_min" min="1"
                   value="${esc(st.door_ajar_min)}" /></label>
          <label>Rate limit — finestra (s)
            <input type="number" id="set-rate_limit_window_s" min="1"
                   value="${esc(st.rate_limit_window_s)}" /></label>
          <label>Rate limit — max letture
            <input type="number" id="set-rate_limit_max" min="1"
                   value="${esc(st.rate_limit_max)}" /></label>
        </div>
      </section>

      <section class="card">
        <h2>Allarme</h2>
        <p class="nota">Dopo <b>${esc(st.alarm_threshold)}</b> letture rifiutate
          di fila il sistema va in allarme: i lettori si <b>spengono</b> e si
          riparte solo a mano. È la difesa contro chi cicla codici con un
          Flipper — ma è anche un modo per lasciare qualcuno fuori, quindi la
          notifica di allarme porta con sé i pulsanti per aprire un varco dal
          telefono senza sbloccare l'impianto.</p>
        <div class="riga">
          <label>Letture errate prima dell'allarme
            <input type="number" id="set-alarm_threshold" min="1"
                   value="${esc(st.alarm_threshold)}" /></label>
        </div>
        <div class="riga">
          ${spunta(
            'id="set-alarm_on_disabled_card"',
            st.alarm_on_disabled_card,
            "Allarme se passa una tessera disabilitata",
          )}
          ${spunta(
            'id="set-alarm_on_blacklist"',
            st.alarm_on_blacklist,
            "Allarme se passa una tessera in blacklist",
          )}
          ${spunta(
            'id="set-alarm_on_tamper"',
            st.alarm_on_tamper,
            "Allarme se un lettore viene manomesso",
          )}
        </div>
        ${
          sic.in_allarme
            ? `<button data-act="sblocca">${icona("ricarica")} Sblocca adesso</button>`
            : ""
        }
      </section>

      <section class="card">
        <h2>Prova una lettura</h2>
        <p class="nota">Percorre tutta la catena — decisione, azioni del
          lettore, registro — <b>senza andare al varco</b>. Serve a verificare
          una configurazione senza doversi alzare e passare una tessera.</p>
        <div class="riga">
          <input id="prova-uid" placeholder="UID della tessera" />
          <select id="prova-varco">
            ${(d.dispositivi || [])
              .map((l) => `<option value="${esc(l.device_id)}">${esc(l.nome)}</option>`)
              .join("")}
          </select>
          <button data-act="scan">${icona("rfid")} Valuta</button>
        </div>
      </section>

      <section class="card">
        <h2>Presenza e sensori</h2>
        <div class="riga">
          <label>Telecamera generale
            ${selettoreEntita(
              this._hass,
              'id="set-camera_entity"',
              st.camera_entity || "",
              "camera",
              "— nessuna —",
            )}
          </label>
          <label>Serratura
            <input id="set-door_lock_entity" value="${esc(st.door_lock_entity || "")}"
                   placeholder="lock.portone" /></label>
          <label>Contatto porta
            <input id="set-door_contact_entity" value="${esc(st.door_contact_entity || "")}"
                   placeholder="binary_sensor.contatto" /></label>
          <label>Zona di avvicinamento
            <input id="set-nearby_zone" value="${esc(st.nearby_zone || "")}"
                   placeholder="zone.vicinanze_di_casa" /></label>
        </div>
        <p class="nota">La serratura e il contatto sono <b>due fonti
          indipendenti</b>: se si contraddicono — anta aperta mentre la
          serratura dichiara chiusa a chiave — è un guasto o un forzamento, e
          diventa lo stato <code>incoerente</code>.</p>
      </section>

      <section class="card">
        <h2>Registro</h2>
        <div class="riga">
          <label>Righe conservate
            <input type="number" id="set-log_max_entries" min="50" max="5000"
                   value="${esc(st.log_max_entries)}" /></label>
        </div>
        <p class="nota">Le righe vivono nell'integration, non nel recorder: un
          registro accessi che si autocancella dopo dieci giorni non è un
          registro accessi.</p>
      </section>

      <button class="primario" data-act="save-settings">
        ${icona("check")} Salva impostazioni</button>`;
  }

  // ── azioni ───────────────────────────────────────────────────────────

  _agganciaAzioni() {
    const r = this.shadowRoot;
    const val = (id) => r.getElementById(id)?.value ?? "";
    const num = (id) => Number(val(id));
    const chk = (id) => r.getElementById(id)?.checked ?? false;

    // ── allarme ────────────────────────────────────────────────────────
    r.querySelector('[data-act="sblocca"]')?.addEventListener("click", () =>
      this._comando({ action: "clear_alarm" }),
    );

    // ── varchi ─────────────────────────────────────────────────────────
    r.querySelector('[data-act="aggiungi-varco"]')?.addEventListener("click", () => {
      const nome = r.getElementById("nuovo-varco")?.value.trim();
      if (!nome) return;
      this._comando({ action: "upsert_gate", gate: { name: nome } });
    });

    r.querySelectorAll("[data-salva-varco]").forEach((el) =>
      el.addEventListener("click", () => {
        const id = el.dataset.salvaVarco;
        const box = r.querySelector(`[data-varco="${id}"]`);
        const gate = { id };
        box.querySelectorAll("[data-v]").forEach((f) => {
          gate[f.dataset.v] =
            f.type === "number" ? Number(f.value) : f.value;
        });
        this._comando({ action: "upsert_gate", gate });
      }),
    );

    r.querySelectorAll("[data-togli-varco]").forEach((el) =>
      el.addEventListener("click", () => {
        if (confirm("Eliminare il varco? I lettori che lo aprivano smetteranno di farlo.")) {
          this._comando({ action: "remove_gate", gate_id: el.dataset.togliVarco });
        }
      }),
    );

    // ── finestre ───────────────────────────────────────────────────────
    r.querySelector('[data-act="aggiungi-finestra"]')?.addEventListener("click", () => {
      const nome = r.getElementById("nuova-finestra")?.value.trim();
      if (!nome) return;
      this._comando({ action: "upsert_window", window: { name: nome } });
    });

    r.querySelectorAll("[data-salva-finestra]").forEach((el) =>
      el.addEventListener("click", () => {
        const id = el.dataset.salvaFinestra;
        const box = r.querySelector(`[data-finestra="${id}"]`);
        const w = { id };
        box.querySelectorAll("[data-w]").forEach((f) => {
          w[f.dataset.w] = eSpunta(f) ? f.checked : f.value;
        });
        w.days = [...box.querySelectorAll("[data-giorno-w]")]
          .filter((c) => c.checked)
          .map((c) => Number(c.dataset.giornoW));
        w.roles = [...box.querySelectorAll("[data-ruolo-w]")]
          .filter((c) => c.checked)
          .map((c) => c.dataset.ruoloW);
        w.devices = [...box.querySelectorAll("[data-lettore-w]")]
          .filter((c) => c.checked)
          .map((c) => c.dataset.lettoreW);
        this._comando({ action: "upsert_window", window: w });
      }),
    );

    r.querySelectorAll("[data-togli-finestra]").forEach((el) =>
      el.addEventListener("click", () => {
        if (confirm("Eliminare la finestra?")) {
          this._comando({
            action: "remove_window",
            window_id: el.dataset.togliFinestra,
          });
        }
      }),
    );

    r.querySelector('[data-act="salva-presenza"]')?.addEventListener("click", () =>
      this._comando({
        action: "set_settings",
        settings: {
          presence_opens_all: r.getElementById("set-presence_opens_all")?.checked,
          nearby_opens_adults: r.getElementById("set-nearby_opens_adults")?.checked,
        },
      }),
    );

    // ── notifiche ──────────────────────────────────────────────────────
    r.querySelector('[data-act="salva-master-notifiche"]')?.addEventListener(
      "click",
      () =>
        this._comando({
          action: "set_notifications",
          changes: {
            master: r.getElementById("notif-master")?.checked,
            service: r.getElementById("notif-service")?.value || "",
          },
        }),
    );

    r.querySelectorAll("[data-salva-notifica]").forEach((el) =>
      el.addEventListener("click", () => {
        const chiave = el.dataset.salvaNotifica;
        const box = r.querySelector(`[data-notifica="${chiave}"]`);
        const conf = {};
        box.querySelectorAll("[data-n]").forEach((f) => {
          conf[f.dataset.n] = eSpunta(f) ? f.checked : f.value;
        });
        this._notificheSporche?.delete(chiave);
        this._comando({
          action: "set_notifications",
          changes: { tipi: { [chiave]: conf } },
        });
      }),
    );

    // ── configurazione del lettore ─────────────────────────────────────
    r.querySelectorAll("[data-config-disp]").forEach((el) =>
      el.addEventListener("click", () => {
        this._configDisp = el.dataset.configDisp;
        this._azioniInModifica = {};
        this._render();
        // Sta sotto l'elenco, quindi aprendola puo' restare fuori schermo:
        // un pulsante che non produce niente di visibile si preme due volte.
        this.shadowRoot
          .querySelector("[data-config-lettore]")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }),
    );

    r.querySelector("[data-chiudi-config]")?.addEventListener("click", () => {
      this._configDisp = null;
      this._azioniInModifica = {};
      this._render();
    });

    r.querySelectorAll("[data-aggiungi-apertura]").forEach((el) =>
      el.addEventListener("click", () => {
        const [deviceId, gateId] = el.dataset.aggiungiApertura.split("|");
        let correnti;
        try {
          correnti = this._azioniCorrenti(deviceId);
        } catch (err) {
          this._errore = err.message;
          this._render();
          return;
        }
        this._azioniInModifica = this._azioniInModifica || {};
        this._azioniInModifica[`${deviceId}|azioni`] = [
          ...(correnti || []),
          { action: "access_control.open_gate", data: { gate: gateId } },
        ];
        // Si salva subito: l'editor si ridisegna col valore nuovo, e non
        // resta uno stato a metà fra quello che si vede e quello che c'è.
        this._comando({
          action: "set_device",
          device_id: deviceId,
          changes: { azioni: this._azioniInModifica[`${deviceId}|azioni`] },
        });
      }),
    );

    r.querySelectorAll("[data-salva-config]").forEach((el) =>
      el.addEventListener("click", () => {
        const id = el.dataset.salvaConfig;
        const box = r.querySelector(`[data-config="${id}"]`);
        let changes;
        try {
          changes = {
            azioni: this._azioniCorrenti(id, "azioni"),
            azioni_ko: this._azioniCorrenti(id, "azioni_ko"),
            azioni_allarme: this._azioniCorrenti(id, "azioni_allarme"),
          };
        } catch (err) {
          this._errore = err.message;
          this._render();
          return;
        }
        box.querySelectorAll("[data-c]").forEach((f) => {
          changes[f.dataset.c] = f.value;
        });
        this._azioniInModifica = {};
        this._comando({ action: "set_device", device_id: id, changes });
      }),
    );

    r.querySelector('[data-act="ricarica"]')?.addEventListener("click", () =>
      this._ricarica(),
    );

    r.querySelector('[data-act="unlock"]')?.addEventListener("click", () =>
      this._comando({ action: "unlock_readers" }),
    );

    r.querySelector('[data-act="clear-log"]')?.addEventListener("click", () => {
      if (confirm("Svuotare il registro accessi? Non è reversibile.")) {
        this._comando({ action: "clear_log" });
      }
    });

    r.querySelector('[data-act="scan"]')?.addEventListener("click", () =>
      this._comando({
        action: "scan",
        uid: val("prova-uid"),
        gate: val("prova-varco"),
      }),
    );

    // Un pulsante per varco: il censimento ascolta un lettore preciso, non
    // "tutti". Con due varchi, "abilita lettura" senza dire quale non sarebbe
    // un'istruzione completa — e aprirebbe una porta che nessuno ha chiesto.
    r.querySelectorAll("[data-vai]").forEach((el) =>
      el.addEventListener("click", () => {
        this._tab = el.dataset.vai;
        this._render();
      }),
    );

    r.querySelectorAll("[data-enroll]").forEach((el) =>
      el.addEventListener("click", () =>
        this._comando({ action: "start_enrollment", device: el.dataset.enroll }),
      ),
    );

    r.querySelector('[data-act="cancel-enroll"]')?.addEventListener("click", () =>
      this._comando({ action: "cancel_enrollment" }),
    );

    // Stato tessera: un pulsante per azione, non una tendina. Con la tendina
    // il cambio parte al primo movimento della rotellina sopra il campo, e su
    // una lista di tessere è un modo silenzioso per mettere in blacklist
    // quella sbagliata.
    r.querySelectorAll("[data-set]").forEach((el) =>
      el.addEventListener("click", () => {
        const [card_id, state] = el.dataset.set.split("|");
        if (
          state === "blacklist" &&
          !confirm(
            "Mettere la tessera in blacklist? Se ripassa genererà un allarme " +
              "ad alta priorità. Per una tessera solo riposta usa Disabilita.",
          )
        ) {
          return;
        }
        this._comando({ action: "set_card_state", card_id, state });
      }),
    );

    // Rinomina inline. Si salva su Invio o uscendo dal campo, e solo se il
    // testo è davvero cambiato: il ridisegno periodico rimetterebbe altrimenti
    // una scrittura al secondo mentre si digita.
    r.querySelectorAll("[data-rename]").forEach((el) => {
      const originale = el.value;
      const salva = () => {
        const nuovo = el.value.trim();
        if (nuovo === originale.trim()) return;
        this._comando({
          action: "update_card",
          card_id: el.dataset.rename,
          changes: { name: nuovo },
        });
      };
      el.addEventListener("blur", salva);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          el.blur();
        } else if (ev.key === "Escape") {
          el.value = originale;
          el.blur();
        }
      });
      // Il trascinamento della riga non deve partire selezionando il testo.
      el.addEventListener("mousedown", (ev) => ev.stopPropagation());
      el.addEventListener("dragstart", (ev) => ev.preventDefault());
    });

    r.querySelector('[data-act="start-learn"]')?.addEventListener("click", () =>
      this._comando({ action: "start_device_learning" }),
    );

    r.querySelector('[data-act="stop-learn"]')?.addEventListener("click", () =>
      this._comando({ action: "cancel_device_learning" }),
    );

    r.querySelectorAll("[data-agg-disp]").forEach((el) =>
      el.addEventListener("click", () =>
        this._comando({ action: "register_device", device_id: el.dataset.aggDisp }),
      ),
    );

    r.querySelectorAll("[data-togli-disp]").forEach((el) =>
      el.addEventListener("click", () => {
        if (confirm("Rimuovere questo lettore? I varchi che lo usano resteranno senza lettore.")) {
          this._comando({
            action: "unregister_device",
            device_id: el.dataset.togliDisp,
          });
        }
      }),
    );

    // La ricerca filtra localmente: l'elenco dei dispositivi e' gia' tutto
    // qui, non serve un giro sul server per ogni lettera.
    const cerca = r.getElementById("cerca-disp");
    cerca?.addEventListener("input", () => {
      this._cercaDisp = cerca.value;
      const pos = cerca.selectionStart;
      this._render();
      const nuovo = this.shadowRoot.getElementById("cerca-disp");
      if (nuovo) {
        nuovo.focus();
        nuovo.setSelectionRange(pos, pos);
      }
    });

    // ── assegnazione a tocchi (l'alternativa al trascinamento) ─────────
    r.querySelectorAll("[data-scegli]").forEach((el) =>
      el.addEventListener("click", () => {
        const id = el.dataset.scegli;
        this._assegna = this._assegna === id ? null : id;
        this._render();
      }),
    );

    r.querySelectorAll("[data-assegna]").forEach((el) =>
      el.addEventListener("click", () => {
        const [card_id, person] = el.dataset.assegna.split("|");
        this._assegna = null;
        this._comando({ action: "assign_person", card_id, person: person || "" });
      }),
    );

    r.querySelector("[data-assegna-chiudi]")?.addEventListener("click", () => {
      this._assegna = null;
      this._render();
    });

    r.querySelector('[data-act="aggiungi-gruppo"]')?.addEventListener(
      "click",
      () => {
        const campo = r.getElementById("nuovo-gruppo");
        const nome = (campo?.value || "").trim();
        if (!nome) {
          this._errore = "Serve un nome per il gruppo.";
          this._render();
          return;
        }
        this._comando({ action: "add_group", nome });
      },
    );

    r.querySelectorAll("[data-togli-gruppo]").forEach((el) =>
      el.addEventListener("click", () => {
        if (
          confirm(
            "Togliere questo gruppo? Chi ci sta dentro resta senza gruppo e " +
              "non aprirà più niente finché non gliene assegni un altro.",
          )
        ) {
          this._comando({
            action: "remove_group",
            group_id: el.dataset.togliGruppo,
          });
        }
      }),
    );

    r.querySelector('[data-act="aggiungi-persona"]')?.addEventListener(
      "click",
      () => {
        const campo = r.getElementById("nuova-persona");
        const nome = (campo?.value || "").trim();
        if (!nome) {
          this._errore = "Serve un nome per aggiungere una persona.";
          this._render();
          return;
        }
        this._comando({ action: "add_person", nome });
      },
    );

    r.querySelectorAll("[data-togli-persona]").forEach((el) =>
      el.addEventListener("click", () => {
        // Le tessere non si toccano: tornano senza titolare, che e' uno stato
        // visibile. Cancellarle sarebbe il modo piu' rapido per perdere il
        // ricordo di una tessera che sta ancora in giro in una tasca.
        if (
          confirm(
            "Rimuovere questa persona? Le sue tessere restano nel registro, " +
              "senza titolare — e finché non gliene assegni uno non aprono nulla.",
          )
        ) {
          this._comando({
            action: "remove_person",
            person_id: el.dataset.togliPersona,
          });
        }
      }),
    );

    r.querySelectorAll("[data-ruolo]").forEach((el) =>
      el.addEventListener("click", () => {
        const [person, role] = el.dataset.ruolo.split("|");
        this._comando({ action: "set_person_role", person, role: role || "" });
      }),
    );

    // ── trascinamento tessera → titolare ──────────────────────────────
    // Il trascinamento parte SOLO dalla maniglia.
    //
    // `draggable` va sulla riga — è la riga che deve muoversi — ma se resta
    // sempre attivo si trascina afferrando qualunque punto, comprese le celle
    // dove si legge e si clicca: si finisce per spostare tessere per sbaglio
    // mentre si cerca di premere un pulsante. Quindi la riga diventa
    // trascinabile solo mentre si tiene premuta la maniglia, e torna ferma
    // appena si lascia.
    r.querySelectorAll("[data-card]").forEach((riga) => {
      riga.draggable = false;
      const maniglia = riga.querySelector(".tocca-maniglia");

      const arma = () => {
        riga.draggable = true;
      };
      const disarma = () => {
        riga.draggable = false;
      };
      maniglia?.addEventListener("pointerdown", arma);
      maniglia?.addEventListener("pointerup", disarma);
      maniglia?.addEventListener("pointercancel", disarma);

      riga.addEventListener("dragstart", (ev) => {
        // Se la riga è trascinabile senza che la maniglia sia premuta,
        // l'origine non è quella prevista: si annulla invece di indovinare.
        if (!riga.draggable) {
          ev.preventDefault();
          return;
        }
        this._dragging = riga.dataset.card;
        riga.classList.add("in-volo");
        ev.dataTransfer.effectAllowed = "move";
        // Firefox non avvia il trascinamento senza payload impostato.
        ev.dataTransfer.setData("text/plain", riga.dataset.card);
      });

      riga.addEventListener("dragend", () => {
        this._dragging = null;
        disarma();
        riga.classList.remove("in-volo");
        r.querySelectorAll("[data-drop]").forEach((t) =>
          t.classList.remove("sopra"),
        );
      });
    });

    r.querySelectorAll("[data-drop]").forEach((target) => {
      target.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        target.classList.add("sopra");
      });
      target.addEventListener("dragleave", () =>
        target.classList.remove("sopra"),
      );
      target.addEventListener("drop", (ev) => {
        ev.preventDefault();
        target.classList.remove("sopra");
        const card_id = this._dragging || ev.dataTransfer.getData("text/plain");
        this._dragging = null;
        if (!card_id) return;
        this._comando({
          action: "assign_person",
          card_id,
          person: target.dataset.drop,
        });
      });
    });

    r.querySelectorAll("[data-remove-card]").forEach((el) =>
      el.addEventListener("click", () => {
        if (
          confirm(
            "Eliminare la tessera? Se è stata persa, la scelta giusta è la blacklist: " +
              "una tessera eliminata torna sconosciuta e non allarma più.",
          )
        ) {
          this._comando({
            action: "remove_card",
            card_id: el.dataset.removeCard,
          });
        }
      }),
    );

    r.querySelectorAll("[data-save-gate]").forEach((el) =>
      el.addEventListener("click", () => {
        const box = r.querySelector(`.varco[data-gate="${el.dataset.saveGate}"]`);
        const gate = { id: el.dataset.saveGate };
        box.querySelectorAll("[data-g]").forEach((f) => {
          gate[f.dataset.g] = eSpunta(f) ? f.checked : f.value;
        });
        this._comando({ action: "upsert_gate", gate });
      }),
    );

    r.querySelector('[data-act="save-settings"]')?.addEventListener("click", () => {
      // Si manda solo quello che questa scheda mostra davvero: i ruoli
      // stanno sulla scheda della persona e le notifiche nella loro, e
      // mandarli da qui li azzererebbe perche' qui i loro campi non ci sono.
      this._comando({
        action: "set_settings",
        settings: {
          sleep_delay_min: num("set-sleep_delay_min"),
          door_ajar_min: num("set-door_ajar_min"),
          rate_limit_window_s: num("set-rate_limit_window_s"),
          rate_limit_max: num("set-rate_limit_max"),
          alarm_threshold: num("set-alarm_threshold"),
          alarm_on_disabled_card: chk("set-alarm_on_disabled_card"),
          alarm_on_blacklist: chk("set-alarm_on_blacklist"),
          alarm_on_tamper: chk("set-alarm_on_tamper"),
          camera_entity: val("set-camera_entity"),
          door_lock_entity: val("set-door_lock_entity"),
          door_contact_entity: val("set-door_contact_entity"),
          nearby_zone: val("set-nearby_zone"),
          log_max_entries: num("set-log_max_entries"),
        },
      });
    });
  }

  _css() {
    return `
      /* Tutta la pagina un gradino piu' grande: e' una pagina di
         amministrazione, si legge stando in piedi col telefono in mano. */
      :host { display:block; background:var(--primary-background-color); color:var(--primary-text-color);
              font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); font-size:16px; }
      * { box-sizing:border-box; }
      .wrap { max-width:1180px; margin:0 auto; padding:18px; }
      /* La barra resta in cima mentre il contenuto scorre sotto: da telefono
         gli elenchi sono lunghi, e per cambiare scheda si tornava su a mano
         ogni volta. Lo sfondo e' obbligatorio — senza, il contenuto si vede
         passare attraverso. */
      header { display:flex; flex-wrap:wrap; align-items:center; gap:14px;
               position:sticky; top:0; z-index:5; padding:10px 0;
               margin-bottom:8px; background:var(--primary-background-color);
               border-bottom:1px solid var(--divider-color); }
      .titolo { display:flex; align-items:center; gap:8px; flex:1; }
      h1 { font-size:1.7rem; margin:0; }
      /* Il pulsante del menu esiste solo dove la barra laterale si chiude: la
         soglia e' la stessa di Home Assistant, cosi' compare esattamente
         quando serve. */
      .hamburger { display:none; background:none; border:none; padding:8px;
                   border-radius:50%; cursor:pointer; color:var(--primary-text-color);
                   flex:0 0 auto; }
      .hamburger .ico { width:26px; height:26px; }
      h2 { font-size:1.2rem; margin:0 0 12px; }
      /* Titolo a sinistra, interruttore all'altro capo: e' il posto in cui lo
         si cerca, ed e' dove Home Assistant mette quello delle sue schede. */
      .intestazione-card { display:flex; align-items:center; justify-content:space-between;
                           gap:12px; margin-bottom:12px; }
      .intestazione-card h2 { margin:0; }
      nav { display:flex; gap:6px; flex-wrap:wrap; }
      .tab { background:none; border:none; padding:10px 18px; border-radius:20px; cursor:pointer;
             color:var(--secondary-text-color); font-size:1rem; }
      .tab.on { background:var(--primary-color); color:var(--text-primary-color, #fff); }
      .nota.avviso { color:var(--error-color,#db4437); }
      /* La spiegazione serve una volta, non a ogni apertura della pagina:
         chiusa resta a disposizione senza occupare lo schermo. */
      .blocco-spiega > summary { cursor:pointer; font-size:1.2rem; font-weight:600;
                                 list-style:none; display:flex; align-items:center; gap:8px; }
      .blocco-spiega > summary::-webkit-details-marker { display:none; }
      .blocco-spiega > summary::before { content:"›"; display:inline-block;
                                         transition:transform .15s; font-size:1.3rem;
                                         color:var(--secondary-text-color); }
      .blocco-spiega[open] > summary::before { transform:rotate(90deg); }
      .blocco-spiega > summary + * { margin-top:14px; }
      .gruppi-elenco { display:flex; flex-direction:column; gap:8px; margin-bottom:14px; }
      .gruppo-riga { display:flex; align-items:center; gap:10px; padding:10px 12px;
                     border:1px solid var(--divider-color); border-radius:8px; }
      .gruppo-nome { font-weight:600; flex:1; }
      .sotto-nav { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
      .sotto-nav .tab { display:inline-flex; align-items:center; gap:7px; padding:8px 16px;
                        font-size:.95rem; border:1px solid var(--divider-color); }
      .sotto-nav .tab.avviso { color:var(--error-color,#db4437);
                               border-color:rgba(219,68,55,.5); }
      .sotto-nav .tab.avviso.on { background:var(--error-color,#db4437); color:#fff; }
      .conteggio-mini { background:rgba(0,0,0,.14); border-radius:10px;
                        padding:1px 8px; font-size:.85rem; }
      .card { background:var(--card-background-color); border-radius:12px; padding:18px; margin-bottom:16px;
              box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
      .card.allarme { border-left:4px solid var(--error-color, #db4437); }
      .big { font-size:1.35rem; font-weight:600; }
      .big.ok { color:var(--success-color, #43a047); }
      .big.off { color:var(--secondary-text-color); }
      .motivo { margin:8px 0 16px; color:var(--secondary-text-color); font-size:1rem; }
      .griglia { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; }
      .kv { display:flex; flex-direction:column; gap:3px; }
      .kv span { font-size:.8rem; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.5px; }
      .kv b { font-size:1.05rem; }
      .riga { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }
      label { display:flex; flex-direction:column; gap:5px; font-size:.9rem;
              color:var(--secondary-text-color); flex:1 1 190px; }
      label.check { flex-direction:row; align-items:center; gap:8px; flex:0 0 auto; font-size:.95rem; }
      ha-formfield.check { flex:0 0 auto; --mdc-typography-body2-font-size:.95rem; }
      ha-formfield.check span[slot="label"] { display:inline-flex; align-items:center; gap:6px; }
      input, select, textarea { padding:10px; border-radius:7px; border:1px solid var(--divider-color);
                      background:var(--card-background-color); color:var(--primary-text-color); font-size:1rem;
                      font-family:inherit; }
      /* Cresce col testo invece di scorrere dentro una riga sola: i messaggi
         hanno segnaposto e vanno riletti tutti interi prima di salvarli. */
      textarea { resize:vertical; min-height:64px; line-height:1.45; }

      /* Interruttore di ripiego, per quando i componenti di Home Assistant
         non sono disponibili. Usa le variabili del tema, cosi' segue chiaro e
         scuro come tutto il resto. */
      .interruttore { cursor:pointer; }
      .interruttore input { position:absolute; opacity:0; width:0; height:0; }
      .interruttore .binario { width:38px; height:22px; border-radius:11px; flex:0 0 auto;
                               background:var(--divider-color); position:relative;
                               transition:background .18s; }
      .interruttore .pallina { position:absolute; top:3px; left:3px; width:16px; height:16px;
                               border-radius:50%; background:var(--card-background-color);
                               box-shadow:0 1px 3px rgba(0,0,0,.35); transition:transform .18s; }
      .interruttore input:checked + .binario { background:var(--primary-color); }
      .interruttore input:checked + .binario .pallina { transform:translateX(16px); }
      .interruttore input:focus-visible + .binario { outline:2px solid var(--primary-color);
                                                     outline-offset:2px; }
      button { display:inline-flex; align-items:center; gap:7px; padding:10px 16px; border-radius:7px;
               border:none; cursor:pointer; background:var(--primary-color);
               color:var(--text-primary-color,#fff); font-size:.95rem; font-family:inherit; }
      button.danger { background:var(--error-color, #db4437); color:#fff; }
      button.primario { width:100%; padding:14px; font-size:1.05rem; justify-content:center; }
      .ico { width:18px; height:18px; fill:currentColor; flex:0 0 auto; }

      /* ── tabelle ──────────────────────────────────────────────────────
         Le azioni stanno in un div dentro la cella, non nella cella stessa:
         un display:flex sul <td> lo toglie dal layout della tabella e il
         bordo inferiore della riga si interrompe proprio sotto l'ultima
         colonna. */
      table { width:100%; border-collapse:collapse; font-size:.95rem; }
      th { text-align:left; padding:10px 8px; border-bottom:2px solid var(--divider-color);
           font-size:.78rem; text-transform:uppercase; letter-spacing:.4px; color:var(--secondary-text-color); }
      td { padding:10px 8px; border-bottom:1px solid var(--divider-color); vertical-align:middle; }
      tbody tr:last-child td { border-bottom:none; }
      .azioni { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
      .uid { font-size:.8rem; color:var(--secondary-text-color); font-family:ui-monospace, monospace; margin-top:2px; }

      .mini { padding:6px 11px; font-size:.82rem; background:var(--divider-color);
              color:var(--primary-text-color); }
      .mini .ico { width:16px; height:16px; }
      .mini.ok { background:rgba(67,160,71,.22); }
      .mini.warn { background:rgba(255,167,38,.28); }
      .mini.danger { background:rgba(219,68,55,.22); color:var(--primary-text-color); }
      .mini:hover { filter:brightness(1.12); }

      .pill { display:inline-block; padding:3px 10px; border-radius:11px; font-size:.8rem; font-weight:600; }
      .pill.debole { background:rgba(255,167,38,.2); color:#e08600; }
      .pill.forte { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.s-attiva { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.s-disabilitata { background:rgba(158,158,158,.25); color:var(--secondary-text-color); }
      .pill.s-blacklist { background:rgba(219,68,55,.2); color:#c62828; }
      .pill.e-granted { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.e-denied { background:rgba(158,158,158,.25); color:var(--secondary-text-color); }
      .pill.e-enrolled { background:rgba(33,150,243,.2); color:#1565c0; }
      .pill.e-blacklist, .pill.e-alarm { background:rgba(219,68,55,.2); color:#c62828; }
      tr.stato-blacklist { background:rgba(219,68,55,.07); }
      tr.stato-disabilitata { opacity:.68; }
      .motivo-cella { font-size:.85rem; color:var(--secondary-text-color); }
      .nota { font-size:.9rem; color:var(--secondary-text-color); margin:0 0 12px; line-height:1.55; }
      .vuoto { text-align:center; padding:26px; color:var(--secondary-text-color); }
      .err { background:var(--error-color,#db4437); color:#fff; padding:12px 16px; border-radius:8px; margin-bottom:14px; }
      .giorni { display:flex; flex-wrap:wrap; gap:14px; margin-top:12px; }
      .varco { border:1px solid var(--divider-color); border-radius:8px; padding:14px; margin-bottom:12px;
               display:flex; flex-direction:column; gap:10px; }
      /* flex:1 sulle etichette serve dentro .riga, che e' una fila. Qui la
         direzione e' la colonna, e la stessa regola le faceva crescere in
         ALTEZZA: da cui il vuoto fra un campo e il successivo. */
      .varco > label { flex:0 0 auto; }
      footer { text-align:center; font-size:.78rem; color:var(--secondary-text-color); padding:14px; }

      /* ── nome tessera modificabile sul posto ─────────────────────────── */
      .nome-tessera { font-weight:600; font-size:1rem; padding:5px 8px; width:100%; max-width:260px;
                      background:transparent; border:1px solid transparent; border-radius:6px; }
      .nome-tessera:hover { border-color:var(--divider-color); }
      .nome-tessera:focus { border-color:var(--primary-color); background:var(--card-background-color);
                            outline:none; }

      /* ── censimento ──────────────────────────────────────────────────── */
      .enroll-avvio .riga { margin-bottom:12px; align-items:flex-start; }
      .scelta-varco { display:flex; flex-direction:column; gap:5px; }
      .avviso { display:inline-flex; align-items:center; gap:5px; color:#e08600; }
      .avviso .ico { width:15px; height:15px; }
      .attesa { display:flex; align-items:center; gap:16px; flex-wrap:wrap;
                border:2px dashed var(--primary-color); border-radius:10px; padding:16px; }
      .attesa-testo { flex:1 1 260px; }
      .attesa-testo strong { font-size:1.05rem; }
      .attesa .nota { margin:6px 0 0; }
      .pulsa { width:18px; height:18px; border-radius:50%; background:var(--primary-color);
               animation:pulsa 1.2s ease-in-out infinite; flex:0 0 auto; }
      @keyframes pulsa { 0%,100% { opacity:1; transform:scale(1); }
                         50% { opacity:.35; transform:scale(1.5); } }
      /* Chi non tollera le animazioni riceve comunque il conto alla rovescia. */
      @media (prefers-reduced-motion: reduce) { .pulsa { animation:none; } }

      /* ── gruppi per titolare, che sono anche i bersagli del drop ─────── */
      .gruppo { border:2px solid transparent; transition:border-color .15s, background .15s; }
      .gruppo.sopra { border-color:var(--primary-color);
                      background:color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color)); }
      .gruppo.orfane { border-color:rgba(255,167,38,.55); }
      .gruppo.spento { opacity:.6; }
      .titolare { display:flex; align-items:center; gap:14px; margin-bottom:12px; }
      .avatar { width:46px; height:46px; border-radius:50%; object-fit:cover; flex:0 0 auto;
                background:var(--divider-color); display:flex; align-items:center; justify-content:center; }
      .avatar-iniziali { font-weight:700; font-size:1rem; color:var(--primary-text-color);
                         background:color-mix(in srgb, var(--primary-color) 25%, transparent); }
      .avatar-orfano { background:rgba(255,167,38,.22); color:#e08600; }
      .avatar-orfano .ico { width:24px; height:24px; }
      .gruppo.in-blacklist { border-color:var(--error-color,#db4437); }
      .avatar-blacklist { background:rgba(219,68,55,.18); color:var(--error-color,#db4437); }
      .avatar-blacklist .ico { width:24px; height:24px; }
      .chi { flex:1; display:flex; flex-direction:column; gap:3px; min-width:0; }
      .chi b { font-size:1.1rem; }
      .sotto { font-size:.88rem; color:var(--secondary-text-color);
               display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
      .tag { padding:2px 9px; border-radius:10px; font-size:.75rem; font-weight:600;
             background:var(--divider-color); }
      .tag.ruolo-bambino { background:rgba(156,39,176,.2); color:#7b1fa2; }
      .tag.ruolo-adulto { background:rgba(33,150,243,.2); color:#1565c0; }
      .punto { width:9px; height:9px; border-radius:50%; background:var(--secondary-text-color);
               opacity:.45; display:inline-block; }
      .punto.acceso { background:var(--success-color,#43a047); opacity:1; }
      .conteggio { font-size:1.5rem; font-weight:700; color:var(--secondary-text-color); flex:0 0 auto; }
      .vuoto-gruppo { margin:0; font-style:italic; }

      tr.in-volo { opacity:.4; }
      .maniglia { color:var(--secondary-text-color); cursor:grab; user-select:none; width:28px; }

      /* ── assegnazione a tocchi ───────────────────────────────────────── */
      .tocca-maniglia { background:none; border:none; padding:8px; margin:-8px;
                        color:var(--secondary-text-color); cursor:grab;
                        min-width:44px; min-height:44px; justify-content:center; }
      .riga-assegna td { background:color-mix(in srgb, var(--primary-color) 8%, transparent); }
      .assegna { display:flex; flex-wrap:wrap; align-items:center; gap:10px; }
      .assegna .nota { margin:0; }

      /* ── ruolo del titolare ──────────────────────────────────────────── */
      .ruoli { display:flex; gap:7px; flex-wrap:wrap; margin-bottom:10px; }
      .tag.ruolo-mancante { background:rgba(255,167,38,.25); color:#e08600;
                            display:inline-flex; align-items:center; gap:5px; }
      .tag.ruolo-mancante .ico { width:14px; height:14px; }
      .gruppo.senza-ruolo { border-color:rgba(255,167,38,.5); }

      /* Ruolo mancante: l'istruzione e i pulsanti sono un blocco solo, così
         non si legge il perché senza vedere cosa premere. */
      .serve-ruolo { background:rgba(255,167,38,.12); border-radius:8px;
                     padding:12px 14px; margin-bottom:12px; }
      .serve-ruolo .nota { display:flex; gap:9px; align-items:flex-start; margin:0 0 11px; }
      .serve-ruolo .nota > .ico { flex:0 0 auto; color:#e08600; margin-top:2px; }
      .scegli-ruolo { background:var(--primary-color); color:var(--text-primary-color,#fff);
                      padding:11px 20px; font-size:1rem; text-transform:capitalize; }
      .scegli-ruolo.ok { outline:2px solid var(--primary-text-color); }
      .scegli-ruolo .ico { width:21px; height:21px; }
      .vuoto-gruppo { display:flex; align-items:center; gap:12px; }
      .ico-grande { width:30px; height:30px; flex:0 0 auto; opacity:.55; }

      /* ── disallineamento di versione ─────────────────────────────────── */
      .disallineata { display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap;
                      background:rgba(255,167,38,.15); border:1px solid rgba(255,167,38,.5);
                      border-radius:10px; padding:14px 16px; margin-bottom:16px; }
      .disallineata > .ico { flex:0 0 auto; color:#e08600; margin-top:3px; width:22px; height:22px; }
      .disallineata-testo { flex:1 1 260px; }
      .disallineata-testo strong { font-size:1.05rem; }
      .disallineata-testo p { margin:6px 0 0; font-size:.9rem; line-height:1.55;
                              color:var(--secondary-text-color); }
      .disallineata button { flex:0 0 auto; }

      /* ── scheda dispositivi ──────────────────────────────────────────── */
      .cerca-riga { display:flex; align-items:center; gap:10px; margin-bottom:12px;
                    border:1px solid var(--divider-color); border-radius:8px; padding:0 12px; }
      .cerca-riga .ico { color:var(--secondary-text-color); }
      .cerca-riga input { flex:1; border:none; background:none; padding:12px 0; }
      .cerca-riga input:focus { outline:none; }
      .cerca-riga:focus-within { border-color:var(--primary-color); }
      .candidati { display:flex; flex-direction:column; gap:8px; max-height:420px;
                   overflow-y:auto; }
      .candidato { display:flex; align-items:center; gap:12px; width:100%; text-align:left;
                   background:none; border:1px solid var(--divider-color);
                   color:var(--primary-text-color); padding:11px 13px; }
      .candidato:hover { border-color:var(--primary-color);
                         background:color-mix(in srgb, var(--primary-color) 8%, transparent); }
      .candidato .ico { color:var(--primary-color); }
      .cand-testo { flex:1; display:flex; flex-direction:column; gap:2px; min-width:0; }
      .cand-testo b { font-size:.98rem; }
      tr.assente { opacity:.7; }
      tr.assente .pill .ico { width:13px; height:13px; vertical-align:-2px; }

      /* ── due macchine a stati, affiancate ────────────────────────────── */
      .due-stati { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                   gap:12px; margin-bottom:14px; }
      .stato-box { border-radius:10px; padding:14px 16px; display:flex;
                   flex-direction:column; gap:3px; border:2px solid var(--divider-color); }
      .stato-box b { font-size:1.3rem; }
      .stato-box.ok { border-color:rgba(67,160,71,.55);
                      background:rgba(67,160,71,.08); }
      .stato-box.off { border-color:var(--divider-color); opacity:.85; }
      .stato-box.male { border-color:rgba(219,68,55,.6);
                        background:rgba(219,68,55,.1); }
      .etichetta { font-size:.75rem; text-transform:uppercase; letter-spacing:.5px;
                   color:var(--secondary-text-color); }

      /* ── editor azioni ───────────────────────────────────────────────── */
      .editor-azioni { margin:10px 0 18px; }
      .json-azioni { width:100%; font-family:ui-monospace, monospace; font-size:.9rem;
                     padding:10px; border-radius:8px; border:1px solid var(--divider-color);
                     background:var(--card-background-color); color:var(--primary-text-color); }
      .varco.attiva-ora { border-color:rgba(67,160,71,.6);
                          background:rgba(67,160,71,.06); }
      .card.spento { opacity:.75; border-left:4px solid var(--error-color,#db4437); }
      code { font-family:ui-monospace, monospace; font-size:.85em;
             background:var(--divider-color); padding:1px 5px; border-radius:4px; }

      /* ── legenda degli stati ─────────────────────────────────────────── */
      .spiega { list-style:none; margin:0 0 14px; padding:0; display:flex; flex-direction:column; gap:10px; }
      .spiega li { display:flex; align-items:flex-start; gap:10px; font-size:.95rem; line-height:1.5; }
      .spiega .ico { margin-top:2px; color:var(--secondary-text-color); }

      /* ═══════════════════════════════════════════════════════════════════
         TABLET E MOBILE

         Le tabelle non si comprimono: sei colonne su 375 px sono illeggibili
         a qualunque dimensione di carattere. Sotto i 780 px ogni riga diventa
         una scheda, e l'intestazione di colonna torna come etichetta davanti
         al valore (l'attributo data-etichetta sul <td>). Cosi' non si perde
         nessun dato e non si scrolla in orizzontale.
         ═══════════════════════════════════════════════════════════════════ */

      /* Sopravvivenza minima: qualunque tabella troppo larga scorre dentro il
         suo contenitore invece di allargare la pagina. */
      .tabella { overflow-x:auto; -webkit-overflow-scrolling:touch; }

      @media (max-width: 870px) {
        .hamburger { display:inline-flex; }
      }

      @media (max-width: 1024px) {
        .wrap { padding:14px; }
        .griglia { grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); }
      }

      @media (max-width: 780px) {
        .wrap { padding:12px; }
        .titolo { width:100%; }
        h1 { font-size:1.45rem; }
        /* Le schede scorrono in orizzontale invece di andare a capo su piu'
           righe, che farebbe saltare in basso il contenuto a ogni cambio. */
        nav { width:100%; overflow-x:auto; flex-wrap:nowrap; padding-bottom:4px;
              scrollbar-width:none; }
        nav::-webkit-scrollbar { display:none; }
        .tab { flex:0 0 auto; }

        .card { padding:14px; }
        .tabella { overflow-x:visible; }
        table, thead, tbody, tr, td { display:block; width:100%; }
        thead { display:none; }
        tbody tr { border:1px solid var(--divider-color); border-radius:10px;
                   padding:10px 12px; margin-bottom:10px; }
        tbody tr:last-child td { border-bottom:none; }
        td { border-bottom:1px solid var(--divider-color); padding:8px 0;
             display:flex; gap:12px; align-items:flex-start; }
        td:last-child { border-bottom:none; }
        /* L'etichetta di colonna davanti al valore. Le celle senza etichetta
           (la maniglia) non ne mostrano una vuota che sposterebbe tutto. */
        td[data-etichetta]:not([data-etichetta=""])::before {
          content:attr(data-etichetta);
          flex:0 0 34%;
          font-size:.75rem; text-transform:uppercase; letter-spacing:.4px;
          color:var(--secondary-text-color); padding-top:3px;
        }
        td.maniglia { justify-content:flex-end; }
        .nome-tessera { max-width:none; }
        .azioni { flex:1; }
        .mini { flex:1 1 auto; justify-content:center; }

        /* Il trascinamento non esiste sotto un dito: la maniglia qui e' solo
           il pulsante che apre l'elenco dei titolari. */
        tr { cursor:default; }

        .titolare { gap:11px; }
        .avatar { width:40px; height:40px; }
        .chi b { font-size:1.05rem; }
        .conteggio { font-size:1.25rem; }
        .attesa { gap:12px; }
        .scelta-varco, .scelta-varco button { width:100%; }
        .enroll-avvio .riga { flex-direction:column; align-items:stretch; }
        button { min-height:44px; }
        label { flex:1 1 100%; }
      }

      @media (max-width: 420px) {
        .griglia { grid-template-columns:1fr 1fr; }
        .mini span { display:none; }   /* restano le icone, gia' etichettate */
        .mini { flex:1 1 auto; padding:10px; }
        td[data-etichetta]:not([data-etichetta=""])::before { flex:0 0 42%; }
      }

      /* Su schermi con solo tocco il cursore "grab" e' una promessa che il
         dispositivo non puo' mantenere. */
      @media (hover: none) {
        .maniglia, .tocca-maniglia { cursor:pointer; }
      }
    `;
  }
}

// Il define va protetto: l'URL del modulo porta la versione, quindi lo
// stesso file puo' essere caricato due volte nella stessa pagina — la copia
// in cache e quella nuova. Un secondo define solleva, e sollevare qui fa
// fallire l'intero modulo: il pannello resta quello vecchio e non si capisce
// perche'. Vince il primo caricato; per prendere il nuovo basta ricaricare.
if (!customElements.get("access-control-panel")) {
  customElements.define("access-control-panel", AccessControlPanel);
}
