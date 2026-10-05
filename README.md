# Clue for Home Assistant

Unofficial Home Assistant integration for the [Clue](https://helloclue.com)
period tracker. It exposes the current cycle day, phase and upcoming period
as sensors, for your own cycle or for a partner's calendar shared through
Clue Connect.

Clue publishes no API. This integration relies on
[pyclue](https://github.com/GiowGiow/pyclue), a client built against the
endpoints the Clue app uses, which may change without notice. Not affiliated
with or endorsed by Clue or BioWink GmbH. Clue is a trademark of its owner.

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=GiowGiow&repository=hass-clue&category=integration)

Or add it by hand:

1. In HACS, open the menu → **Custom repositories**, and add
   `https://github.com/GiowGiow/hass-clue` with type **Integration**.
2. Search for **Clue** in HACS and download it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Clue**.

### Manual

1. Copy `custom_components/clue/` into your Home Assistant `config/custom_components/`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Clue**.

## Configuration

Sign in with your Clue email and password. The integration then lists the
calendars this account can read:

- its **own** cycle, when the account tracks one;
- each **active Clue Connect** link, labeled with the partner's name.

With a single calendar the choice is skipped. To track several, add the
integration once per calendar.

If Clue rejects the stored password, Home Assistant asks you to reauthenticate.

## Entities

All entities belong to one service device per calendar.

| Entity | Type | Example |
|---|---|---|
| Cycle day | sensor | `20` |
| Phase | sensor (enum) | `luteal` |
| Next period | sensor (date) | `2025-05-30` |
| Days until next period | sensor (d) | `9` |
| Last period start | sensor (date) | `2025-05-02` |
| Last period length | sensor (d) | `4` |
| Next ovulation | sensor (date) | `2025-06-13` |
| Period | binary sensor | `off` |
| Fertile window | binary sensor, with `window_start` / `window_end` | `off` |
| Ovulation day | binary sensor | `off` |
| Awaiting period confirmation | binary sensor, disabled by default | `off` |

Phase is one of `period`, `fertile`, `ovulation`, `pms`, `follicular`,
`luteal` or `unknown`. Clue marks only period, fertile and ovulation days;
`follicular` and `luteal` are inferred from Clue's predicted ovulation.

Data refreshes every hour and right after local midnight, so the cycle day
turns over on time.

## Privacy

Cycle data is intimate health data, often someone else's.

- No symptom-level data (feelings, sex life, medication…) is exposed; only
  the derived cycle state above.
- Home Assistant's recorder keeps entity history. To avoid a long-term local
  record, exclude the entities:

  ```yaml
  recorder:
    exclude:
      entity_globs:
        - sensor.partner_*
        - binary_sensor.partner_*
  ```

- Think twice before exposing these entities to voice assistants or shared
  dashboards.

## Development

The pyclue library is **vendored** in `custom_components/clue/pyclue/`. It is
not on PyPI, where the name `pyclue` belongs to an unrelated project, so the
integration ships a pinned copy and HACS installs both together.
`custom_components/clue/pyclue/VENDORED` records the tag and commit. To move
to a new release:

```bash
scripts/sync_pyclue.sh v0.2.0
```

Do not edit the vendored files; change pyclue and re-sync.

### Tests

Tests run against Home Assistant 2026.9.2 and need Python 3.14:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```

### Releases

HACS offers the GitHub releases as versions. Tag `vX.Y.Z` to match
`"version"` in `manifest.json`, then publish a release from the tag.

## License

MIT
