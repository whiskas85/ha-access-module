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

// ── lettura ────────────────────────────────────────────────────────────────

void Ntag424Pn532I2C::loop() {
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
    this->tessera_andata_via_();
    return;
  }

  // NbTg, Tg, SENS_RES (2), SEL_RES, NFCIDLength, NFCID…
  if (read.size() < 6)
    return;
  uint8_t nfcid_length = read[5];
  if (nfcid_length > nfc::NFC_UID_MAX_LENGTH || read.size() < 6U + nfcid_length)
    return;
  nfc::NfcTagUid nfcid(read.begin() + 6, read.begin() + 6 + nfcid_length);

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

  // Il link si chiede solo a chi parla ISO 14443-4. Una MIFARE Classic non lo
  // saprebbe fare, e una lettura fallita non toglie niente: resta l'UID, cioè
  // esattamente quello che il lettore riferiva prima. Se non si legge, non si
  // inventa niente — sarà Home Assistant a trattarla come una lettura debole.
  std::string link;
  if ((read[4] & SAK_ISO14443_4) != 0) {
    if (this->leggi_link_(link)) {
      // La lunghezza e basta: il contenuto è il messaggio della tessera, e nei
      // log non ci deve finire (SPEC.md §11).
      ESP_LOGD(TAG, "Messaggio della tessera letto (%u caratteri)", (unsigned) link.size());
    } else {
      ESP_LOGD(TAG, "Tessera ISO 14443-4 senza un messaggio leggibile");
      link.clear();
    }
  }

  auto tag = std::make_unique<nfc::NfcTag>(nfcid);
  for (auto *trigger : this->triggers_ontag_)
    trigger->process(tag);
  for (auto *trigger : this->triggers_lettura_)
    trigger->process(uid, link);

  this->turn_off_rf_();
}

void Ntag424Pn532I2C::tessera_andata_via_() {
  if (!this->current_uid_.empty()) {
    auto tag = std::make_unique<nfc::NfcTag>(this->current_uid_);
    for (auto *trigger : this->triggers_ontagremoved_)
      trigger->process(tag);
  }
  this->current_uid_ = {};
  this->turn_off_rf_();
}

// Un comando alla tessera attraverso il PN532. Riesce solo se il PN532 non
// segnala errori, se la risposta sta tutta in un pacchetto (niente bit MI) e
// se la tessera chiude con 90 00. Tutto il resto è un fallimento, senza
// distinzioni: a chi chiama interessa solo se può fidarsi dei dati.
bool Ntag424Pn532I2C::apdu_(const std::vector<uint8_t> &comando, std::vector<uint8_t> &risposta) {
  std::vector<uint8_t> frame = {pn532::PN532_COMMAND_INDATAEXCHANGE, 0x01};
  frame.insert(frame.end(), comando.begin(), comando.end());
  if (!this->write_command_(frame))
    return false;

  std::vector<uint8_t> dati;
  if (!this->read_response(pn532::PN532_COMMAND_INDATAEXCHANGE, dati))
    return false;

  // [stato del PN532] [dati della tessera…] [SW1] [SW2]
  if (dati.size() < 3 || dati[0] != 0x00)
    return false;
  if (dati[dati.size() - 2] != 0x90 || dati[dati.size() - 1] != 0x00)
    return false;

  risposta.assign(dati.begin() + 1, dati.end() - 2);
  return true;
}

// Il link scritto nella tessera, senza il prefisso (https://…). È ciò che la
// tessera produce a ogni lettura quando l'SDM è acceso: UID e contatore
// cifrati, più la firma, nel punto in cui erano gli zeri segnaposto.
bool Ntag424Pn532I2C::leggi_link_(std::string &link) {
  std::vector<uint8_t> risposta;
  if (!this->apdu_(SELEZIONA_APPLICAZIONE, risposta))
    return false;
  if (!this->apdu_(SELEZIONA_FILE_NDEF, risposta))
    return false;

  // I primi due byte del file sono la lunghezza del messaggio NDEF.
  if (!this->apdu_({0x00, 0xB0, 0x00, 0x00, 0x02}, risposta) || risposta.size() != 2)
    return false;
  uint16_t lunghezza = (uint16_t(risposta[0]) << 8) | risposta[1];
  if (lunghezza < 6 || lunghezza > MASSIMO_NDEF)
    return false;

  std::vector<uint8_t> ndef;
  if (!this->apdu_({0x00, 0xB0, 0x00, 0x02, uint8_t(lunghezza)}, ndef) || ndef.size() != lunghezza)
    return false;

  // Un solo record, breve, di tipo URI: MB e ME accesi, SR acceso, nessun ID,
  // TNF «well-known», tipo «U». È l'unica forma che produce la configurazione
  // SDM di questo impianto; qualunque altra cosa non si prova a interpretare.
  if ((ndef[0] & 0xF8) != 0xD0 || (ndef[0] & 0x07) != 0x01)
    return false;
  if (ndef[1] != 1 || ndef[3] != 'U')
    return false;
  uint8_t lunghezza_dati = ndef[2];
  if (lunghezza_dati < 2 || 4U + lunghezza_dati != ndef.size())
    return false;

  // ndef[4] è il codice del prefisso: non serve, conta la parte dopo.
  link.clear();
  for (size_t i = 5; i < ndef.size(); i++) {
    uint8_t c = ndef[i];
    if (c < 0x21 || c > 0x7E)
      return false;
    link.push_back(char(c));
  }
  return true;
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
