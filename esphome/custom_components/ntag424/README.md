# Custom component ESPHome `ntag424`

PN532 su I²C che, oltre all'UID, legge dalla tessera NTAG 424 DNA il link
con il messaggio firmato (SDM) e lo riferisce a Home Assistant. Progetto in
SPEC.md §15.

**Legge e riferisce, non verifica.** Sul nodo non c'è nessuna chiave: la
verifica della firma e il controllo del contatore stanno in Home Assistant
(`sdm.py`, `ntag424.py`), come chiede SPEC.md §2.

## Cosa fa a ogni lettura

1. Anticollisione, come `pn532_i2c`: si ricava l'UID.
2. Se la tessera parla ISO 14443-4 (SAK bit 6), le chiede il file NDEF con i
   comandi di un telefono: selezione dell'applicazione `D2760000850101`,
   selezione del file `E104`, lettura della lunghezza e poi del messaggio.
3. Se il messaggio è un solo record URI, ne riferisce il testo con
   `on_lettura`. Se la tessera risponde a tutto ma un messaggio di quella
   forma non ce l'ha, il link resta vuoto: è una lettura completa del solo
   UID, cioè debole.
4. Se invece la tessera **smette di rispondere** a metà (errore di radio,
   nessuna risposta), non è una lettura: parte `on_lettura_incompleta` con
   l'UID, non si riferisce niente, e la tessera si rilegge da capo al giro
   dopo se è ancora lì.

Una tessera si considera tolta solo dopo tre giri di fila senza vederla: il
PN532 ogni tanto ne perde una per un giro, e senza questa tolleranza la
rileggerebbe come nuova.

Per una MIFARE Classic non cambia niente rispetto a prima.

## Uso

Al posto di `pn532_i2c`:

```yaml
ntag424:
  update_interval: 500ms
  on_lettura:
    then:
      - logger.log:
          format: "Tessera %s, messaggio di %u caratteri"
          args: ['uid.c_str()', 'sdm.size()']
```

Il trasporto I²C è copiato da `pn532_i2c` di ESPHome 2026.8, non ereditato:
lì la classe è `final`. Il nucleo PN532 invece è quello di ESPHome.
