# AlphaForge Professional Quant Research Dossier

> **v0.28** — Research standardını akademik/profesyonel financial ML literatürüne göre yeniden tanımlama.
>
> Amaç: "Config değiştirerek puan artırma" devri bitti. Bundan sonra her değişiklik
> hipotez + kanıt + baseline karşılaştırması gerektirir.

---

## İçindekiler

1. [Cost-Aware Crypto ML Trading](#1-cost-aware-crypto-ml-trading)
2. [Backtest Overfitting / PBO / DSR / MHT](#2-backtest-overfitting--pbo--dsr--mht)
3. [Alpha Mining / Factor Discovery](#3-alpha-mining--factor-discovery)
4. [LOB / Microstructure](#4-lob--microstructure)
5. [Architecture / Handoff — AlphaForge → V7](#5-architecture--handoff--alphaforge--v7)
6. [Baseline Standards](#6-baseline-standards)
7. [Validator Hardening Rules (from literature)](#7-validator-hardening-rules-from-literature)
8. [Immediate Action Items](#8-immediate-action-items)

---

## 1. Cost-Aware Crypto ML Trading

### Kaynak: "Machine Learning-Based Bitcoin Trading Under Transaction Costs" (arXiv:2606.00060)

**Claim:**
XGBoost/LSTM/iTransformer modelleri BTC-USDT hourly veride forecast üretebiliyor, ancak
**transaction cost sonrası naive sign-based stratejiler başarısız oluyor.** Kârı geri getiren
şey daha iyi model değil, **cost-aware execution filter**.

**Dataset:**
- ~70,000 hourly BTC-USDT observation (2018–2026)
- 27-fold walk-forward protocol
- 10 bps transaction cost

**Key Findings:**

| Finding | Implication |
|---------|------------|
| "Naive sign-based strategies fail once transaction costs of ten basis points are imposed" | Basit yön tahmini ile trade açmak maliyetlerden sonra anlamsız |
| "Cost-aware filter sharply reduces turnover and restores profitability in selected configurations" | **Forecast magnitude thresholding** çalışıyor |
| "The main obstacle is not weak predictability, but how forecasts are converted into trades" | **Forecast → trade conversion** asıl Ar-Ge alanı |

**AlphaForge Implication:**
- `CONFIDENCE_THRESHOLD = 0.55` yeterli değil. Confidence **tek başına** edge büyüklüğünü ölçmez.
- Forecast magnitude + cost threshold birleşimi gerekli.
- Label üretiminde R-multiple'ın yanında **expected_net_R / cost_ratio** filtresi olmalı.
- Her trade kararı: `if expected_net_R > cost_per_trade_R: trade, else: NO_TRADE`

**Validator Kuralı:**
```
if cost_aware_filter_not_implemented:
  economic_score hard cap = 20
```

---

## 2. Backtest Overfitting / PBO / DSR / MHT

### Kaynak: Bailey & López de Prado — "The Probability of Backtest Overfitting" (SSRN 2326253)

**Claim:**
Çok sayıda backtest denemesi yapıldığında en iyi görünen sonuç büyük olasılıkla
**şans eseri overfit** olabilir. PBO (Probability of Backtest Overfitting) bunu
CSCV (Combinatorially Symmetric Cross-Validation) ile ölçer.

**Key Concept — CSCV:**
- Veriyi 2N parçaya böl
- Tüm kombinasyonları (N choose K) train/test olarak dene
- En iyi modelin test setinde ilk N/2'de mi yoksa son N/2'de mi olduğuna bak
- PBO = en iyi modelin şans eseri seçilme olasılığı

**Thresholds:**
- PBO < 0.50: düşük overfit riski
- PBO > 0.50: yüksek overfit riski (model şans eseri iyi görünüyor)

**AlphaForge Implication:**
- Walk-forward validation tek başına yeterli değil
- **CSCV veya benzeri kombinatoryal cross-validation** PBO hesabı için şart
- PBO NOT_RUN ise hiçbir alpha iddiası geçerli değil
- Trial ledger (kaç deneme yapıldı) PBO hesabına girmeli

### Kaynak: López de Prado — "The Deflated Sharpe Ratio" (SSRN 2460551)

**Claim:**
Klasik Sharpe ratio, multiple testing ve non-normal return dağılımı yüzünden şişer.
DSR bunu düzeltir.

**Formula:**
```
DSR = Sharpe ratio'in, deneme sayısı ve return skewness'ine göre düzeltilmiş hali.
```

**Threshold:**
- DSR > 0: modelin gerçekten edge'i olma ihtimali yüksek
- DSR < 0: Sharpe multiple testing artifact'ı olabilir

**AlphaForge Implication:**
- `net_sharpe` tek başına raporlanmamalı
- **Deflated Sharpe** yanında zorunlu olmalı
- Özellikle Optuna gibi hyperparameter search yapıldığında DSR kritik

### Kaynak: Harvey, Liu & Zhu — "… and the Cross-Section of Expected Returns" (OUP / RFS 2016)

**Claim:**
Yüzlerce faktör denenmiş bir ortamda klasik t-stat > 2.0 eşiği yetersiz.
**Yeni faktörler için t-stat > 3.0** gibi daha sert bir eşik gerekli.

**AlphaForge Implication:**
- Her denenen feature ailesi / model konfigürasyonu "trial" olarak sayılmalı
- Başarı eşiği deneme sayısıyla birlikte yükselmeli
- **Trial ledger** zorunlu: her run'da kaç hiperparametre / feature set / model denendiği kaydedilmeli

### Kaynak: QuantConnect Research Guide

**Method:**
- Walk-forward optimization + paper trading + multiple market/asset class testing
- "Her backtest fikri biraz daha overfit'e yaklaştırır"
- Backtest sayısı ve fikir seçimi kontrol edilmeli

**AlphaForge Kuralı:**
```
Trial ledger'i yoksa run sonucu güvenilmez.
Her config değişikliği = hipotez + fail kriteri gerektirir.
```

---

## 3. Alpha Mining / Factor Discovery

### Kaynak: WorldQuant — "101 Formulaic Alphas" (arXiv:1601.00991)

**Structure:**
- 101 adet formül bazlı alpha sinyali (matematik + kod olarak ifade edilmiş)
- Ortalama holding period: **0.6–6.4 gün**
- Average pairwise correlation: **%15.9** (çok düşük)
- Return-volatility korelasyonu yüksek, turnover-alpha korelasyonu düşük

**Professional Lesson:**
Amaç tek bir büyük model değil, **düşük korelasyonlu, çeşitlendirilmiş alpha havuzu** oluşturmak.

**AlphaForge Implication:**
- AlphaForge sadece XGBoost classifier değil, **alpha factor mining platformu** olmalı
- Feature family = potansiyel alpha ailesi
- Her aile için: **IC (Information Coefficient), dönüşümlülük, diğer ailelerle korelasyon**
- Amaç: en iyi tek model değil, **düşük korelasyonlu alpha family portföyü**

### Kaynak: AutoAlpha — "Hierarchical Evolutionary Algorithm for Alpha Factors" (arXiv:2002.08245)

**Approach:**
- Evrimsel algoritma ile formül bazlı alpha keşfi
- Hiyerarşik yapı + PCA-QD (Quality Diversity) ile arama uzayının verimli taranması
- Keşfedilen alphalar ensemble learning-to-rank ile portföye dönüşüyor

**Key Insight:**
- İnsan eliyle factor keşfi yavaş ve sübjektif
- Sistematik evolutionary search daha hızlı ve daha geniş alpha uzayı tarar
- Formulaic alpha'lar black-box modellere göre **yorumlanabilir ve overfit kontrolü daha kolay**

**AlphaForge Implication:**
- Feature family ablation = manuel alpha mining'in ilk adımı
- Uzun vadede: **otomatik alpha factor generation** (formül bazlı, evolutionary)
- Feature family'ler arası korelasyon matrisi zorunlu

---

## 4. LOB / Microstructure

### Kaynak: DeepLOB (arXiv:1808.03668)

**Architecture:**
- CNN + LSTM: LOB'un spatial yapısını CNN, temporal bağımlılıkları LSTM ile modeller
- **Cross-instrument transferability**: bir enstrümanda öğrenilen özellikler diğerine geçiyor
- Sensitivity analysis ile hangi LOB seviyelerinin önemli olduğu belirlenebiliyor

**Data Requirement:**
- Gerçek LOB verisi (level-2/level-3 order book)
- Yüksek frekans (tick data veya çok kısa bar)
- 1 yıl LSE verisi yeterli olabiliyor

### Kaynak: HLOB — "Information Persistence in LOB" (arXiv:2405.18938)

**Critical Finding:**
LOB bilgisinin **spatial structure**'ı artan forecast horizon ile bozuluyor.

| Horizon | LOB Signal |
|---------|-----------|
| Çok kısa (saniye/dakika) | Zengin, yapısal |
| Kısa (15-60 dk) | Azalıyor |
| Orta-uzun (4h+) | Çok zayıf |

**AlphaForge Implication:**
- SWING (4h) ve üzerinde **orderbook feature'larının anlamlı olması beklenmez**
- SCALP (1h) sınırda — test edilmeli
- AGGRESSIVE_SCALP (15m) en uygun LOB adayı
- **Synthetic random-walk üzerinde LOB feature test etmek bilimsel olarak geçersiz**

**Validator Kuralı:**
```
if mode == SWING and orderbook_features_active:
  behavior_score -= 15 penalty (uygun horizon değil)
```

---

## 5. Architecture / Handoff — AlphaForge → V7

### Kaynak: FinRL-X (arXiv:2603.21330)

**Core Architecture:**
```
Data Layer → Strategy Layer → Backtesting Layer → Execution Layer
                |
           wₜ (target weight vector) — tek interface
```

**4 Strategy Module:**
1. **Stock Selection (𝒮)** — aday havuzu
2. **Portfolio Allocation (𝒜)** — base weights
3. **Timing Adjustment (𝒯)** — zamanlama sinyali
4. **Risk Overlay (ℛ)** — volatilite skalası

**Key Principle:**
> "Interface consistency across environments matters more than model sophistication."

Research ve execution **aynı weight vector interface'ini** kullanır. Strateji kodu değişmeden
backtest → paper trading → live execution'a geçer.

**2 Systematic Gap:**
1. **Backtest → Paper**: oversimplified execution, unrealistic costs, no market impact
2. **Paper → Live**: fill uncertainty, latency, API differences, real capital constraints

**AlphaForge → V7 Handoff Implication:**

Mevcut handoff (model.pkl + threshold) yetersiz. FinRL-X prensibine göre handoff şunları içermeli:

```yaml
handoff_package:
  model: model.pkl (veya model binary)
  feature_schema_hash: string
  expected_net_R_per_trade: float
  confidence_threshold: float
  cost_threshold_R: float
  allowed_regimes: list[str]
  max_position_size_R: float
  kill_conditions:
    - max_drawdown_R: float
    - consecutive_losses: int
    - max_trades_per_day: int
  feature_importance_top_k: list[str]
  validation_passport:
    - fold_pass_ratio: float
    - net_sharpe: float
    - pbo_risk: str
    - cost_stress_result: str
```

---

## 6. Baseline Standards

### Every model must beat these baselines

Literatür ve profesyonel uygulamadan çıkarılan zorunlu baseline'lar:

| Baseline | Why | Measurement |
|----------|-----|-------------|
| **NO_TRADE** | Trade açmamanın getirisini geçmeli | active_return > 0 (net_R bazında) |
| **RANDOM_ACTION** | Rastgele trade'den iyi olmalı | net_sharpe_random < net_sharpe_model |
| **ALWAYS_LONG** | Sürekli long'dan iyi olmalı | net_sharpe_long < net_sharpe_model |
| **ALWAYS_SHORT** | Sürekli short'tan iyi olmalı | net_sharpe_short < net_sharpe_model |
| **BUY_AND_HOLD** | Passif hold'dan iyi olmalı | active_return > hold_return (net_R) |
| **NAIVE_MOMENTUM** | Basit momentumdan iyi olmalı | net_sharpe > momentum_net_sharpe |
| **COST_ONLY_NULL** | Maliyetleri karşılamalı | net_expectancy > cost_per_trade_R |

### Validator Kuralları:

```
if active_not_beats_no_trade:
  level_assessment = NOT_ALPHA_CANDIDATE_YET (override)

if active_not_beats_random:
  level_assessment = NOT_ALPHA_CANDIDATE_YET (override)

if always_long_or_short_beats_model:
  level_assessment = NOT_ALPHA_CANDIDATE_YET (override)
```

---

## 7. Validator Hardening Rules (from literature)

Aşağıdaki kurallar doğrudan okunan kaynaklardan çıkarılmıştır ve
validator'a eklenmelidir:

| # | Kural | Kaynak | Priority |
|---|-------|--------|----------|
| V1 | **Cost-aware filter yoksa** economic_score cap 20 | arXiv:2606.00060 | P0 |
| V2 | **PBO NOT_RUN ise** validation_score cap, alpha candidate olamaz | SSRN 2326253 | P0 |
| V3 | **DSR NOT_RUN ise** net_sharpe raporlanamaz, güvenilmez | SSRN 2460551 | P0 |
| V4 | **Trial ledger yoksa** hiçbir alpha claim geçerli değil | Harvey-Liu-Zhu, QuantConnect | P0 |
| V5 | **Fold_pass_ratio = 0 ise** max proximity 25 (daha sert) | Multiple sources | P0 |
| V6 | **LOB feature'ları SWING'de aktifse** behavior penalty | HLOB, DeepLOB | P1 |
| V7 | **Synthetic data + yüksek PF/Sharpe** anomaly flag zorunlu | Literature consensus | P0 |
| V8 | **Baseline library yoksa** level max RESEARCH_CANDIDATE | Industry standard | P0 |
| V9 | **Confidence bucket calibration yoksa** davranış skoru cap 30 | arXiv:2606.00060 | P1 |
| V10 | **Feature family ablation yoksa** proximity max 40 | WorldQuant, AutoAlpha | P1 |

---

## 8. Immediate Action Items

### P0 — Hemen yapılması gerekenler (bu hafta)

```yaml
- id: V2-V3-V4
  action: PBO/DSR/Trial Ledger validator gates
  files:
    - alphaforge/src/alphaforge/validation/target_validator.py
    - alphaforge/src/alphaforge/reports/mht.py
  acceptance:
    - PBO NOT_RUN ise validation_score <= 25
    - DSR not computed ise net_sharpe flagged
    - Trial count pipeline evidence'a eklenmeli

- id: V8
  action: Baseline library
  files:
    - alphaforge/src/alphaforge/validation/baselines.py
  acceptance:
    - NO_TRADE / RANDOM / ALWAYS_LONG / ALWAYS_SHORT baseline'ları
    - Her baseline için net_R, Sharpe, expectancy
    - Validator'da "beats_baseline" kontrolü

- id: V1
  action: Cost-aware filter indicator
  files:
    - alphaforge/src/alphaforge/train.py
    - alphaforge/src/alphaforge/validation/target_validator.py
  acceptance:
    - Model cost-aware filter kullanıyorsa flag
    - Kullanmıyorsa economic_score cap 20

- id: dossier
  action: Paper reading matrix
  files:
    - reports/research/paper_reading_matrix.yaml
  acceptance:
    - 11 kaynağın tümü analiz edilmiş
    - Her implication doğrudan validator/main dile değişikliği
```

### P1 — Sıradaki

```yaml
- id: V9
  action: Confidence bucket calibration report
  files:
    - alphaforge/src/alphaforge/reports/calibration.py
  acceptance:
    - 0.55-0.60 / 0.60-0.65 / 0.65+ bucket'ları
    - Her bucket için realized net_R
    - Eğer artan confidence artan net_R getirmiyorsa flag

- id: V6
  action: LOB feature horizon penalty
  files:
    - alphaforge/src/alphaforge/validation/target_validator.py
  acceptance:
    - SWING mode + orderbook features = behavior penalty

- id: V10
  action: Feature family ablation integration
  files:
    - alphaforge/src/alphaforge/features/ablation.py
  acceptance:
    - Her family için net_PF / net_expectancy raporu
    - Hangi family'lerin pozitif katkı verdiği
```

---

## Kaynakça

| # | Kaynak | Tür | Odak |
|---|--------|-----|------|
| 1 | [ML-Based Bitcoin Trading Under Transaction Costs](https://arxiv.org/abs/2606.00060) | Paper | Cost-aware crypto trading |
| 2 | [Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) | Paper | PBO / CSCV |
| 3 | [Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2460551_code87814.pdf?abstractid=2460551) | Paper | DSR / multiple testing |
| 4 | [Harvey-Liu-Zhu: t-stat > 3.0](https://academic.oup.com/rfs/article/29/1/5/1843824) | Paper | Factor significance |
| 5 | [QuantConnect Research Guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide) | Industry | Research workflow |
| 6 | [101 Formulaic Alphas](https://arxiv.org/abs/1601.00991) | Paper | Alpha mining |
| 7 | [AutoAlpha](https://arxiv.org/abs/2002.08245) | Paper | Evolutionary alpha discovery |
| 8 | [DeepLOB](https://arxiv.org/abs/1808.03668) | Paper | LOB modeling |
| 9 | [BDLOB](https://arxiv.org/abs/1811.10041) | Paper | Bayesian LOB + uncertainty |
| 10 | [HLOB](https://arxiv.org/abs/2405.18938) | Paper | LOB information persistence |
| 11 | [FinRL-X](https://arxiv.org/html/2603.21330v1) | Paper | Research-live architecture |

---

> **Slogan:**
>
> *No config change without hypothesis.*
> *No hypothesis without evidence.*
> *No evidence without real-data validation.*
> *No alpha claim without baseline defeat.*
