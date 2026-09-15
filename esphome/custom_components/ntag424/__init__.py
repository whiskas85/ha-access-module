"""PN532 su I²C che riferisce anche il messaggio firmato dell'NTAG 424 DNA.

Sostituisce `pn532_i2c` nel nodo: stesso chip, stesso bus, stesse opzioni, e
in più il trigger `on_lettura` con due variabili:

- `uid`: l'UID letto in anticollisione, come la `x` di `on_tag`;
- `sdm`: il link che la tessera produce con l'SDM acceso, vuoto se non c'è.

La verifica non si fa qui: si fa in Home Assistant, dove stanno le chiavi.
"""

from esphome import automation
import esphome.codegen as cg
from esphome.components import i2c, pn532
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_TRIGGER_ID

AUTO_LOAD = ["pn532"]
DEPENDENCIES = ["i2c"]

CONF_ON_LETTURA = "on_lettura"
CONF_ON_LETTURA_INCOMPLETA = "on_lettura_incompleta"

ntag424_ns = cg.esphome_ns.namespace("ntag424")
Ntag424Pn532I2C = ntag424_ns.class_("Ntag424Pn532I2C", pn532.PN532, i2c.I2CDevice)
LetturaTrigger = ntag424_ns.class_(
    "LetturaTrigger", automation.Trigger.template(cg.std_string, cg.std_string)
)
LetturaIncompletaTrigger = ntag424_ns.class_(
    "LetturaIncompletaTrigger", automation.Trigger.template(cg.std_string)
)

CONFIG_SCHEMA = (
    pn532.PN532_SCHEMA.extend(
        {
            cv.GenerateID(): cv.declare_id(Ntag424Pn532I2C),
            cv.Optional(CONF_ON_LETTURA): automation.validate_automation(
                {
                    cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(LetturaTrigger),
                }
            ),
            cv.Optional(CONF_ON_LETTURA_INCOMPLETA): automation.validate_automation(
                {
                    cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(
                        LetturaIncompletaTrigger
                    ),
                }
            ),
        }
    )
    .extend(i2c.i2c_device_schema(0x24))
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await pn532.setup_pn532(var, config)
    await i2c.register_i2c_device(var, config)

    for conf in config.get(CONF_ON_LETTURA, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID])
        cg.add(var.register_lettura_trigger(trigger))
        await automation.build_automation(
            trigger, [(cg.std_string, "uid"), (cg.std_string, "sdm")], conf
        )

    for conf in config.get(CONF_ON_LETTURA_INCOMPLETA, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID])
        cg.add(var.register_incompleta_trigger(trigger))
        await automation.build_automation(trigger, [(cg.std_string, "uid")], conf)
