#pragma once

// PN532 su I²C che, oltre all'UID, legge dalla tessera il messaggio firmato
// dell'NTAG 424 DNA (SDM, AN12196) e lo riferisce così com'è.
//
// Legge e riferisce, non verifica: la verifica sta in Home Assistant, dove
// stanno le chiavi (SPEC.md §2, §15). Qui dentro non c'è nessuna chiave e
// nessuna decisione — solo i comandi per chiedere alla tessera il suo link.

#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/components/i2c/i2c.h"
#include "esphome/components/pn532/pn532.h"

#include <string>
#include <vector>

namespace esphome::ntag424 {

// Una lettura: l'UID dell'anticollisione e, se la tessera lo produce, il link
// con il messaggio firmato. Vuoto per le tessere che non lo hanno (una MIFARE
// Classic, un'NTAG 424 senza SDM): per loro la lettura resta quella di sempre.
class LetturaTrigger : public Trigger<std::string, std::string> {
 public:
  void process(const std::string &uid, const std::string &sdm) { this->trigger(uid, sdm); }
};

// Il trasporto I²C è copiato da `pn532_i2c`, e non ereditato, per un motivo
// solo: lì la classe è `final`. Il nucleo PN532 invece è quello di ESPHome, e
// da lui si prendono comandi, polling e trigger `on_tag`.
class Ntag424Pn532I2C : public pn532::PN532, public i2c::I2CDevice {
 public:
  void loop() override;
  void dump_config() override;

  void register_lettura_trigger(LetturaTrigger *trigger) { this->triggers_lettura_.push_back(trigger); }

 protected:
  bool is_read_ready() override;
  bool write_data(const std::vector<uint8_t> &data) override;
  bool read_data(std::vector<uint8_t> &data, uint8_t len) override;
  bool read_response(uint8_t command, std::vector<uint8_t> &data) override;
  uint8_t read_response_length_();

  void tessera_andata_via_();
  bool apdu_(const std::vector<uint8_t> &comando, std::vector<uint8_t> &risposta);
  bool leggi_link_(std::string &link);

  std::vector<LetturaTrigger *> triggers_lettura_;
};

}  // namespace esphome::ntag424
