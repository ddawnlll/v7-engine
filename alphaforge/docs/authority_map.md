# AlphaForge Authority Map

**Purpose:** Map every computation to its single authoritative source, identify current violations, and provide a phased resolution plan.

**Authority principle:** *Every metric lives at the layer closest to its source data. No downstream layer recomputes what an upstream layer already computed.* (from [discovery_authority.md](discovery_authority.md))

**Status:** DRAFT — LOCKABLE_WITH_HOLDS

---

## 1. Authority Table

### Single-Source Truths

| Kavram | Authority (tek kaynak) | Dosya/Fonksiyon | Mevcut Durum |
|--------|----------------------|-----------------|--------------|
| **IC / RankIC / IC_IR** | AlphaForge — sinyal kalitesi ölçümü | `factors/evaluation.py::compute_cross_sectional_ic()` | ✅ Doğru yerde, birim test var |
| **Turnover** | AlphaForge — sinyal kararlılığı | `factors/evaluation.py::compute_turnover()` | ✅ Doğru yerde, birim test var |
| **Top-bottom spread** | AlphaForge — sinyal ayrışma gücü | `factors/evaluation.py::compute_top_bottom_spread()` | ⚠️ "net_return" etiketi yanıltıcı (bkz. İhlal #2) |
| **Forward returns** | AlphaForge — ham getiri hesaplaması | `factors/evaluation.py::compute_forward_returns()` | ✅ Doğru yerde |
| **Pass/fail (IC bazlı)** | AlphaForge — sinyal kalitesi eşiği | `factors/evaluation.py::evaluate_factor()` | ✅ Doğru yerde |
| **R-multiple (realized_r_gross/net)** | Simulation — ekonomik gerçeklik | `simulation/engine/engine.py::simulate()` | ✅ Doğru yerde |
| **Fee cost (R)** | Simulation — işlem maliyeti | `simulation/engine/costs.py::fee_cost_r()` | ✅ Doğru yerde |
| **Slippage cost (R)** | Simulation — kayma maliyeti | `simulation/engine/costs.py::slippage_cost_r()` | ✅ Doğru yerde |
| **Funding cost (R)** | Simulation — fonlama maliyeti | `simulation/engine/funding.py::funding_cost_r()` | ✅ Doğru yerde |
| **Total cost (R)** | Simulation — toplam maliyet | `simulation/engine/costs.py::total_cost_r()` | ✅ Doğru yerde |
| **Stop/target/exit logic** | Simulation — çıkış mantığı | `simulation/engine/exits.py::simulate_path()` | ✅ Doğru yerde |
| **NO_TRADE quality** | Simulation — işlem yapmama kalitesi | `simulation/engine/engine.py::_build_no_trade_outcome()` | ✅ Doğru yerde |
| **Rejim etiketi (uptrend/downtrend/range)** | AlphaForge — tek authority | `features/regime.py::classify_regime()` | ⚠️ features/ altında gömülü, ayrı authority olmalı |
| **Factor registry** | AlphaForge — factor listesi | `factors/factors.py::FACTOR_REGISTRY` | ⚠️ Mirror-pair audit mekanizması yok |
| **Sprint cost net_return** | AlphaForge (evaluation) + Simulation (costs) | `sprint/runner.py::_evaluate_single_factor()` | ⚠️ simulation'dan cost alıyor ama trade sayısını heuristic hesaplıyor |

### Mevcut "Gölge Sistemler" (Authority İhlali)

| Dosya | Ne Yapıyor | Neden İhlal | Ne Yapılmalı |
|-------|-----------|-------------|--------------|
| `factors/fast_simulator.py` | Numba-accelerated R simulation. Kendi `TOTAL_COST_RATE = 0.0012`, kendi ATR/stop/target/exit mantığı. | Simulation engine'in authority'sini çiğniyor — cost model, exit logic, path metrics'in hepsini yeniden yazıyor. | **Deprecated.** Şu an `simulation_adapter.py` dışında hiçbir yerden çağrılmıyor. |
| `factors/r_simulator.py` | Eski standalone R simulator. Kendi cost modeli var. | Aynı ihlal. Zaten `DEPRECATED` etiketi var. | Zaten deprecated, silinebilir. |
| `factors/simulation_adapter.py` | simulation'a köprü. İki yolu var: (1) `TrainingAdapter.run()` (doğru), (2) `HAS_FAST_SIM → fast_simulator` (yanlış). | `HAS_FAST_SIM` fallback'i fast_simulator'a düşüyor. | `HAS_FAST_SIM` yolu kapatılmalı, sadece `TrainingAdapter` yolu kalmalı. |

---

## 2. Mevcut Sprint Pipeline (Çalışan Akış)

```
CLI/script
  → sprint/runner.py::FactorSprintRunner.run()
    → evaluation.py::evaluate_factor()
      → compute_cross_sectional_ic()     ← ✅ IC/IC_IR
      → compute_top_bottom_spread()      ← ⚠️ "net" = gross × sign, cost yok
      → compute_turnover()               ← ✅
    → simulation.engine.costs            ← ✅ simulation'dan fee+slippage
    → kendi net_return = gross - heuristic_cost  ← ⚠️ trade sayısı = turnover × n_timestamps (tahmin, simulation değil)
  → leaderboard.py / eval_gate.py        ← raporlama
```

**Bu pipeline fast_simulator'ı, r_simulator'ı veya simulation_adapter'ı çağırmaz.** Bunlar "atıl/yedek" kod olarak durur.

---

## 3. Detaylı İhlal Analizi

### İhlal #1: `fast_simulator.py` — Simulation Gölge Sistemi

- **Dosya:** `factors/fast_simulator.py` (699 satır)
- **İhlal:** `simulation/` authority'sini çiğniyor: kendi `TOTAL_COST_RATE`, ATR, stop/target, exit mantığı
- **Etki:** Eğer `simulation_adapter.py` üzerinden çağrılırsa, gerçek `simulation.engine`'den farklı sonuç üretir
- **Kullanım durumu:** Şu an hiçbir aktif pipeline burayı çağırmıyor (sadece `simulation_adapter.py` import ediyor, o da çağrılmıyor)
- **Yapılacak:** Deprecate et, import zincirini kır, testler kalibrasyon için kalabilir

### İhlal #2: `evaluation.py` — "net_return" Yanıltıcı Etiket

- **Dosya:** `factors/evaluation.py` satır 286-288
  ```python
  gross_spread = valid_spread.sum()
  net_spread = gross_spread * spread_sign  # ← sadece işaret çevirimi!
  ```
- **İhlal:** `top_bottom_net_return` alanı "net" olarak etiketlenmiş ama gerçek cost/fee/slippage içermiyor — sadece direction-adjusted gross spread
- **Etki:** Sprint raporlarında `net_return` okuyan herkes yanıltılıyor. `gross == net` sürprizinin kaynağı.
- **Yapılacak:** Alan adı `top_bottom_direction_adjusted_spread` olarak değiştirilmeli veya en azından docstring/net notu eklenmeli

### İhlal #3: `sprint/runner.py` — Heuristic Trade Sayısı

- **Dosya:** `sprint/runner.py` satır 234-237
  ```python
  n_trades = max(int(turnover * n_timestamps), 1)  # ← tahmin!
  total_cost = cost_per_trade * n_trades
  ```
- **İhlal:** Gerçek simulation.engine.simulate() çağrılmıyor, trade sayısı heuristic hesaplanıyor
- **Etki:** `net_return` miktarı simulation motorunun üreteceğinden farklı
- **Yapılacak:** Sprint pipeline'ına simulation_adapter entegre edilmeli veya net_return'un "heuristic estimate" olduğu belgelenmeli

### İhlal #4: Factor Registry — Mirror-Pair Denetimi Yok

- **Dosya:** `factors/factors.py::FACTOR_REGISTRY`
- **İhlal:** 23 factor kayıtlı ama bağımsızlık/mirror-pair denetimi yok. Örn: `ret_4h_rank` (momentum) vs `reversal_4h_zscore` (reversal) aynı sinyalin iki yüzü olabilir.
- **Etki:** "Kaç bağımsız factor var?" sorusunun cevabı bilinmiyor. Gerçek sayı 23 değil, 12-14 olabilir.
- **Yapılacak:** cross-correlation audit fonksiyonu eklenmeli, FACTOR_REGISTRY'ye bağımsızlık metriği eklenmeli

### İhlal #5: Regim Sınıflandırıcı Gömülü

- **Dosya:** `features/regime.py::classify_regime()` (1003 satır)
- **İhlal:** Rejim etiketlemesi tüm sistem için ortak bir authority olmalı, ama `features/` paketi altında gömülü
- **Etki:** Başka bir modül farklı rejim etiketleri kullanırsa tutarsızlık çıkar
- **Yapılacak:** `regime/` adında ayrı bir authority modülüne taşınmalı

---

## 4. Geçmiş Karışıklıkların Kök Nedenleri

| Karışıklık | Kök Neden | İlgili İhlal |
|-----------|-----------|-------------|
| Üç farklı "en iyi factor" raporu | Her rapor farklı evaluation path'i kullandı (bazen fast_sim, bazen evaluation.py, bazen sprint runner) | #1, #3 |
| IC_IR değerleri rapportan rapora değişti | `evaluate_factor()`'daki cost filter threshold bazen uygulandı bazen uygulanmadı | #2 |
| "gross == net" sürprizi | `top_bottom_net_return` cost düşümü yapmıyor, sadece direction sign çarpıyor | #2 |
| Breakdown_n_low kârlılık tahmini değişiyor | Aynı factore farklı cost hesapları (fast_simulator vs simulation.engine.costs vs heuristic) uygulanıyor | #1, #3 |

---

## 5. Çözüm Planı (Phased)

### Aşama 1 — İzolasyon ve Dondurma (düşük risk, bugün yapılır)
- [x] Bu authority_map.md dokümanını yaz
- [ ] `fast_simulator.py` üstüne deprecation uyarısı koy
- [ ] `simulation_adapter.py`'daki `HAS_FAST_SIM` fallback'ini kapat, sadece TrainingAdapter yolu kalsın
- [ ] Aşama 1 sonrası: breakdown_n_low'u yeniden çalıştır, sayı değişti mi kontrol et

### Aşama 2 — Test ve Doğrulama (Aşama 1'den sonra, kritik)
- [ ] breakdown_n_low sprint'ini aynen tekrar çalıştır
- [ ] fast_simulator vs simulation.engine farkını ölç
- [ ] authority_map.md'yi gerçek sonuçlarla güncelle

### Aşama 3 — İsimlendirme ve Cost Entegrasyonu (Aşama 2'den sonra)
- [ ] `evaluation.py`'da `top_bottom_net_return` → `top_bottom_direction_adjusted_spread` olarak yeniden adlandır
- [ ] Veya: sprint runner'a simulation_adapter entegre et, gerçek simulation'dan net_return al
- [ ] Her değişiklikten sonra test et

### Aşama 4 — Rejim Authority'si (Aşama 3'ten sonra)
- [ ] `features/regime.py` → `regime/classifier.py` taşıması
- [ ] Tek import noktası (`regime/__init__.py`)
- [ ] Test et

### Aşama 5 — Factor Registry Audit (Aşama 4'ten sonra)
- [ ] FACTOR_REGISTRY'ye cross-correlation audit fonksiyonu
- [ ] Mirror-pair tespiti
- [ ] Bagımsız factor sayısını raporla
- [ ] Test et

---

## 6. Kullanım Kılavuzu

### Yeni bir factor eklerken:

1. Factor fonksiyonunu `factors/factors.py`'daki `FACTOR_REGISTRY`'ye ekle
2. Audit fonksiyonunu çalıştır: mevcut factor'lerle korelasyonu < 0.7 mi?
3. Sprint runner ile test et: `python -m alphaforge.sprint.runner ...`
4. Sonuç simulation.engine üzerinden gider, fast_simulator bypass edilir

### Mevcut bir raporu yorumlarken:

- `evaluation.py`'dan gelen `top_bottom_net_return` = **direction-adjusted spread, cost düşümü yok** (Aşama 3'e kadar)
- `sprint/runner.py`'dan gelen `net_return` = **heuristic cost estimate, simulation değil** (Aşama 3'e kadar)
- Gerçek `net R-multiple` için: `simulation.engine.engine.simulate()` çıktısındaki `realized_r_net`

---

## 7. Bağlantılı Dokümanlar

- [discovery_authority.md](discovery_authority.md) — AlphaForge yetki sınırları (LOCKED)
- [ai_summary.md](ai_summary.md) — AlphaForge thin hub
- [label_contract.md](label_contract.md) — SimulationOutput → Label dönüşümü
- [simulation/docs/ai_summary.md](../../simulation/docs/ai_summary.md) — Simulation authority
- [simulation/docs/cost_model.md](../../simulation/docs/cost_model.md) — Cost model detayı
- [simulation/docs/vision.md](../../simulation/docs/vision.md) — 10 economic truth prensibi
- [decision_log.md](decision_log.md) — Locked decisions
- [factors/fast_simulator.py](../src/alphaforge/factors/fast_simulator.py) — Gölge sistem (deprecated)
- [factors/simulation_adapter.py](../src/alphaforge/factors/simulation_adapter.py) — Simulation köprüsü (fix required)
- [factors/evaluation.py](../src/alphaforge/factors/evaluation.py) — IC/IC_IR authority
- [sprint/runner.py](../src/alphaforge/sprint/runner.py) — Sprint pipeline
