# Issue Closure Protocol

## Rule: NO CLOSURE WITHOUT EVIDENCE

Bir GitHub issue'yu kapatmadan önce **3 şart** zorunludur:

### 1. Git Commit
```bash
# Commit mesajı issue numarasını içermeli:
git commit -m "feat: #<num> <description>"
```

### 2. ACCP-YAML Report
```yaml
# reports/accp/issue-<num>.yaml dosyası oluşturulmalı
accp_version: "2.0.0"
result: "PASS" | "PASS_WITH_WARNINGS" | "FAIL"
evidence:
  - "test output"
  - "commit hash"
files_changed: [...]
```

### 3. Checklist Güncellemesi
- `v7/docs/roadmap.md` — lock status değiştiyse
- İlgili `ai_summary.md` — scope değiştiyse
- İlgili issue checklist'i — tüm maddeler tiklenmiş olmalı

## Enforcement

`PreToolUse` hook (`pre-close-guard.sh`) kapatma işlemini bloklar eğer:
- Son 1 saat içinde issue'yu referanslayan commit yoksa
- ACCP report yoksa

## Açık kalan issue'lar nasıl kapatılmaz

- "Kod yazıldı" demek yetmez → test geçmeli
- "Test geçti" demek yetmez → commit edilmeli
- "ACCP var" demek yetmez → roadmap güncellenmeli
