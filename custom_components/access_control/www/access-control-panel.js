// Pannello di Controllo Accessi.
//
// Allineata da scripts/bump.py alla versione del manifest: il pannello la
// confronta con quella dell'integration in esecuzione per accorgersi che i
// file sono stati aggiornati ma Home Assistant non è ancora ripartito.
const PANEL_VERSION = "0.3.0";

const TABS = [
  { id: "stato", label: "Stato" },
  { id: "tessere", label: "Tessere" },
  { id: "registro", label: "Registro" },
  { id: "impostazioni", label: "Impostazioni" },
];

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

const ESITO_ETICHETTA = {
  granted: "consentito",
  denied: "negato",
  blacklist: "BLACKLIST",
  lockout: "lockout",
  // Un censimento non è un tentativo di accesso: al lettore risponde `ok` e
  // non entra nel conteggio dei rifiuti.
  enrolled: "censita",
};

const STATO_ETICHETTA = {
  sleep: "Sleep",
  finestra_scuola: "Finestra scuola",
  rientro_adulto: "Rientro adulto",
  casa_occupata: "Casa occupata",
};

// Icone Material Design Icons, inline: il pannello vive in uno shadow root e
// non eredita il set di icone del frontend, quindi i path se li porta dietro.
const ICONE = {
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
};

