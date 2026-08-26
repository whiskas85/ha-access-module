// Pannello di Controllo Accessi.
//
// Allineata da scripts/bump.py alla versione del manifest: il pannello la
// confronta con quella dell'integration in esecuzione per accorgersi che i
// file sono stati aggiornati ma Home Assistant non è ancora ripartito.
const PANEL_VERSION = "0.1.0";

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
};

const STATO_ETICHETTA = {
  sleep: "Sleep",
  finestra_scuola: "Finestra scuola",
  rientro_adulto: "Rientro adulto",
  casa_occupata: "Casa occupata",
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
    const stati = this._hass?.states || {};
    const persone = Object.keys(stati)
      .filter((e) => e.startsWith("person."))
      .sort();
    const nome = (p) => stati[p]?.attributes?.friendly_name || p;

    const enr = d.enrollment || {};
    const boxEnrollment = enr.attivo
      ? `<div class="attesa">
           <div class="pulsa"></div>
           <div>
             <strong>In attesa della tessera…</strong>
             <p class="nota">Passa la tessera davanti al lettore.
               Si chiude fra <b>${enr.secondi}s</b>, o alla prima lettura.</p>
           </div>
           <button class="danger" data-act="cancel-enroll">Annulla</button>
         </div>`
      : `<div class="riga">
           <button data-act="start-enroll">Abilita lettura tessera</button>
           <p class="nota" style="flex:1 1 300px">
             La tessera viene letta e censita da sola: UID e tipo di chip li
             ricava il modulo. Nasce <b>senza titolare</b> e finché non gliene
             assegni uno non apre nulla — trascinala su una persona qui sotto.
           </p>
         </div>`;

    // Ogni titolare è un bersaglio del trascinamento, più un riquadro per
    // staccare l'abbinamento rimettendo la tessera fra quelle senza titolare.
    const orfane = d.tessere.filter((c) => !c.person).length;
    const bersagli = [
      `<div class="persona vuota" data-drop="">
         <b>Senza titolare</b>
         <span class="uid">${orfane} tessere · non aprono</span>
       </div>`,
      ...persone.map((p) => {
        const n = d.tessere.filter((c) => c.person === p).length;
        const ruolo = (d.impostazioni.person_roles || {})[p] || "adulto";
        return `<div class="persona" data-drop="${esc(p)}">
                  <b>${esc(nome(p))}</b>
                  <span class="uid">${esc(ruolo)} · ${n} tessere</span>
                </div>`;
      }),
    ].join("");

    const bottoni = (c) => {
      const b = [];
      if (c.state !== "attiva")
        b.push(`<button class="mini ok" data-set="${esc(c.id)}|attiva">Attiva</button>`);
      if (c.state !== "disabilitata")
        b.push(`<button class="mini" data-set="${esc(c.id)}|disabilitata">Disabilita</button>`);
      if (c.state !== "blacklist")
        b.push(`<button class="mini warn" data-set="${esc(c.id)}|blacklist">Blacklist</button>`);
      b.push(`<button class="mini danger" data-remove-card="${esc(c.id)}">Elimina</button>`);
      return b.join("");
    };

    const righe = d.tessere.length
      ? d.tessere
          .map(
            (c) => `
        <tr class="stato-${esc(c.state)}" draggable="true" data-card="${esc(c.id)}">
          <td class="maniglia">⠿</td>
          <td>
            <b>${esc(c.name)}</b>
            <div class="uid">${esc(c.uid)}</div>
          </td>
          <td>${c.person ? esc(nome(c.person)) : '<i class="orfana">nessuno</i>'}
              <div class="uid">${c.person ? esc(c.ruolo) : "non apre"}</div></td>
          <td>
            <span class="pill ${c.sicurezza === "forte" ? "forte" : "debole"}">${esc(c.sicurezza)}</span>
            <div class="uid">${esc(c.tecnologia_label)}</div>
          </td>
          <td><span class="pill s-${esc(c.state)}">${esc(c.state)}</span></td>
          <td>${quando(c.last_used)}<div class="uid">${c.uses} usi</div></td>
          <td class="azioni">${bottoni(c)}</td>
        </tr>`,
          )
          .join("")
      : `<tr><td colspan="7" class="vuoto">Nessuna tessera censita.</td></tr>`;

    return `
      <section class="card">
        <h2>Censimento</h2>
        ${boxEnrollment}
      </section>

      <section class="card">
        <h2>Titolari</h2>
        <p class="nota">Trascina una tessera dalla tabella su una persona per
          abbinarla. Il ruolo appartiene alla persona, non alla tessera: due
          tessere dello stesso titolare non possono avere permessi diversi.</p>
        <div class="persone">${bersagli}</div>
      </section>

      <section class="card">
        <h2>Registro tessere</h2>
        <table>
          <thead><tr>
            <th></th><th>Tessera</th><th>Titolare</th><th>Sicurezza</th>
            <th>Stato</th><th>Ultimo uso</th><th>Azioni</th>
          </tr></thead>
          <tbody>${righe}</tbody>
        </table>
        <p class="nota"><b>Disabilita</b> è una sospensione silenziosa, per una
          tessera riposta in un cassetto. <b>Blacklist</b> allarma se la tessera
          ripassa: è quella giusta per una tessera persa. <b>Elimina</b> la
          rende di nuovo sconosciuta, e quindi di nuovo silenziosa.</p>
      </section>

      <section class="card">
        <h2>Perché nessuna tessera risulta “forte”</h2>
        <p class="nota">Il livello non descrive il chip: descrive il fatto che
          il modulo abbia <b>verificato crittograficamente</b> la credenziale.
          Un NTAG424 di cui si legge solo l'UID si clona esattamente come una
          MIFARE Classic — la protezione sta nel cryptogram AES, che oggi
          nessuno verifica. Finché non arriva il componente che lo verifica,
          <b>forte</b> è irraggiungibile, ed è corretto così: a reggere la
          sicurezza è la macchina a stati, non la tessera.</p>
      </section>`;
  }

  // ── registro ─────────────────────────────────────────────────────────

  _vistaRegistro(d) {
    const righe = d.log.length
      ? d.log
          .map(
            (r) => `
        <tr class="esito-${esc(r.esito)}">
          <td>${quando(r.timestamp)}</td>
          <td><span class="pill e-${esc(r.esito)}">${esc(ESITO_ETICHETTA[r.esito] || r.esito)}</span></td>
          <td>${esc(r.card_nome || "sconosciuta")}<div class="uid">${esc(r.uid)}</div></td>
          <td>${esc(r.person || "—")}</td>
          <td>${esc(STATO_ETICHETTA[r.stato_sistema] || r.stato_sistema)}</td>
          <td>${esc(r.varco)}</td>
          <td class="motivo-cella">${esc(r.motivo || "")}</td>
        </tr>`,
          )
          .join("")
      : `<tr><td colspan="7" class="vuoto">Nessun accesso registrato.</td></tr>`;

    return `
      <section class="card">
        <h2>Registro accessi</h2>
        <p class="nota">Conservato dall'integration, non dal recorder: resta
          consultabile anche oltre la finestra di storico di Home Assistant.</p>
        <table>
          <thead><tr>
            <th>Quando</th><th>Esito</th><th>Tessera</th><th>Titolare</th>
            <th>Stato</th><th>Varco</th><th>Motivo</th>
          </tr></thead>
          <tbody>${righe}</tbody>
        </table>
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
        <h2>Ruoli dei titolari</h2>
        <p class="nota">Il ruolo appartiene alla persona, non alla tessera:
          due tessere dello stesso titolare non possono avere autorizzazioni
          diverse per svista.</p>
        ${(s.person_entities || [])
          .map(
            (p) => `
          <label>${esc(p)}
            <select data-ruolo="${esc(p)}">
              ${d.opzioni.ruoli
                .map(
                  (r) =>
                    `<option value="${esc(r)}" ${(s.person_roles || {})[p] === r ? "selected" : ""}>${esc(r)}</option>`,
                )
                .join("")}
            </select></label>`,
          )
          .join("")}
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

    r.querySelector('[data-act="start-enroll"]')?.addEventListener("click", () =>
      this._comando({ action: "start_enrollment" }),
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

    // ── trascinamento tessera → titolare ──────────────────────────────
    r.querySelectorAll("[data-card]").forEach((riga) => {
      riga.addEventListener("dragstart", (ev) => {
        this._dragging = riga.dataset.card;
        riga.classList.add("in-volo");
        ev.dataTransfer.effectAllowed = "move";
        // Firefox non avvia il trascinamento senza payload impostato.
        ev.dataTransfer.setData("text/plain", riga.dataset.card);
      });
      riga.addEventListener("dragend", () => {
        this._dragging = null;
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
      const ruoli = {};
      r.querySelectorAll("[data-ruolo]").forEach((el) => {
        ruoli[el.dataset.ruolo] = el.value;
      });

      this._comando({
        action: "set_settings",
        settings: {
          school_start: val("set-school_start"),
          school_end: val("set-school_end"),
          school_days: giorni,
          person_roles: ruoli,
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
      :host { display:block; background:var(--primary-background-color); color:var(--primary-text-color);
              font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      .wrap { max-width:1100px; margin:0 auto; padding:16px; }
      header { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:16px; }
      h1 { font-size:1.4rem; margin:0; flex:1; }
      h2 { font-size:1rem; margin:0 0 10px; }
      h3 { font-size:.95rem; margin:0 0 8px; }
      nav { display:flex; gap:4px; flex-wrap:wrap; }
      .tab { background:none; border:none; padding:8px 14px; border-radius:18px; cursor:pointer;
             color:var(--secondary-text-color); font-size:.9rem; }
      .tab.on { background:var(--primary-color); color:var(--text-primary-color, #fff); }
      .card { background:var(--card-background-color); border-radius:12px; padding:16px; margin-bottom:14px;
              box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
      .card.allarme { border-left:4px solid var(--error-color, #db4437); }
      .big { font-size:1.15rem; font-weight:600; }
      .big.ok { color:var(--success-color, #43a047); }
      .big.off { color:var(--secondary-text-color); }
      .motivo { margin:6px 0 14px; color:var(--secondary-text-color); }
      .griglia { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }
      .kv { display:flex; flex-direction:column; gap:2px; }
      .kv span { font-size:.75rem; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.4px; }
      .riga { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
      label { display:flex; flex-direction:column; gap:4px; font-size:.8rem;
              color:var(--secondary-text-color); flex:1 1 180px; }
      label.check { flex-direction:row; align-items:center; gap:6px; flex:0 0 auto; }
      input, select { padding:8px; border-radius:6px; border:1px solid var(--divider-color);
                      background:var(--card-background-color); color:var(--primary-text-color); font-size:.9rem; }
      button { padding:8px 14px; border-radius:6px; border:none; cursor:pointer;
               background:var(--primary-color); color:var(--text-primary-color,#fff); font-size:.85rem; }
      button.danger { background:var(--error-color, #db4437); }
      button.primario { width:100%; padding:12px; font-size:.95rem; }
      table { width:100%; border-collapse:collapse; font-size:.85rem; }
      th { text-align:left; padding:8px; border-bottom:2px solid var(--divider-color);
           font-size:.72rem; text-transform:uppercase; color:var(--secondary-text-color); }
      td { padding:8px; border-bottom:1px solid var(--divider-color); vertical-align:top; }
      .uid { font-size:.72rem; color:var(--secondary-text-color); font-family:monospace; }
      .azioni { display:flex; gap:6px; align-items:center; }
      .pill { display:inline-block; padding:2px 8px; border-radius:10px; font-size:.72rem; font-weight:600; }
      .pill.debole { background:rgba(255,167,38,.2); color:#e08600; }
      .pill.forte { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.s-attiva { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.s-disabilitata { background:rgba(158,158,158,.25); color:var(--secondary-text-color); }
      .pill.s-blacklist { background:rgba(219,68,55,.2); color:#c62828; }
      .pill.e-granted { background:rgba(67,160,71,.2); color:#2e7d32; }
      .pill.e-denied { background:rgba(158,158,158,.25); color:var(--secondary-text-color); }
      .pill.e-blacklist, .pill.e-lockout { background:rgba(219,68,55,.2); color:#c62828; }
      tr.stato-blacklist { background:rgba(219,68,55,.06); }
      .motivo-cella { font-size:.78rem; color:var(--secondary-text-color); }
      .nota { font-size:.8rem; color:var(--secondary-text-color); margin:0 0 12px; line-height:1.5; }
      .vuoto { text-align:center; padding:24px; color:var(--secondary-text-color); }
      .err { background:var(--error-color,#db4437); color:#fff; padding:10px 14px; border-radius:8px; margin-bottom:12px; }
      .giorni { display:flex; flex-wrap:wrap; gap:12px; margin-top:10px; }
      .varco { border:1px solid var(--divider-color); border-radius:8px; padding:12px; margin-bottom:10px;
               display:flex; flex-direction:column; gap:8px; }
      footer { text-align:center; font-size:.7rem; color:var(--secondary-text-color); padding:12px; }

      /* ── censimento ────────────────────────────────────────────────── */
      .attesa { display:flex; align-items:center; gap:14px; flex-wrap:wrap;
                border:2px dashed var(--primary-color); border-radius:10px; padding:14px; }
      .attesa > div:nth-child(2) { flex:1 1 240px; }
      .attesa .nota { margin:4px 0 0; }
      .pulsa { width:16px; height:16px; border-radius:50%; background:var(--primary-color);
               animation:pulsa 1.2s ease-in-out infinite; flex:0 0 auto; }
      @keyframes pulsa { 0%,100% { opacity:1; transform:scale(1); }
                         50% { opacity:.35; transform:scale(1.5); } }
      /* Chi non tollera le animazioni riceve comunque il conto alla rovescia. */
      @media (prefers-reduced-motion: reduce) { .pulsa { animation:none; } }

      /* ── titolari come bersagli del trascinamento ──────────────────── */
      .persone { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; }
      .persona { border:2px dashed var(--divider-color); border-radius:10px; padding:12px;
                 display:flex; flex-direction:column; gap:2px; transition:border-color .15s, background .15s; }
      .persona.vuota { border-style:dotted; opacity:.75; }
      .persona.sopra { border-color:var(--primary-color); border-style:solid;
                       background:color-mix(in srgb, var(--primary-color) 12%, transparent); }
      tr[draggable="true"] { cursor:grab; }
      tr.in-volo { opacity:.4; }
      .maniglia { color:var(--secondary-text-color); cursor:grab; user-select:none; width:1.2rem; }
      .orfana { color:var(--secondary-text-color); }
      .mini { padding:4px 9px; font-size:.72rem; background:var(--divider-color);
              color:var(--primary-text-color); }
      .mini.ok { background:rgba(67,160,71,.25); }
      .mini.warn { background:rgba(255,167,38,.3); }
      .mini.danger { background:rgba(219,68,55,.25); color:var(--primary-text-color); }
      .azioni { display:flex; gap:5px; flex-wrap:wrap; align-items:center; }
    `;
  }
}

customElements.define("access-control-panel", AccessControlPanel);
