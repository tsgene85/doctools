---
type: CLI Tool
title: pdfdecrypt
description: Write an unencrypted copy of a password-protected PDF when the password is known.
resource: file:///M:/LCode/doctools/pdfdecrypt.py
tags: [cli, pdf, decrypt]
timestamp: 2026-07-13T16:00:00Z
---

# Usage

```bash
python pdfdecrypt.py -i locked.pdf -o unlocked.pdf -p SECRET
python pdfdecrypt.py -i locked.pdf -O -p SECRET
python pdftool.py decrypt -i locked.pdf -o unlocked.pdf -p SECRET
```

Password may also come from `PDF_PASSWORD` or an interactive prompt. Decrypt **before** accessing pages (pypdf requirement).

# Playbook

[Decrypt PDF](/playbooks/decrypt-pdf.md)
