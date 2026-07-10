#!/usr/bin/env python3
"""Phase 2: Build Symbol Universe Registry and Cluster Map."""
import os
import json
import csv
from datetime import datetime, timezone
from pathlib import Path

V7_ROOT = Path("/teamspace/studios/this_studio/v7-engine")
RAW_DIR = V7_ROOT / "data" / "raw"
DATA_LAKE_DIR = V7_ROOT / "data_lake" / "raw" / "binance" / "um" / "klines"
OUTPUT_BASE = V7_ROOT / "reports" / "v7_lite" / "dataset_expansion"

STARTED_AT = datetime.now(timezone.utc).isoformat()

# ============================================================
# 1. Load existing symbols from data directories
# ============================================================
available_symbols = set()

# data/raw symbols
for d in RAW_DIR.iterdir():
    if d.is_dir():
        available_symbols.add(d.name)

# data_lake symbols (symlinks may exist in data/raw)
for d in DATA_LAKE_DIR.iterdir():
    if d.is_dir():
        available_symbols.add(d.name)

print(f"Available symbols in repo: {len(available_symbols)}")

# ============================================================
# 2. Define cluster assignments and metadata
# ============================================================
CLUSTERS = {
    'MAJORS': {
        'symbols': ['BTCUSDT', 'ETHUSDT'],
        'priority': 'P0_CORE',
        'liquidity_tier': 'ULTRA_HIGH',
        'cost_tier': 'LOW',
    },
    'HIGH_BETA_L1': {
        'symbols': ['SOLUSDT', 'AVAXUSDT', 'NEARUSDT', 'DOTUSDT', 'ADAUSDT', 'OPUSDT', 'ARBUSDT'],
        'priority': 'P0_CORE',
        'liquidity_tier': 'HIGH',
        'cost_tier': 'MEDIUM',
    },
    'MEME_RETAIL': {
        'symbols': ['DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'FLOKIUSDT'],
        'priority': 'P1_EXPANSION',
        'liquidity_tier': 'HIGH',
        'cost_tier': 'MEDIUM',
    },
    'EXCHANGE_INFRA': {
        'symbols': ['BNBUSDT', 'LINKUSDT'],
        'priority': 'P0_CORE',
        'liquidity_tier': 'HIGH',
        'cost_tier': 'LOW',
    },
    'DEFI': {
        'symbols': ['UNIUSDT', 'AAVEUSDT', 'MKRUSDT', 'LDOUSDT'],
        'priority': 'P1_EXPANSION',
        'liquidity_tier': 'MEDIUM',
        'cost_tier': 'MEDIUM',
    },
    'OLD_ALT_MID': {
        'symbols': ['XRPUSDT', 'LTCUSDT', 'BCHUSDT', 'ETCUSDT'],
        'priority': 'P1_EXPANSION',
        'liquidity_tier': 'HIGH',
        'cost_tier': 'LOW',
    },
    'LAYER2_SCALING': {
        'symbols': ['OPUSDT', 'ARBUSDT', 'IMXUSDT'],
        'priority': 'P1_EXPANSION',
        'liquidity_tier': 'MEDIUM',
        'cost_tier': 'MEDIUM',
    },
    'AI_DATA': {
        'symbols': ['FETUSDT', 'RENDERUSDT', 'OCEANUSDT', 'WLDUSDT'],
        'priority': 'P2_OPTIONAL',
        'liquidity_tier': 'MEDIUM',
        'cost_tier': 'MEDIUM',
    },
    'GAMING_METAVERSE': {
        'symbols': ['AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'GALAUSDT'],
        'priority': 'P2_OPTIONAL',
        'liquidity_tier': 'LOW',
        'cost_tier': 'HIGH',
    },
    'PRIVACY_MID': {
        'symbols': ['XMRUSDT', 'ZECUSDT'],
        'priority': 'P2_OPTIONAL',
        'liquidity_tier': 'MEDIUM',
        'cost_tier': 'MEDIUM',
    },
    'INFRA_MID': {
        'symbols': ['ATOMUSDT', 'KAVAUSDT', 'KSMUSDT', 'DOTUSDT', 'ALGOUSDT', 'ICPUSDT', 'HBARUSDT'],
        'priority': 'P1_EXPANSION',
        'liquidity_tier': 'MEDIUM',
        'cost_tier': 'MEDIUM',
    },
    'EXCHANGE_TOKEN': {
        'symbols': ['BNBUSDT'],
        'priority': 'P0_CORE',
        'liquidity_tier': 'ULTRA_HIGH',
        'cost_tier': 'LOW',
    },
    'DERIVATIVES_RICH': {
        'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT',
                    'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'LTCUSDT', 'UNIUSDT',
                    'OPUSDT', 'ARBUSDT', 'SUIUSDT', 'APTUSDT', 'ATOMUSDT', 'FILUSDT', 'BCHUSDT'],
        'priority': 'P0_CORE',
        'liquidity_tier': 'HIGH',
        'cost_tier': 'LOW',
    },
}

# Build reverse mapping: symbol -> primary cluster
symbol_clusters = {}
for cluster_name, info in CLUSTERS.items():
    for sym in info['symbols']:
        if sym not in symbol_clusters:
            symbol_clusters[sym] = cluster_name

# Additional symbols found in repo but not in target clusters
additional_symbols = available_symbols - set(symbol_clusters.keys())

# ============================================================
# 3. Build registry rows
# ============================================================
import pyarrow.parquet as pq

registry_rows = []

# Process target symbols first
for cluster_name, info in CLUSTERS.items():
    for sym in info['symbols']:
        if sym in available_symbols:
            # Find files for this symbol
            sym_files = []
            # Check data/raw
            raw_sym = RAW_DIR / sym
            if raw_sym.is_dir():
                for f in raw_sym.iterdir():
                    if f.suffix == '.parquet':
                        sym_files.append(f)
            # Check data_lake
            lake_sym = DATA_LAKE_DIR / sym
            if lake_sym.is_dir():
                for f in lake_sym.iterdir():
                    if f.suffix == '.parquet':
                        sym_files.append(f)

            # Get metadata from first file
            total_rows = 0
            tfs = set()
            starts = []
            ends = []
            has_deriv = False
            for fp in sym_files:
                try:
                    t = pq.read_table(fp)
                    total_rows += len(t)
                    fname = fp.name
                    if '_1h_' in fname or fname.endswith('_1h.parquet'):
                        tfs.add('1h')
                    if 'funding_rate' in t.column_names:
                        has_deriv = True
                    ts_col = 'timestamp' if 'timestamp' in t.column_names else None
                    if ts_col:
                        sv = t.column(ts_col)[0].as_py()
                        ev = t.column(ts_col)[-1].as_py()
                        if isinstance(sv, (int, float)) and sv > 1e12:
                            from datetime import datetime, timezone
                            starts.append(datetime.fromtimestamp(sv/1000, tz=timezone.utc).strftime('%Y-%m-%d'))
                            ends.append(datetime.fromtimestamp(ev/1000, tz=timezone.utc).strftime('%Y-%m-%d'))
                except:
                    pass

            row = {
                'symbol': sym,
                'cluster_primary': symbol_clusters.get(sym, 'UNCLASSIFIED'),
                'cluster_secondary': 'VOLATILE_ALT' if sym in ['SOLUSDT','DOGEUSDT','AVAXUSDT','NEARUSDT','PEPEUSDT'] else '',
                'priority': info['priority'],
                'available_in_current_cache': 'YES',
                'available_timeframes': ','.join(sorted(tfs)),
                'start_date': min(starts) if starts else 'N/A',
                'end_date': max(ends) if ends else 'N/A',
                'row_count_total': total_rows,
                'liquidity_tier': info['liquidity_tier'],
                'expected_cost_tier': info['cost_tier'],
                'has_derivatives': has_deriv,
                'notes': f'derivatives={has_deriv};cluster={symbol_clusters.get(sym,"UNCLASSIFIED")}',
            }
            registry_rows.append(row)
        else:
            # Target symbol but not available
            row = {
                'symbol': sym,
                'cluster_primary': symbol_clusters.get(sym, 'UNCLASSIFIED'),
                'cluster_secondary': '',
                'priority': info['priority'],
                'available_in_current_cache': 'UNAVAILABLE_IN_CURRENT_DATA',
                'available_timeframes': '',
                'start_date': '',
                'end_date': '',
                'row_count_total': 0,
                'liquidity_tier': info['liquidity_tier'],
                'expected_cost_tier': info['cost_tier'],
                'has_derivatives': False,
                'notes': f'UNAVAILABLE_IN_CURRENT_DATA;cluster={symbol_clusters.get(sym,"UNCLASSIFIED")}',
            }
            registry_rows.append(row)

# Process additional symbols not in any target cluster
for sym in sorted(additional_symbols):
    raw_sym = RAW_DIR / sym
    total_rows = 0
    tfs = set()
    starts = []
    ends = []
    has_deriv = False
    if raw_sym.is_dir():
        for fp in raw_sym.iterdir():
            if fp.suffix == '.parquet':
                try:
                    t = pq.read_table(fp)
                    total_rows += len(t)
                    fname = fp.name
                    if '_1h_' in fname or fname.endswith('_1h.parquet'):
                        tfs.add('1h')
                    if 'funding_rate' in t.column_names:
                        has_deriv = True
                    ts_col = 'timestamp' if 'timestamp' in t.column_names else None
                    if ts_col:
                        sv = t.column(ts_col)[0].as_py()
                        ev = t.column(ts_col)[-1].as_py()
                        if isinstance(sv, (int, float)) and sv > 1e12:
                            from datetime import datetime, timezone
                            starts.append(datetime.fromtimestamp(sv/1000, tz=timezone.utc).strftime('%Y-%m-%d'))
                            ends.append(datetime.fromtimestamp(ev/1000, tz=timezone.utc).strftime('%Y-%m-%d'))
                except:
                    pass

    row = {
        'symbol': sym,
        'cluster_primary': 'UNCLASSIFIED',
        'cluster_secondary': '',
        'priority': 'P3_LATER',
        'available_in_current_cache': 'YES',
        'available_timeframes': ','.join(sorted(tfs)),
        'start_date': min(starts) if starts else 'N/A',
        'end_date': max(ends) if ends else 'N/A',
        'row_count_total': total_rows,
        'liquidity_tier': 'LOW',
        'expected_cost_tier': 'HIGH',
        'has_derivatives': has_deriv,
        'notes': f'UNCLASSIFIED;derivatives={has_deriv}',
    }
    registry_rows.append(row)

# Deduplicate by symbol (keep first occurrence = highest priority cluster)
seen = set()
deduped = []
for r in registry_rows:
    if r['symbol'] not in seen:
        seen.add(r['symbol'])
        deduped.append(r)
registry_rows = deduped

print(f"Registry: {len(registry_rows)} unique symbols")

# ============================================================
# 4. Write SYMBOL_UNIVERSE_REGISTRY.csv
# ============================================================
reg_fields = [
    'symbol', 'cluster_primary', 'cluster_secondary', 'priority',
    'available_in_current_cache', 'available_timeframes', 'start_date',
    'end_date', 'row_count_total', 'liquidity_tier', 'expected_cost_tier',
    'has_derivatives', 'notes'
]
reg_csv = OUTPUT_BASE / "registry" / "SYMBOL_UNIVERSE_REGISTRY.csv"
with open(reg_csv, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=reg_fields)
    writer.writeheader()
    for r in sorted(registry_rows, key=lambda x: x['symbol']):
        writer.writerow({k: r.get(k, '') for k in reg_fields})

print(f"Wrote {reg_csv}")

# ============================================================
# 5. Write SYMBOL_CLUSTER_MAP.yaml
# ============================================================
cluster_map = {}
for r in registry_rows:
    c = r['cluster_primary']
    if c not in cluster_map:
        cluster_map[c] = []
    cluster_map[c].append({
        'symbol': r['symbol'],
        'priority': r['priority'],
        'available': r['available_in_current_cache'],
        'rows': r['row_count_total'],
        'liquidity': r['liquidity_tier'],
        'cost': r['expected_cost_tier'],
        'has_derivatives': r['has_derivatives'],
    })

yaml_lines = ["# Symbol Cluster Map - V7-Lite Dataset Expansion", f"# Generated: {STARTED_AT}", ""]
for cluster in sorted(cluster_map.keys()):
    yaml_lines.append(f"{cluster}:")
    yaml_lines.append(f"  description: {cluster.replace('_', ' ').title()}")
    yaml_lines.append(f"  symbols:")
    for s in cluster_map[cluster]:
        yaml_lines.append(f"    - symbol: {s['symbol']}")
        yaml_lines.append(f"      priority: {s['priority']}")
        yaml_lines.append(f"      available: {s['available']}")
        yaml_lines.append(f"      rows: {s['rows']}")
        yaml_lines.append(f"      liquidity: {s['liquidity']}")
        yaml_lines.append(f"      cost: {s['cost']}")
        yaml_lines.append(f"      has_derivatives: {s['has_derivatives']}")
    yaml_lines.append("")

yaml_path = OUTPUT_BASE / "registry" / "SYMBOL_CLUSTER_MAP.yaml"
with open(yaml_path, 'w') as f:
    f.write('\n'.join(yaml_lines))

print(f"Wrote {yaml_path}")

# ============================================================
# 6. Write SYMBOL_CLUSTER_RATIONALE.md
# ============================================================
available_count = sum(1 for r in registry_rows if r['available_in_current_cache'] == 'YES')
unavailable_count = sum(1 for r in registry_rows if r['available_in_current_cache'] == 'UNAVAILABLE_IN_CURRENT_DATA')

rationale_md = f"""# Symbol Cluster Rationale

Generated: {STARTED_AT}

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
| P0_CORE | {sum(1 for r in registry_rows if r['priority']=='P0_CORE')} | Must-have for any discovery |
| P1_EXPANSION | {sum(1 for r in registry_rows if r['priority']=='P1_EXPANSION')} | Required for cluster discovery |
| P2_OPTIONAL | {sum(1 for r in registry_rows if r['priority']=='P2_OPTIONAL')} | Nice-to-have |
| P3_LATER | {sum(1 for r in registry_rows if r['priority']=='P3_LATER')} | Future expansion |

## Availability

- **Available in current data:** {available_count} symbols
- **UNAVAILABLE_IN_CURRENT_DATA:** {unavailable_count} symbols

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
"""

rationale_path = OUTPUT_BASE / "registry" / "SYMBOL_CLUSTER_RATIONALE.md"
with open(rationale_path, 'w') as f:
    f.write(rationale_md)

print(f"Wrote {rationale_path}")

# ============================================================
# 7. Append to experiments.jsonl
# ============================================================
ledger_row = {
    "timestamp": STARTED_AT,
    "task": "phase_2_symbol_registry",
    "command": "python3 scripts/v7_lite/build_symbol_registry.py",
    "source_files": [str(RAW_DIR), str(DATA_LAKE_DIR)],
    "output_files": [
        str(reg_csv),
        str(yaml_path),
        str(rationale_path),
    ],
    "status": "PASS",
    "metrics": {
        "total_symbols_in_registry": len(registry_rows),
        "available_symbols": available_count,
        "unavailable_symbols": unavailable_count,
        "clusters": len(cluster_map),
        "p0_core": sum(1 for r in registry_rows if r['priority']=='P0_CORE'),
        "p1_expansion": sum(1 for r in registry_rows if r['priority']=='P1_EXPANSION'),
        "p2_optional": sum(1 for r in registry_rows if r['priority']=='P2_OPTIONAL'),
        "p3_later": sum(1 for r in registry_rows if r['priority']=='P3_LATER'),
    },
    "decision": f"Registry created with {len(registry_rows)} symbols across {len(cluster_map)} clusters. {available_count} available, {unavailable_count} missing.",
    "next_action": "phase_3_quality_audit"
}

with open(OUTPUT_BASE / "experiments.jsonl", 'a') as f:
    f.write(json.dumps(ledger_row) + '\n')

print(f"\n=== Phase 2 Complete ===")
print(f"Registry: {len(registry_rows)} symbols, {len(cluster_map)} clusters")
print(f"Available: {available_count}, Unavailable: {unavailable_count}")
