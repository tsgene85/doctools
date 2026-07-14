---
type: Playbook
title: Decrypt a password-protected PDF
description: Produce an unencrypted PDF copy when you know the open password.
tags: [pdf, decrypt, playbook]
timestamp: 2026-07-13T16:00:00Z
---

# Steps

1. Activate `.venv`.
2. Run:

```bash
python pdfdecrypt.py -i locked.pdf -o unlocked.pdf -p 'YOUR_PASSWORD'
```

Or:

```bash
python pdftool.py decrypt -i locked.pdf -O -p 'YOUR_PASSWORD'
```

3. Open `unlocked.pdf` without a password prompt.

# Notes

- Wrong password → clear error; no file written.
- Tool uses **pypdf** (already a project dependency); no qpdf install required.
- See [pdfdecrypt](/tools/pdfdecrypt.md).
