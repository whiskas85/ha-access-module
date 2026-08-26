# Custom component ESPHome per Grow R503 - UpChar / DownChar

Previsto, non ancora implementato (SPEC.md 12).

Export/import dei template biometrici, per un enrollment unico riutilizzabile
su piu varchi.

**Attenzione:** i template biometrici non vanno mai in `/config` versionato, in
attributi di entita, in `input_text`, ne in log a livello DEBUG. Destinazione
prevista: `/share/fingerprints/` cifrata ed esclusa dai backup.
