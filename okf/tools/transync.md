---
type: CLI Tool
title: transync
description: Sync bank transaction CSV exports into a history CSV without duplicates (YAML; banks dict by filename glob).
resource: file:///M:/LCode/doctools/transync.py
tags: [cli, csv, bank, sync]
timestamp: 2026-08-09T13:00:00Z
---

# Usage

```bash
python transync.py -c _GTNotes/transync.yaml -n
python transync.py -c _GTNotes/transync.yaml -n -v
python transync.py -c _GTNotes/transync.yaml -n -df -dh
python transync.py -c _GTNotes/transync.yaml --list-banks
```

| Flag | Meaning |
|------|---------|
| `-c` / `--config` | YAML config file (required) |
| `-n` / `--dry-run` | Report new vs duplicate; do not write history |
| `-df` / `--dup-file` `[FILE]` | Append-vs-history duplicates (default `<stem>_appdups.csv`) |
| `-dh` / `--history-dup-file` `[FILE]` | History-only duplicates (default `<stem>_hist_dups.csv`) |
| `-v` / `--verbose` | Preview dedupe-key fields for new rows |
| `--list-banks` | List `banks` keys + globs from the config |

`-df` / YAML `appdups`: history schema + **`DupSrc`** (`H` or append stem). Each skipped txn is a pair.

`-dh` / YAML `hist_dups`: fingerprints inside history only; every row has `DupSrc=H`.

# Config shape

```yaml
history: path/to/history.csv
append_dir: path/to/inbox
dedupe_keys: [AccountNumber, TransDate, Amount, Description]
auto_id: Id
encoding: utf-8-sig

appdups: true      # or a path; default <history_stem>_appdups.csv
hist_dups: true    # or a path; default <history_stem>_hist_dups.csv

banks:
  bofa_87:
    glob: "bofa_87*.csv"
    format: bofa
    account_number: "430187"
    account_type: CK
    column_map:
      TransDate: Date
      Amount: Amount
      Description: Description
```

CLI `-df` / `-dh` override YAML when passed.

# Formats

| `format` | Behavior |
|----------|----------|
| `generic` | First row is header |
| `bofa` | BoA checking (skip preamble) |
| `bofa_cc` | BoA credit-card export |

# Related

[csvdatclean](/tools/csvdatclean.md), [xlstool](/tools/xlstool.md)
