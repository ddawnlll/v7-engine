## Problem

`.github/workflows/ci.yml`'daki multi-line pytest komutu backslash continuation kullanıyor ama YAML `|` block literal'de backslash + indent sorunu yüzünden shell doğru parse etmiyor. CI log'unda `ERROR: file or directory not found: --ignore=lib/tests/test_data_lake_downloader.py`.

Bunun sonucu:
- lib+integration+simulation testleri `collected 0 items` ile geçiyor (hicbir sey calismiyor)
- runtime/alphaforge/v7/policycritic testleri + gate check hic tetiklenmiyor
- CI failure dönse bile downstream job'lar suskun kaliyor

Main branch 24+ saattir kirmizi.

## Acceptance Criteria
- [ ] `.github/workflows/ci.yml` duzeltildi
- [ ] `gh run list --branch main`'de yesil run goruluyor
- [ ] lib+integration+simulation testleri gercekten calisiyor (collected > 0 items)
- [ ] runtime/alphaforge/v7/policycritic job'lari tetikleniyor ve geciyor
- [ ] Gate check (self-validator) calisiyor
