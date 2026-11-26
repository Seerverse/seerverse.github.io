# seerverse.github.io

Public audit and bug bounty record of 0xSeerBear, read daily from the public profiles on Sherlock, Code4rena, Cantina and HackenProof, plus the Immunefi profile. Immunefi blocks scripted reads, so its findings are kept by hand in `MANUAL_FINDINGS` in `scripts/update.py`. Payout amounts are not collected.

- `python3 scripts/update.py` rebuilds `data/profile.json` (standard library only).
- `.github/workflows/update.yml` runs it daily and commits the change.
- Preview: `python3 -m http.server 8000`, open http://localhost:8000.
