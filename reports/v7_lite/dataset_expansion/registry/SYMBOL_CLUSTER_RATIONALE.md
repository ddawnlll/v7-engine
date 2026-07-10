# Symbol Cluster Rationale

Generated: 2026-07-09T07:12:12.669086+00:00

## Overview

This document defines the symbol clustering strategy for V7-Lite specialist alpha discovery.
Clusters are designed to group symbols with similar market microstructure, liquidity, and
correlation properties — enabling cluster-specialist alpha discovery.

## Clusters

### MAJORS (P0_CORE)
- **Symbols:** BTCUSDT, ETHUSDT
- **Rationale:** Highest liquidity, lowest cost, benchmark assets. Every strategy must
  work here first. BTC dominance drives correlation structure across all crypto.

### HIGH_BETA_L1 (P0_CORE)
- **Symbols:** SOLUSDT, AVAXUSDT, NEARUSDT, DOTUSDT, ADAUSDT, OPUSDT, ARBUSDT
- **Rationale:** High-beta Layer 1 tokens that amplify BTC moves. Good for momentum
  and breakout strategies. SOLUSDT already shows Truth V6 specialist potential.

### EXCHANGE_INFRA (P0_CORE)
- **Symbols:** BNBUSDT, LINKUSDT
- **Rationale:** Exchange ecosystem tokens with utility-driven demand. BNB has
  unique burn mechanics; LINK has oracle network demand.

### OLD_ALT_MID (P1_EXPANSION)
- **Symbols:** XRPUSDT, LTCUSDT, BCHUSDT, ETCUSDT
- **Rationale:** Legacy altcoins with high retail participation. Different
  correlation structure than L1s. Good for mean-reversion.

### DEFI (P1_EXPANSION)
- **Symbols:** UNIUSDT, AAVEUSDT, MKRUSDT, LDOUSDT
- **Rationale:** DeFi protocol tokens correlated to TVL and protocol revenue.
  May have unique alpha from on-chain signals.

### MEME_RETAIL (P1_EXPANSION)
- **Symbols:** DOGEUSDT, SHIBUSDT, PEPEUSDT, FLOKIUSDT
- **Rationale:** Meme-driven retail tokens. High volatility, unique volume
  patterns. May require specialist strategies.

### LAYER2_SCALING (P1_EXPANSION)
- **Symbols:** OPUSDT, ARBUSDT, IMXUSDT
- **Rationale:** Layer 2 scaling tokens. Correlated to L1 usage but with
  unique fee-burn dynamics.

### INFRA_MID (P1_EXPANSION)
- **Symbols:** ATOMUSDT, KAVAUSDT, KSMUSDT, ALGOUSDT, ICPUSDT, HBARUSDT
- **Rationale:** Infrastructure tokens with different correlation profiles.
  May show regime-dependent behavior.

### DERIVATIVES_RICH (P0_CORE)
- **Symbols:** 19 symbols with funding_rate + open_interest data
- **Rationale:** These symbols have derivatives data enabling basis trading,
  funding rate strategies, and OI-based signals.

### AI_DATA (P2_OPTIONAL)
- **Symbols:** FETUSDT, RENDERUSDT, OCEANUSDT, WLDUSDT
- **Rationale:** AI/Data tokens — emerging narrative. Lower liquidity.

### GAMING_METAVERSE (P2_OPTIONAL)
- **Symbols:** AXSUSDT, SANDUSDT, MANAUSDT, GALAUSDT
- **Rationale:** Gaming/metaverse tokens — high beta to narrative.

### PRIVACY_MID (P2_OPTIONAL)
- **Symbols:** XMRUSDT, ZECUSDT
- **Rationale:** Privacy coins — unique regulatory risk profile.

## Cluster Intersection (VOLATILE_ALT)

Some symbols appear in multiple clusters:

| Symbol | Primary | Secondary |
|--------|---------|-----------|
| SOLUSDT | HIGH_BETA_L1 | VOLATILE_ALT |
| DOGEUSDT | MEME_RETAIL | VOLATILE_ALT |
| AVAXUSDT | HIGH_BETA_L1 | VOLATILE_ALT |
| NEARUSDT | HIGH_BETA_L1 | VOLATILE_ALT |
| PEPEUSDT | MEME_RETAIL | VOLATILE_ALT |

This overlap is intentional — volatile assets may need specialist strategies
that cross cluster boundaries.

## Priority Distribution

| Priority | Count | Description |
|----------|-------|-------------|
| P0_CORE | 14 | Must-have for any discovery |
| P1_EXPANSION | 19 | Required for cluster discovery |
| P2_OPTIONAL | 10 | Nice-to-have |
| P3_LATER | 20 | Future expansion |

## Availability

- **Available in current data:** 56 symbols
- **UNAVAILABLE_IN_CURRENT_DATA:** 7 symbols

Missing symbols that would complete clusters:
- SHIBUSDT (MEME_RETAIL) — not in data/raw or data_lake
- PEPEUSDT (MEME_RETAIL) — not in data/raw or data_lake
- FLOKIUSDT (MEME_RETAIL) — not in data/raw or data_lake
- FETUSDT (AI_DATA) — not in data/raw or data_lake
- RENDERUSDT (AI_DATA) — not in data/raw or data_lake
- OCEANUSDT (AI_DATA) — not in data/raw or data_lake
- WLDUSDT (AI_DATA) — not in data/raw or data_lake

## Specialist Discovery Strategy

1. **Cluster-MAJORS:** Test global strategies on BTC/ETH first
2. **Cluster-HIGH_BETA_L1:** Test momentum/breakout on SOL, AVAX, NEAR
3. **Cluster-DERIVATIVES_RICH:** Test funding rate / OI strategies
4. **Cluster-DEFI:** Test protocol-correlated strategies
5. **Cluster-MEME_RETAIL:** Test volatility breakout on meme tokens
6. **Cluster-OLD_ALT_MID:** Test mean-reversion on legacy alts