const icona = (nome, cls = "") =>
  `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${ICONE[nome] || ""}"/></svg>`;

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
    }
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
  }

  _puoRinfrescare() {
    // Durante l'enrollment si rinfresca sempre: serve il conto alla rovescia,
    // e chi sta censendo è al lettore, non con le mani sulla tastiera.
    if (this._data?.enrollment?.attivo) return true;
    // Un ridisegno azzera un trascinamento a metà e cancella quello che si
    // sta scrivendo in un campo: finché una delle due cose è in corso, la
    // pagina aspetta.
    if (this._dragging) return false;
    const a = this.shadowRoot.activeElement;
    if (a && ["INPUT", "SELECT", "TEXTAREA"].includes(a.tagName)) return false;
    // Fuori dall'enrollment basta un giro ogni 10 s.
    this._tick = (this._tick || 0) + 1;
    return this._tick % 5 === 0;
  }

  async _carica() {
    if (!this._hass) return;
    try {
      this._data = await this._hass.callApi("get", "access_control/state");
      this._errore = "";
    } catch (err) {
      this._errore = err?.message || "Impossibile leggere lo stato";
    }
    this._render();
  }

  async _comando(payload) {
    try {
      this._data = await this._hass.callApi(
        "post",
        "access_control/command",
        payload,
      );
      this._errore = "";
    } catch (err) {
      this._errore = err?.body?.message || err?.message || "Comando fallito";
    }
    this._render();
  }

  // ── rendering ────────────────────────────────────────────────────────

  _render() {
    if (!this.shadowRoot) return;
    const d = this._data;

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="wrap">
        <header>
          <h1>Controllo Accessi</h1>
          <nav>
            ${TABS.map(
              (t) =>
                `<button class="tab ${t.id === this._tab ? "on" : ""}" data-tab="${t.id}">${t.label}</button>`,
            ).join("")}
          </nav>
        </header>
        ${this._errore ? `<div class="err">${esc(this._errore)}</div>` : ""}
        ${d ? this._corpo(d) : `<div class="vuoto">Caricamento…</div>`}
        <footer>pannello v${PANEL_VERSION}</footer>
      </div>`;

    this.shadowRoot.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", () => {
        this._tab = el.dataset.tab;
        this._render();
      }),
    );
    this._agganciaAzioni();
  }

  _corpo(d) {
    if (this._tab === "stato") return this._vistaStato(d);
    if (this._tab === "tessere") return this._vistaTessere(d);
    if (this._tab === "registro") return this._vistaRegistro(d);
    return this._vistaImpostazioni(d);
  }

  // ── stato ────────────────────────────────────────────────────────────

  _vistaStato(d) {
    const s = d.stato;
    const badge = s.armato
      ? `<span class="big ok">🔓 Sistema armato</span>`
      : `<span class="big off">🔒 Sistema in sleep</span>`;

    const ultimo = d.log.find((r) => r.esito === "granted");

    return `
      <section class="card">
        ${badge}
        <p class="motivo">${esc(s.motivo || "—")}</p>
        <div class="griglia">
          ${this._kv("Stato", STATO_ETICHETTA[s.sistema] || s.sistema)}
          ${this._kv("Porta", s.porta)}
          ${this._kv("Ultimo accesso", ultimo ? `${quando(ultimo.timestamp)} — ${esc(ultimo.card_nome)}` : "mai")}
          ${this._kv("Negati oggi", s.negati_oggi)}
          ${this._kv("Tessere censite", d.tessere.length)}
          ${this._kv("Fallimenti consecutivi", s.fallimenti)}
        </div>
      </section>

      ${
        s.lockout
          ? `<section class="card allarme">
               <strong>🚨 Lettori in allarme</strong>
               <p>Modalità <b>${esc(d.impostazioni.lockout_mode)}</b>, fino alle ${quando(s.bloccati_fino_a)}.
               ${
                 d.impostazioni.lockout_mode === "segnala"
                   ? "Le credenziali valide continuano a funzionare."
                   : "<b>Ogni lettura è rifiutata, comprese quelle valide.</b>"
               }</p>
               <button data-act="unlock">Sblocca i lettori</button>
             </section>`
          : ""
      }

      <section class="card">
        <h2>Perché il sistema fa così</h2>
        <div class="griglia">
          ${this._kv("Master", s.master ? "acceso" : "spento")}
          ${this._kv("Finestra scuola attiva", s.finestra_scuola ? "sì" : "no")}
          ${this._kv("Presenza recente", s.presenza ? "sì" : "no")}
          ${this._kv("Adulto in avvicinamento", s.adulto_vicino ? "sì" : "no")}
        </div>
      </section>

      <section class="card">
        <h2>Prova una lettura</h2>
        <p class="nota">Percorre tutta la catena — decisione, hook, script,
          registro — senza andare al varco.</p>
        <div class="riga">
          <input id="prova-uid" placeholder="UID" />
          <select id="prova-varco">
            ${d.varchi.map((g) => `<option value="${esc(g.id)}">${esc(g.name)}</option>`).join("")}
          </select>
          <button data-act="scan">Valuta</button>
        </div>
      </section>`;
  }

  _kv(k, v) {
    return `<div class="kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
  }

  // ── tessere ──────────────────────────────────────────────────────────

  _vistaTessere(d) {
    const enr = d.enrollment || {};
    const varchi = d.varchi || [];

    // ── censimento: sempre esplicito su QUALE lettore ───────────────────
    const piuVarchi = varchi.length > 1;
    const bottoniVarco = varchi
      .map(
        (g) => `<div class="scelta-varco">
                  <button data-enroll="${esc(g.id)}">
                    ${icona("cardPlus")} Abilita lettura — ${esc(g.name)}
                  </button>
                  <span class="uid">${
                    g.reader_device_mancante
                      ? (piuVarchi
                          ? `<span class="avviso">${icona("alert")} nessun lettore associato: le letture finiscono sul primo varco</span>`
                          : "lettore non associato — con un varco solo va bene lo stesso")
                      : `lettore: ${esc(g.reader_device_name || g.reader_device_id)}`
                  }</span>
                </div>`,
      )
      .join("");

    const boxEnrollment = enr.attivo
      ? `<div class="attesa">
           <div class="pulsa"></div>
           <div class="attesa-testo">
             <strong>In attesa della tessera su “${esc(enr.varco_nome || enr.varco)}”</strong>
             <p class="nota">Passa la tessera davanti a <b>quel</b> lettore.
               Una lettura da un altro varco viene valutata normalmente, non censita.
               Si chiude fra <b>${enr.secondi}s</b>, o alla prima lettura.</p>
           </div>
           <button class="danger" data-act="cancel-enroll">${icona("close")} Annulla</button>
         </div>`
      : `<div class="enroll-avvio">
           <div class="riga">${bottoniVarco}</div>
           <p class="nota">
             La tessera viene letta e censita da sola: UID e tipo di chip li ricava
             il modulo. Nasce <b>senza titolare</b>, e finché non gliene assegni uno
             non apre nulla — trascinala sulla persona qui sotto.
           </p>
         </div>`;

    // ── gruppi: prima le orfane, poi un gruppo per titolare ─────────────
    const persone = d.persone || [];
    const orfane = d.tessere.filter((c) => !c.person);
    const gruppi = [this._gruppoOrfane(orfane, persone)];

    for (const p of persone) {
      gruppi.push(
        this._gruppoPersona(
          p,
          d.tessere.filter((c) => c.person === p.entity_id),
          persone,
        ),
      );
    }

    return `
      <section class="card">
        <h2>Censimento</h2>
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
    const vuoto = tessere.length === 0;
    return `
      <section class="card gruppo ${vuoto ? "spento" : "orfane"}" data-drop="">
        <header class="titolare">
          <div class="avatar avatar-orfano">${icona(vuoto ? "check" : "alert")}</div>
          <div class="chi">
            <b>Senza titolare</b>
            <span class="sotto">${
              vuoto
                ? "nessuna tessera in sospeso"
                : `${tessere.length} ${tessere.length === 1 ? "tessera non apre" : "tessere non aprono"} — assegnale a una persona`
            }</span>
          </div>
          <span class="conteggio">${tessere.length}</span>
        </header>
        ${vuoto ? "" : this._tabellaTessere(tessere, persone)}
      </section>`;
  }

  _gruppoPersona(p, tessere, persone) {
    const avatar = p.foto
      ? `<img class="avatar" src="${esc(p.foto)}" alt="" />`
      : `<div class="avatar avatar-iniziali">${esc(
          p.nome.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase(),
        )}</div>`;

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

    // Il ruolo si sceglie qui, dove si vede a chi lo si sta dando. Senza
    // ruolo le tessere di questa persona non aprono: è una decisione che
    // manca, non un valore da indovinare.
    const ruolo = p.ruolo
      ? `<span class="tag ruolo-${esc(p.ruolo)}">${esc(p.ruolo)}</span>`
      : `<span class="tag ruolo-mancante">${icona("alert")} ruolo da assegnare</span>`;

    const sceltaRuolo = `
      <div class="ruoli">
        ${["bambino", "adulto"]
          .map(
            (r) =>
              `<button class="mini ${p.ruolo === r ? "ok" : ""}"
                 data-ruolo="${esc(p.entity_id)}|${r}">${r}</button>`,
          )
          .join("")}
        ${
          p.ruolo
            ? `<button class="mini" data-ruolo="${esc(p.entity_id)}|">togli</button>`
            : ""
        }
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
              <span class="punto ${p.stato === "home" ? "acceso" : ""}"></span>${esc(dove)}
              · ${esc(dettaglio)}
            </span>
          </div>
          <span class="conteggio">${tessere.length}</span>
        </header>
        ${sceltaRuolo}
        ${
          p.ruolo
            ? ""
            : `<p class="nota avviso-blocco">${icona("alert")}
                 Finché non ha un ruolo, le sue tessere <b>non aprono nulla</b>.
                 Non viene trattata come adulto per comodità: sarebbe darle i
                 permessi più ampi proprio perché nessuno ha detto chi è.</p>`
        }
        ${
          tessere.length
            ? this._tabellaTessere(tessere, persone)
            : `<p class="nota vuoto-gruppo">Trascina qui una tessera per abbinargliela.</p>`
        }
      </section>`;
  }

  _tabellaTessere(tessere, persone) {
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
          <td colspan="6">
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
            <th></th><th>Tessera</th><th>Sicurezza</th>
            <th>Stato</th><th>Ultimo uso</th><th>Azioni</th>
          </tr></thead>
          <tbody>${righe}</tbody>
        </table>
      </div>`;
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
          <td data-etichetta="Titolare">${esc(r.person || "—")}</td>
          <td data-etichetta="Stato">${esc(STATO_ETICHETTA[r.stato_sistema] || r.stato_sistema)}</td>
          <td data-etichetta="Varco">${esc(r.varco)}</td>
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
    const s = d.impostazioni;
    const giorni = s.school_days || [];
    const script = Object.keys(this._hass?.states || {})
      .filter((e) => e.startsWith("script."))
      .sort();
    const opt = (lista, sel) =>
      [`<option value="">— nessuno —</option>`]
        .concat(
          lista.map(
            (e) =>
              `<option value="${esc(e)}" ${e === sel ? "selected" : ""}>${esc(e)}</option>`,
          ),
        )
        .join("");

    const varchi = d.varchi
      .map(
        (g) => `
      <div class="varco" data-gate="${esc(g.id)}">
        <h3>${esc(g.name)} <span class="uid">${esc(g.id)}</span></h3>
        <label>Script di apertura
          <select data-g="action_script">${opt(script, g.action_script)}</select></label>
        <label>Pre-hook (può vietare l'apertura)
          <select data-g="pre_hook">${opt(script, g.pre_hook)}</select></label>
        <label>Post-hook
          <select data-g="post_hook">${opt(script, g.post_hook)}</select></label>
        <label>Servizio di risposta al lettore
          <input data-g="reader_service" value="${esc(g.reader_service || "")}"
                 placeholder="esphome.rfid_ingresso_esito_accesso" /></label>
        <label>Device id del lettore
          <input data-g="reader_device_id" value="${esc(g.reader_device_id || "")}" /></label>
        <label class="check"><input type="checkbox" data-g="pre_hook_fail_closed"
          ${g.pre_hook_fail_closed ? "checked" : ""} /> Se il pre-hook fallisce, non aprire</label>
        <button data-save-gate="${esc(g.id)}">Salva varco</button>
      </div>`,
      )
      .join("");

    return `
      <section class="card">
        <h2>Finestra scuola</h2>
        <div class="riga">
          <label>Inizio <input type="time" id="set-school_start" value="${esc(s.school_start)}" /></label>
          <label>Fine <input type="time" id="set-school_end" value="${esc(s.school_end)}" /></label>
        </div>
        <div class="giorni">
          ${GIORNI.map(
            (g, i) =>
              `<label class="check"><input type="checkbox" data-giorno="${i}"
                 ${giorni.includes(i) ? "checked" : ""} /> ${g}</label>`,
          ).join("")}
        </div>
      </section>

      <section class="card">
        <h2>Comportamento</h2>
        <div class="riga">
          <label>Ritardo sleep (min)
            <input type="number" id="set-sleep_delay_min" value="${esc(s.sleep_delay_min)}" min="1" /></label>
          <label>Porta socchiusa (min)
            <input type="number" id="set-door_ajar_min" value="${esc(s.door_ajar_min)}" min="1" /></label>
          <label>Rate limit finestra (s)
            <input type="number" id="set-rate_limit_window_s" value="${esc(s.rate_limit_window_s)}" min="1" /></label>
          <label>Rate limit max
            <input type="number" id="set-rate_limit_max" value="${esc(s.rate_limit_max)}" min="1" /></label>
        </div>
      </section>

      <section class="card">
        <h2>Lockout lettori</h2>
        <p class="nota"><b>segnala</b> non blocca nulla: notifica e conta.
          <b>blocca</b> rifiuta ogni lettura, comprese quelle valide — e chi
          deve entrare resta fuori finché non scade o non lo sblocchi da qui.
          Il default è <i>segnala</i> perché bastano N letture di una tessera
          qualsiasi per armare un lockout contro chi ha diritto di entrare,
          mentre il brute-force dell'UID che il blocco fermerebbe richiederebbe
          comunque secoli.</p>
        <div class="riga">
          <label>Modalità
            <select id="set-lockout_mode">
              ${d.opzioni.modalita_lockout
                .map(
                  (m) =>
                    `<option value="${esc(m)}" ${m === s.lockout_mode ? "selected" : ""}>${esc(m)}</option>`,
                )
                .join("")}
            </select></label>
          <label>Soglia fallimenti
            <input type="number" id="set-lockout_threshold" value="${esc(s.lockout_threshold)}" min="1" /></label>
          <label>Durata (min)
            <input type="number" id="set-lockout_duration_min" value="${esc(s.lockout_duration_min)}" min="1" /></label>
        </div>
      </section>

      <section class="card">
        <h2>Notifiche e sensori</h2>
        <div class="riga">
          <label>Servizio di notifica
            <input id="set-notify_service" value="${esc(s.notify_service || "")}" /></label>
          <label>Telecamera
            <input id="set-camera_entity" value="${esc(s.camera_entity || "")}" /></label>
          <label>Serratura
            <input id="set-door_lock_entity" value="${esc(s.door_lock_entity || "")}" /></label>
          <label>Contatto porta
            <input id="set-door_contact_entity" value="${esc(s.door_contact_entity || "")}" /></label>
        </div>
        <div class="riga">
          <label class="check"><input type="checkbox" id="set-notify_on_entry"
            ${s.notify_on_entry ? "checked" : ""} /> Notifica ogni accesso</label>
          <label class="check"><input type="checkbox" id="set-notify_on_denied"
            ${s.notify_on_denied ? "checked" : ""} /> Notifica ogni diniego</label>
        </div>
      </section>

      <section class="card">
        <h2>Varchi e hook</h2>
        <p class="nota">Il modulo non apre: decide, risponde al lettore e
          chiama questi script. Senza script di apertura configurato nega e lo
          scrive nel registro — non apre "di default".</p>
        ${varchi}
      </section>

      <button class="primario" data-act="save-settings">Salva impostazioni</button>`;
  }

  // ── azioni ───────────────────────────────────────────────────────────

  _agganciaAzioni() {
    const r = this.shadowRoot;
    const val = (id) => r.getElementById(id)?.value ?? "";
    const num = (id) => Number(val(id));
    const chk = (id) => r.getElementById(id)?.checked ?? false;

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
    r.querySelectorAll("[data-enroll]").forEach((el) =>
      el.addEventListener("click", () =>
        this._comando({ action: "start_enrollment", gate: el.dataset.enroll }),
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
          gate[f.dataset.g] = f.type === "checkbox" ? f.checked : f.value;
        });
        this._comando({ action: "upsert_gate", gate });
      }),
    );

    r.querySelector('[data-act="save-settings"]')?.addEventListener("click", () => {
      const giorni = [...r.querySelectorAll("[data-giorno]")]
        .filter((c) => c.checked)
        .map((c) => Number(c.dataset.giorno));
      this._comando({
        action: "set_settings",
        settings: {
          school_start: val("set-school_start"),
          school_end: val("set-school_end"),
          school_days: giorni,
          // person_roles non si tocca da qui: lo scrive la scheda della
          // persona. Mandarlo da questa form lo azzererebbe, perche' qui
          // i selettori dei ruoli non esistono piu'.
          sleep_delay_min: num("set-sleep_delay_min"),
          door_ajar_min: num("set-door_ajar_min"),
          rate_limit_window_s: num("set-rate_limit_window_s"),
          rate_limit_max: num("set-rate_limit_max"),
          lockout_mode: val("set-lockout_mode"),
          lockout_threshold: num("set-lockout_threshold"),
          lockout_duration_min: num("set-lockout_duration_min"),
          notify_service: val("set-notify_service"),
          camera_entity: val("set-camera_entity"),
          door_lock_entity: val("set-door_lock_entity"),
          door_contact_entity: val("set-door_contact_entity"),
          notify_on_entry: chk("set-notify_on_entry"),
          notify_on_denied: chk("set-notify_on_denied"),
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
      header { display:flex; flex-wrap:wrap; align-items:center; gap:14px; margin-bottom:18px; }
      h1 { font-size:1.7rem; margin:0; flex:1; }
      h2 { font-size:1.2rem; margin:0 0 12px; }
      nav { display:flex; gap:6px; flex-wrap:wrap; }
      .tab { background:none; border:none; padding:10px 18px; border-radius:20px; cursor:pointer;
             color:var(--secondary-text-color); font-size:1rem; }
      .tab.on { background:var(--primary-color); color:var(--text-primary-color, #fff); }
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
      input, select { padding:10px; border-radius:7px; border:1px solid var(--divider-color);
                      background:var(--card-background-color); color:var(--primary-text-color); font-size:1rem;
                      font-family:inherit; }
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
      .pill.e-blacklist, .pill.e-lockout { background:rgba(219,68,55,.2); color:#c62828; }
      tr.stato-blacklist { background:rgba(219,68,55,.07); }
      tr.stato-disabilitata { opacity:.68; }
      .motivo-cella { font-size:.85rem; color:var(--secondary-text-color); }
      .nota { font-size:.9rem; color:var(--secondary-text-color); margin:0 0 12px; line-height:1.55; }
      .vuoto { text-align:center; padding:26px; color:var(--secondary-text-color); }
      .err { background:var(--error-color,#db4437); color:#fff; padding:12px 16px; border-radius:8px; margin-bottom:14px; }
      .giorni { display:flex; flex-wrap:wrap; gap:14px; margin-top:12px; }
      .varco { border:1px solid var(--divider-color); border-radius:8px; padding:14px; margin-bottom:12px;
               display:flex; flex-direction:column; gap:10px; }
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
      .gruppo.spento .avatar-orfano { background:rgba(67,160,71,.18); color:#2e7d32; }
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
      .avviso-blocco { display:flex; gap:8px; align-items:flex-start;
                       background:rgba(255,167,38,.12); border-radius:8px; padding:10px 12px; }
      .avviso-blocco .ico { flex:0 0 auto; color:#e08600; margin-top:2px; }

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

      @media (max-width: 1024px) {
        .wrap { padding:14px; }
        .griglia { grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); }
      }

      @media (max-width: 780px) {
        .wrap { padding:12px; }
        h1 { font-size:1.45rem; width:100%; }
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

customElements.define("access-control-panel", AccessControlPanel);
