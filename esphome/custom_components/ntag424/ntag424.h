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

// La tessera si è vista, ma ha smesso di rispondere a metà: tolta troppo
// presto, appoggiata storta. Non è una lettura e a Home Assistant non si
// riferisce niente, perché non c'è niente di certo da riferire. Il nodo chiede
// solo di riappoggiarla — e lo decide da sé, senza sapere chi sia la tessera,
// quindi il segnale è uguale per qualunque tessera, censita o no.
class LetturaIncompletaTrigger : public Trigger<std::string> {
 public:
  void process(const std::string &uid) { this->trigger(uid); }
};

// Una tessera ISO 14443-4 è ferma sul lettore, in attesa dei comandi di Home
// Assistant: il tramite è aperto e la programmazione può cominciare.
class TesseraProntaTrigger : public Trigger<std::string> {
 public:
  void process(const std::string &uid) { this->trigger(uid); }
};

// Come è andato un comando: `RIFIUTATO` vuol dire che la tessera ha risposto,
// e ha detto di no; `INTERROTTO` che non ha risposto affatto.
enum class EsitoApdu : uint8_t { OK, RIFIUTATO, INTERROTTO };

// Come è andata la richiesta del link: `ASSENTE` vuol dire che la tessera ha
// risposto a tutto e un link SDM non ce l'ha; `INTERROTTO` che si è fermata.
enum class EsitoLink : uint8_t { LETTO, ASSENTE, INTERROTTO };

// Il trasporto I²C è copiato da `pn532_i2c`, e non ereditato, per un motivo
// solo: lì la classe è `final`. Il nucleo PN532 invece è quello di ESPHome, e
// da lui si prendono comandi, polling e trigger `on_tag`.
class Ntag424Pn532I2C : public pn532::PN532, public i2c::I2CDevice {
 public:
  void loop() override;
  void update() override;
  void dump_config() override;

  // ── tramite (SPEC.md §15, scelta «B») ──
  //
  // Con il tramite aperto, la prossima tessera ISO 14443-4 non viene letta:
  // resta ferma sul lettore e parla solo attraverso `scambia`, un comando
  // alla volta, con i byte decisi da Home Assistant. Il nodo non sa cosa
  // passa: niente chiavi, niente crittografia, niente decisioni.
  void set_tramite(bool attivo);
  // Un comando alla tessera trattenuta, in esadecimale; la risposta intera,
  // parola di stato compresa, in esadecimale. Vuota se non c'è una tessera
  // trattenuta o se non ha risposto — e allora la si rilascia.
  std::string scambia(const std::string &comando);
  void register_pronta_trigger(TesseraProntaTrigger *trigger) { this->triggers_pronta_.push_back(trigger); }

  void register_lettura_trigger(LetturaTrigger *trigger) { this->triggers_lettura_.push_back(trigger); }
  void register_incompleta_trigger(LetturaIncompletaTrigger *trigger) {
    this->triggers_incompleta_.push_back(trigger);
  }

 protected:
  bool is_read_ready() override;
  bool write_data(const std::vector<uint8_t> &data) override;
  bool read_data(std::vector<uint8_t> &data, uint8_t len) override;
  bool read_response(uint8_t command, std::vector<uint8_t> &data) override;
  uint8_t read_response_length_();

  void tessera_non_vista_();
  EsitoApdu apdu_(const std::vector<uint8_t> &comando, std::vector<uint8_t> &risposta);
  EsitoLink leggi_link_(std::string &link);

  std::vector<LetturaTrigger *> triggers_lettura_;
  std::vector<LetturaIncompletaTrigger *> triggers_incompleta_;
  std::vector<TesseraProntaTrigger *> triggers_pronta_;

  void rilascia_();
  bool tramite_{false};
  bool trattenuta_{false};
  uint32_t ultimo_scambio_{0};
  // Giri consecutivi in cui la tessera riferita non si è vista (vedi .cpp).
  uint8_t assenze_{0};
};

}  // namespace esphome::ntag424
