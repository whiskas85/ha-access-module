#include "ntag424.h"

#include <memory>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

// Riferimenti:
// - NXP AN12196, NTAG 424 DNA features and hints (SDM, lettura del file NDEF)
// - NFC Forum Type 4 Tag, selezione dell'applicazione e del file NDEF
// - PN532 User Manual, InListPassiveTarget e InDataExchange

namespace esphome::ntag424 {

static const char *const TAG = "ntag424";

// Applicazione NDEF (NFC Forum Type 4) e, dentro, il file NDEF E104. Sono i
// comandi che manda un telefono: quelli con cui la 1ª prova ha letto il link.
static const std::vector<uint8_t> SELEZIONA_APPLICAZIONE = {0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76,
                                                             0x00, 0x00, 0x85, 0x01, 0x01, 0x00};
static const std::vector<uint8_t> SELEZIONA_FILE_NDEF = {0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x04};

// Più che sufficiente per un link SDM (il nostro sta sotto i cento byte), e
// abbastanza piccolo da stare in una sola risposta del PN532, che conta la
// lunghezza su un byte. Un file più lungo non è uno dei nostri: si lascia.
static const uint8_t MASSIMO_NDEF = 200;

// SEL_RES, bit 6: la tessera parla ISO 14443-4, cioè accetta comandi APDU. Il
// PN532 in quel caso ha già fatto da solo la RATS durante l'anticollisione.
static const uint8_t SAK_ISO14443_4 = 0x20;

// Quanti giri di fila senza vederla, prima di dare per tolta una tessera: a
// 500 ms per giro, un secondo e mezzo.
//
// Il PN532 ogni tanto perde per un giro una tessera che è ancora lì — alla
// prima prova una NTAG 424 appena appoggiata è stata letta due volte a un
// secondo di distanza, con i contatori consecutivi a dimostrarlo. Data per
// tolta al primo giro mancato, al giro dopo sembrava nuova e veniva riletta:
// una lettura in più a ogni appoggio, e con tre dinieghi di fila l'impianto
// va in allarme. Una tessera tolta e riappoggiata entro questo tempo resta
// la stessa lettura; se il gesto era voluto, basta ripassarla.
static const uint8_t ASSENZE_PER_TOLTA = 3;

// Una tessera trattenuta per il tramite senza comandi da tanto così viene
// rilasciata da sola. Durante una programmazione i comandi arrivano a pochi
// centesimi di secondo l'uno dall'altro: un silenzio lungo vuol dire che Home
// Assistant non c'è più, e il lettore non deve restare bloccato ad aspettarlo.
static const uint32_t SILENZIO_TRAMITE_MS = 5000;

// Il comando più lungo della programmazione sta sotto i cento byte; questo
// limite tiene la risposta dentro un solo pacchetto del PN532.
static const size_t MASSIMO_COMANDO = 200;

static int cifra_(char c) {
  if (c >= '0' && c <= '9')
    return c - '0';
  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;
  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;
  return -1;
}

static bool da_esadecimale_(const std::string &testo, std::vector<uint8_t> &dati) {
  if (testo.empty() || testo.size() % 2 != 0 || testo.size() > 2 * MASSIMO_COMANDO)
    return false;
  dati.clear();
  for (size_t i = 0; i < testo.size(); i += 2) {
    int alto = cifra_(testo[i]);
    int basso = cifra_(testo[i + 1]);
    if (alto < 0 || basso < 0)
      return false;
    dati.push_back(uint8_t((alto << 4) | basso));
  }
  return true;
}

static std::string in_esadecimale_(const uint8_t *dati, size_t quanti) {
  static const char *const CIFRE = "0123456789ABCDEF";
  std::string testo;
  testo.reserve(2 * quanti);
  for (size_t i = 0; i < quanti; i++) {
    testo.push_back(CIFRE[dati[i] >> 4]);
    testo.push_back(CIFRE[dati[i] & 0x0F]);
  }
  return testo;
}

// ── lettura ────────────────────────────────────────────────────────────────

void Ntag424Pn532I2C::update() {
  // Con una tessera trattenuta non si interroga il campo: una nuova
  // anticollisione la farebbe ripartire da zero a metà dei comandi.
  if (this->trattenuta_)
    return;
  pn532::PN532::update();
}

void Ntag424Pn532I2C::loop() {
  if (this->trattenuta_) {
    if (millis() - this->ultimo_scambio_ > SILENZIO_TRAMITE_MS) {
      ESP_LOGW(TAG, "Tramite: nessun comando da %u ms, tessera rilasciata", (unsigned) SILENZIO_TRAMITE_MS);
      this->rilascia_();
    }
    return;
  }

  if (!this->requested_read_)
    return;

  auto ready = this->read_ready_(false);
  if (ready == pn532::WOULDBLOCK)
    return;

  bool success = false;
  std::vector<uint8_t> read;
  if (ready == pn532::READY) {
    success = this->read_response(pn532::PN532_COMMAND_INLISTPASSIVETARGET, read);
  } else {
    this->send_ack_();  // interrompe l'InListPassiveTarget ancora in corso
  }
  this->requested_read_ = false;

  if (!success || read.empty() || read[0] != 1) {
    this->tessera_non_vista_();
    return;
  }

  // NbTg, Tg, SENS_RES (2), SEL_RES, NFCIDLength, NFCID…
  if (read.size() < 6)
    return;
  uint8_t nfcid_length = read[5];
  if (nfcid_length > nfc::NFC_UID_MAX_LENGTH || read.size() < 6U + nfcid_length)
    return;
  nfc::NfcTagUid nfcid(read.begin() + 6, read.begin() + 6 + nfcid_length);
  this->assenze_ = 0;

  // Tramite aperto: la tessera non si legge, si trattiene per Home Assistant.
  // Anche se era già appoggiata prima: è proprio quella che si vuole
  // programmare. Solo le ISO 14443-4, perché le altre i comandi non li
  // capirebbero; una Classic appoggiata adesso si ignora.
  if (this->tramite_) {
    if ((read[4] & SAK_ISO14443_4) == 0) {
      this->turn_off_rf_();
      return;
    }
    this->current_uid_ = nfcid;
    this->trattenuta_ = true;
    this->ultimo_scambio_ = millis();
    char buf[nfc::FORMAT_UID_BUFFER_SIZE];
    std::string uid = nfc::format_uid_to(buf, nfcid);
    ESP_LOGI(TAG, "Tramite: tessera trattenuta per Home Assistant");
    for (auto *trigger : this->triggers_pronta_)
      trigger->process(uid);
    return;
  }

  // Stessa tessera ancora appoggiata: è già stata riferita.
  //
  // Il campo si spegne anche qui, e non è un dettaglio. Il PN532 di ESPHome
  // lo lascia acceso, e con una tessera ISO 14443-4 è un difetto: dopo la
  // RATS la tessera resta attiva, non risponde più alla richiesta del giro
  // successivo, sembra tolta — e al giro dopo ancora, ripartita da zero,
  // sembra una tessera nuova. Una tessera lasciata sul lettore veniva così
  // riletta ogni secondo e mezzo, e con tre dinieghi di fila l'impianto va in
  // allarme. Spegnendo il campo la tessera riparte da zero a ogni giro, si
  // ripresenta con lo stesso UID, e resta la stessa lettura.
  if (nfcid.size() == this->current_uid_.size()) {
    bool stessa = true;
    for (size_t i = 0; i < nfcid.size(); i++)
      stessa &= nfcid[i] == this->current_uid_[i];
    if (stessa) {
      this->turn_off_rf_();
      return;
    }
  }
  this->current_uid_ = nfcid;

  char uid_buf[nfc::FORMAT_UID_BUFFER_SIZE];
  std::string uid = nfc::format_uid_to(uid_buf, nfcid);

  // Il link si chiede solo a chi parla ISO 14443-4: una MIFARE Classic non lo
  // saprebbe fare, e per lei resta l'UID, come sempre.
  std::string link;
  if ((read[4] & SAK_ISO14443_4) != 0) {
    switch (this->leggi_link_(link)) {
      case EsitoLink::LETTO:
        // La lunghezza e basta: il contenuto è il messaggio della tessera, e
        // nei log non ci deve finire (SPEC.md §11).
        ESP_LOGD(TAG, "Messaggio della tessera letto (%u caratteri)", (unsigned) link.size());
        break;
      case EsitoLink::ASSENTE:
        // Ha risposto a tutto e un link SDM non ce l'ha: è una lettura
        // completa del solo UID, e come tale si riferisce.
        ESP_LOGD(TAG, "Tessera ISO 14443-4 senza messaggio SDM");
        link.clear();
        break;
      case EsitoLink::INTERROTTO:
        // Si è fermata a metà. Riferire l'UID da solo sarebbe riferire una
        // lettura che non c'è stata — per una tessera forte, un diniego da
        // clone a chi ha solo tolto la mano troppo presto. Si chiede di
        // riappoggiarla, e si dimentica la tessera: se è ancora lì, al giro
        // dopo la si rilegge da capo (SPEC.md §15).
        ESP_LOGW(TAG, "Lettura interrotta a metà: la tessera va riappoggiata");
        this->current_uid_ = {};
        this->assenze_ = 0;
        for (auto *trigger : this->triggers_incompleta_)
          trigger->process(uid);
        this->turn_off_rf_();
        return;
    }
  }

  auto tag = std::make_unique<nfc::NfcTag>(nfcid);
  for (auto *trigger : this->triggers_ontag_)
    trigger->process(tag);
  for (auto *trigger : this->triggers_lettura_)
    trigger->process(uid, link);

  this->turn_off_rf_();
}

// Un giro senza tessera. Tolta davvero solo dopo ASSENZE_PER_TOLTA giri di
// fila: fino ad allora si continua a ricordarla, così se ricompare è la
// stessa e non si rilegge. Una tessera *diversa* invece si legge subito,
// perché il confronto in loop() è sull'UID.
void Ntag424Pn532I2C::tessera_non_vista_() {
  this->turn_off_rf_();
  if (this->current_uid_.empty())
    return;
  if (++this->assenze_ < ASSENZE_PER_TOLTA)
    return;

  auto tag = std::make_unique<nfc::NfcTag>(this->current_uid_);
  for (auto *trigger : this->triggers_ontagremoved_)
    trigger->process(tag);
  this->current_uid_ = {};
  this->assenze_ = 0;
}

// Un comando alla tessera attraverso il PN532, e quale dei tre esiti ha avuto.
//
// La distinzione che conta è fra una tessera che dice di no e una tessera che
// non risponde. La prima ha risposto per intero con una parola di stato
// diversa da 90 00: è un fatto sulla tessera. La seconda — il PN532 segnala un
// errore di radio, o non arriva niente — è un fatto sul gesto: la tessera se
// n'è andata, o non era appoggiata bene.
EsitoApdu Ntag424Pn532I2C::apdu_(const std::vector<uint8_t> &comando, std::vector<uint8_t> &risposta) {
  std::vector<uint8_t> frame = {pn532::PN532_COMMAND_INDATAEXCHANGE, 0x01};
  frame.insert(frame.end(), comando.begin(), comando.end());
  if (!this->write_command_(frame))
    return EsitoApdu::INTERROTTO;

  std::vector<uint8_t> dati;
  if (!this->read_response(pn532::PN532_COMMAND_INDATAEXCHANGE, dati) || dati.empty())
    return EsitoApdu::INTERROTTO;

  // [stato del PN532] [dati della tessera…] [SW1] [SW2]
  //
  // Nei 6 bit bassi dello stato c'è l'errore di radio: timeout, CRC, trama.
  // Il bit MI invece dice che la risposta continua in un altro pacchetto: la
  // tessera ha risposto, ma più di quanto un nostro comando chieda.
  if ((dati[0] & 0x3F) != 0x00)
    return EsitoApdu::INTERROTTO;
  if (dati[0] != 0x00 || dati.size() < 3)
    return EsitoApdu::RIFIUTATO;
  if (dati[dati.size() - 2] != 0x90 || dati[dati.size() - 1] != 0x00)
    return EsitoApdu::RIFIUTATO;

  risposta.assign(dati.begin() + 1, dati.end() - 2);
  return EsitoApdu::OK;
}

// Il link scritto nella tessera, senza il prefisso (https://…). È ciò che la
// tessera produce a ogni lettura quando l'SDM è acceso: UID e contatore
// cifrati, più la firma, nel punto in cui erano gli zeri segnaposto.
//
// Un comando che non ha risposta interrompe tutto: la lettura è a metà. Un
// comando rifiutato, o una risposta di forma inattesa, dice invece che questa
// tessera un link SDM non ce l'ha — una DESFire senza applicazione NDEF, un
// file letto per intero ma diverso dal nostro.
EsitoLink Ntag424Pn532I2C::leggi_link_(std::string &link) {
  std::vector<uint8_t> risposta;
  auto passo = [](EsitoApdu esito) {
    return esito == EsitoApdu::INTERROTTO ? EsitoLink::INTERROTTO : EsitoLink::ASSENTE;
  };

  EsitoApdu esito = this->apdu_(SELEZIONA_APPLICAZIONE, risposta);
  if (esito != EsitoApdu::OK)
    return passo(esito);
  esito = this->apdu_(SELEZIONA_FILE_NDEF, risposta);
  if (esito != EsitoApdu::OK)
    return passo(esito);

  // I primi due byte del file sono la lunghezza del messaggio NDEF.
  esito = this->apdu_({0x00, 0xB0, 0x00, 0x00, 0x02}, risposta);
  if (esito != EsitoApdu::OK)
    return passo(esito);
  if (risposta.size() != 2)
    return EsitoLink::ASSENTE;
  uint16_t lunghezza = (uint16_t(risposta[0]) << 8) | risposta[1];
  if (lunghezza < 6 || lunghezza > MASSIMO_NDEF)
    return EsitoLink::ASSENTE;

  std::vector<uint8_t> ndef;
  esito = this->apdu_({0x00, 0xB0, 0x00, 0x02, uint8_t(lunghezza)}, ndef);
  if (esito != EsitoApdu::OK)
    return passo(esito);
  if (ndef.size() != lunghezza)
    return EsitoLink::ASSENTE;

  // Un solo record, breve, di tipo URI: MB e ME accesi, SR acceso, nessun ID,
  // TNF «well-known», tipo «U». È l'unica forma che produce la configurazione
  // SDM di questo impianto; qualunque altra cosa non si prova a interpretare.
  if ((ndef[0] & 0xF8) != 0xD0 || (ndef[0] & 0x07) != 0x01)
    return EsitoLink::ASSENTE;
  if (ndef[1] != 1 || ndef[3] != 'U')
    return EsitoLink::ASSENTE;
  uint8_t lunghezza_dati = ndef[2];
  if (lunghezza_dati < 2 || 4U + lunghezza_dati != ndef.size())
    return EsitoLink::ASSENTE;

  // ndef[4] è il codice del prefisso: non serve, conta la parte dopo.
  link.clear();
  for (size_t i = 5; i < ndef.size(); i++) {
    uint8_t c = ndef[i];
    if (c < 0x21 || c > 0x7E) {
      link.clear();
      return EsitoLink::ASSENTE;
    }
    link.push_back(char(c));
  }
  return EsitoLink::LETTO;
}

// ── tramite ────────────────────────────────────────────────────────────────

void Ntag424Pn532I2C::set_tramite(bool attivo) {
  this->tramite_ = attivo;
  if (!attivo)
    this->rilascia_();
  ESP_LOGI(TAG, "Tramite %s", attivo ? "aperto" : "chiuso");
}

// La tessera torna libera. Resta però «quella già vista»: se è ancora
// appoggiata non viene riletta, e una lettura subito dopo la programmazione
// non si trasforma in un tentativo di accesso che nessuno ha voluto.
void Ntag424Pn532I2C::rilascia_() {
  if (this->trattenuta_) {
    this->trattenuta_ = false;
    this->turn_off_rf_();
  }
}

std::string Ntag424Pn532I2C::scambia(const std::string &comando) {
  if (!this->tramite_ || !this->trattenuta_)
    return "";

  std::vector<uint8_t> frame = {pn532::PN532_COMMAND_INDATAEXCHANGE, 0x01};
  std::vector<uint8_t> byte_comando;
  if (!da_esadecimale_(comando, byte_comando)) {
    ESP_LOGW(TAG, "Tramite: comando non valido, ignorato");
    return "";
  }
  frame.insert(frame.end(), byte_comando.begin(), byte_comando.end());

  std::vector<uint8_t> dati;
  if (!this->write_command_(frame) || !this->read_response(pn532::PN532_COMMAND_INDATAEXCHANGE, dati) ||
      dati.empty() || dati[0] != 0x00) {
    // La tessera non ha risposto: si è allontanata. La si rilascia subito,
    // e sarà Home Assistant a dire com'è andata.
    ESP_LOGW(TAG, "Tramite: la tessera non risponde più");
    this->rilascia_();
    return "";
  }

  this->ultimo_scambio_ = millis();
  // I byte non vanno nei log: sono il dialogo cifrato con la tessera.
  return in_esadecimale_(dati.data() + 1, dati.size() - 1);
}

void Ntag424Pn532I2C::dump_config() {
  ESP_LOGCONFIG(TAG, "PN532 con lettura del messaggio NTAG 424:");
  PN532::dump_config();
  LOG_I2C_DEVICE(this);
}

// ── trasporto I²C, identico a pn532_i2c di ESPHome ─────────────────────────

bool Ntag424Pn532I2C::is_read_ready() {
  uint8_t ready;
  if (!this->read_bytes_raw(&ready, 1)) {
    return false;
  }
  return ready == 0x01;
}

bool Ntag424Pn532I2C::write_data(const std::vector<uint8_t> &data) {
  return this->write(data.data(), data.size()) == i2c::ERROR_OK;
}

bool Ntag424Pn532I2C::read_data(std::vector<uint8_t> &data, uint8_t len) {
  delay(1);

  if (this->read_ready_(true) != pn532::PN532ReadReady::READY) {
    return false;
  }

  data.resize(len + 1);
  this->read_bytes_raw(data.data(), len + 1);
  return true;
}

bool Ntag424Pn532I2C::read_response(uint8_t command, std::vector<uint8_t> &data) {
  uint8_t len = this->read_response_length_();
  if (len == 0) {
    return false;
  }

  if (!this->read_data(data, 6 + len + 2)) {
    return false;
  }

  if (data[1] != 0x00 || data[2] != 0x00 || data[3] != 0xFF) {
    return false;
  }

  bool valid_header = (static_cast<uint8_t>(data[4] + data[5]) == 0 &&  // LCS, len + lcs = 0
                       data[6] == 0xD5 &&                               // TFI, dal PN532 all'host
                       data[7] == command + 1);                         // risposta al comando giusto
  if (!valid_header) {
    return false;
  }

  data.erase(data.begin(), data.begin() + 6);  // intestazione

  uint8_t checksum = 0;
  for (int i = 0; i < len + 1; i++) {
    checksum += data[i];
  }
  checksum = ~checksum + 1;

  if (data[len + 1] != checksum) {
    return false;
  }
  if (data[len + 2] != 0x00) {
    return false;
  }

  data.erase(data.begin(), data.begin() + 2);  // TFI e codice del comando
  data.erase(data.end() - 2, data.end());      // checksum e postambolo
  return true;
}

uint8_t Ntag424Pn532I2C::read_response_length_() {
  std::vector<uint8_t> data;
  if (!this->read_data(data, 6)) {
    return 0;
  }

  if (data[1] != 0x00 || data[2] != 0x00 || data[3] != 0xFF) {
    return 0;
  }

  bool valid_header = (static_cast<uint8_t>(data[4] + data[5]) == 0 && data[6] == 0xD5);
  if (!valid_header) {
    return 0;
  }

  this->send_nack_();

  uint8_t full_len = data[4];  // lunghezza del messaggio, TFI compreso
  uint8_t len = full_len - 1;
  if (full_len == 0)
    len = 0;
  return len;
}

}  // namespace esphome::ntag424
