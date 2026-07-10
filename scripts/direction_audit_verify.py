"""
Direction Fix Audit Verification Script.

Reads FACTOR_REGISTRY, IC leaderboard, and R leaderboard to verify
direction declarations and identify mismatches.

Output: JSON report of per-factor direction audit.
"""
import csv
import json
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "reports/alphaforge/factor_sprint"

def load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def main():
    # 1. Read FACTOR_REGISTRY from source
    registry_path = REPO_ROOT / "alphaforge/src/alphaforge/factors/factors.py"
    registry_lines = registry_path.read_text().splitlines()
    
    # Parse FACTOR_REGISTRY dict
    registry = {}
    in_registry = False
    for line in registry_lines:
        if "FACTOR_REGISTRY: dict[str, tuple[str, callable]]" in line:
            in_registry = True
            continue
        if in_registry and "}" in line and not line.strip().startswith("#"):
            in_registry = False
            continue
        if in_registry and '"' in line:
            # Parse "name": ("direction", func_name),
            parts = line.strip().split('"')
            if len(parts) >= 5:
                name = parts[1]
                dir_part = parts[3] if "," not in parts[3] else parts[3].split(",")[0].strip()
                registry[name] = dir_part

    print(f"Loaded {len(registry)} factors from FACTOR_REGISTRY")
    for name, direction in sorted(registry.items()):
        print(f"  {name}: {direction}")

    # 2. Read IC leaderboard
    ic_path = ARTIFACTS_DIR / "ALPHA_LEADERBOARD_V2.csv"
    ic_rows = load_csv(ic_path)
    print(f"\nIC leaderboard: {len(ic_rows)} rows")

    # Group by factor name
    ic_by_factor = {}
    for row in ic_rows:
        fname = row.get("factor_name", "")
        if fname not in ic_by_factor:
            ic_by_factor[fname] = []
        ic_by_factor[fname].append(row)

    # 3. Read R leaderboard
    r_path = ARTIFACTS_DIR / "ALPHA_R_LEADERBOARD.csv"
    r_rows = load_csv(r_path)
    print(f"R leaderboard: {len(r_rows)} rows")
    
    r_by_factor = {}
    for row in r_rows:
        fname = row.get("factor_name", "")
        if fname not in r_by_factor:
            r_by_factor[fname] = []
        r_by_factor[fname].append(row)

    # 4. Cross-reference
    print("\n" + "="*80)
    print("DIRECTION AUDIT RESULTS")
    print("="*80)
    
    audit_results = []
    
    for fname, decl_dir in sorted(registry.items()):
        if decl_dir in ("agnostic", "unstable"):
            audit_results.append({
                "factor_name": fname,
                "current_declared_direction": decl_dir,
                "expected_direction": decl_dir,
                "evidence": "Direction-agnostic or unstable by design",
                "classification": "NOT_MISDECLARED",
            })
            continue
        
        ic_entries = ic_by_factor.get(fname, [])
        r_entries = r_by_factor.get(fname, [])
        
        # Find best IC data
        best_ic_abs = 0
        best_ic_row = None
        for ic_row in ic_entries:
            ic_val = float(ic_row.get("mean_rank_ic", 0) or 0)
            if abs(ic_val) > best_ic_abs:
                best_ic_abs = abs(ic_val)
                best_ic_row = ic_row
        
        # Find best R data
        best_r = 0
        best_r_row = None
        for r_row in r_entries:
            r_val = float(r_row.get("net_R_per_trade", 0) or 0)
            if abs(r_val) > best_r:
                best_r = abs(r_val)
                best_r_row = r_row
        
        ic_sign = "positive" if best_ic_row and float(best_ic_row.get("mean_rank_ic", 0) or 0) > 0 else "negative" if best_ic_row else "unknown"
        ic_val = float(best_ic_row.get("mean_rank_ic", 0)) if best_ic_row else 0
        
        # For "long" direction: expected IC sign is positive (high factor score → high forward return)
        # For "short" direction: expected IC sign is negative (high factor score → low forward return = high factor score → short bet wins)
        # But wait - the IC is computed on raw factor scores, not on the trading signal.
        # The direction in the registry determines how the factor is used as a trade signal.
        # If direction is "long": high score = long bet → expect positive IC (high score predicts positive returns)
        # If direction is "short": high score = short bet → expect negative IC (high score predicts negative returns)
        
        ic_consistent = None
        if decl_dir == "long":
            ic_consistent = ic_val > 0
        elif decl_dir == "short":
            ic_consistent = ic_val < 0
        
        if ic_consistent is None:
            classification = "UNCLEAR"
            note = f"IC sign={ic_sign}, direction={decl_dir} — cannot determine consistency"
        elif ic_consistent:
            classification = "NOT_MISDECLARED"
            note = f"IC sign={ic_sign} ({ic_val:.4f}), direction={decl_dir} — CONSISTENT ✓"
        else:
            classification = "CONFIRMED_MISDECLARED"
            note = f"IC sign={ic_sign} ({ic_val:.4f}), direction={decl_dir} — INCONSISTENT ✗"
        
        # R evidence
        old_raw_r = 0
        old_trade_count = 0
        if best_r_row:
            old_raw_r = float(best_r_row.get("net_R_per_trade", 0) or 0)
            old_trade_count = int(best_r_row.get("trade_count", 0) or 0)
        
        # Check annotations for "flipped"
        annotations = []
        for ic_row in ic_entries:
            tags = ic_row.get("tags", "")
            if "flipped" in tags.lower() or "inverted" in tags.lower():
                annotations.append(f"IC row {ic_row.get('alpha_id','')}: {tags}")
        
        audit_results.append({
            "factor_name": fname,
            "current_declared_direction": decl_dir,
            "expected_direction": "short" if decl_dir == "long" and not ic_consistent else 
                                 "long" if decl_dir == "short" and not ic_consistent else decl_dir,
            "evidence": note + ("; " + "; ".join(annotations) if annotations else ""),
            "best_ic_val": ic_val,
            "ic_sign": ic_sign,
            "ic_consistent": ic_consistent,
            "classification": classification,
            "old_raw_R": old_raw_r,
            "old_trade_count": old_trade_count,
            "retest_required": classification in ("CONFIRMED_MISDECLARED", "LIKELY_MISDECLARED"),
        })
        
        print(f"\n{fname} ({decl_dir}):")
        print(f"  Best IC: {ic_val:.4f} ({ic_sign})")
        print(f"  IC consistent with direction: {ic_consistent}")
        print(f"  Classification: {classification}")
        print(f"  Best R: {old_raw_r:.4f} ({old_trade_count} trades)")
    
    # Summary
    confirmed = sum(1 for r in audit_results if r["classification"] == "CONFIRMED_MISDECLARED")
    not_misdeclared = sum(1 for r in audit_results if r["classification"] == "NOT_MISDECLARED")
    unclear = sum(1 for r in audit_results if r["classification"] == "UNCLEAR")
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {confirmed} CONFIRMED_MISDECLARED, {not_misdeclared} NOT_MISDECLARED, {unclear} UNCLEAR")
    
    # Write results
    output = {
        "registry_size": len(registry),
        "confirmed_misdeclared": confirmed,
        "not_misdeclared": not_misdeclared,
        "unclear": unclear,
        "results": audit_results,
    }
    output_path = REPO_ROOT / "reports/v7_lite/auto_loop/recovery/direction_audit_raw.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {output_path}")

if __name__ == "__main__":
    main()
