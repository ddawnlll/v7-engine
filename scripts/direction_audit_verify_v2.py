"""
Direction Fix Audit — v2 using proper CSV column names.
"""
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "reports/alphaforge/factor_sprint"

def load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def main():
    # Parse FACTOR_REGISTRY from source
    registry_path = REPO_ROOT / "alphaforge/src/alphaforge/factors/factors.py"
    lines = registry_path.read_text().splitlines()
    
    registry = {}
    in_registry = False
    for line in lines:
        if "FACTOR_REGISTRY: dict[str, tuple[str, callable]]" in line:
            in_registry = True
            continue
        if in_registry and "}" in line and not line.strip().startswith("#") and not line.strip().startswith("}"):
            # end of dict
            pass
        if in_registry and '"' in line:
            parts = line.strip().split('"')
            if len(parts) >= 5:
                name = parts[1]
                dir_part = parts[3]
                if "," in dir_part:
                    dir_part = dir_part.split(",")[0].strip().strip("(").strip()
                registry[name] = dir_part
        if in_registry and line.strip() == "}":
            break
    
    print(f"Loaded {len(registry)} factors from FACTOR_REGISTRY")
    
    # Load IC + R data
    ic_rows = load_csv(ARTIFACTS_DIR / "ALPHA_LEADERBOARD_V2.csv")
    r_rows = load_csv(ARTIFACTS_DIR / "ALPHA_R_LEADERBOARD.csv")
    
    # Group IC by factor_name
    ic_by_factor = {}
    for r in ic_rows:
        fn = r["factor_name"]
        if fn not in ic_by_factor:
            ic_by_factor[fn] = []
        ic_by_factor[fn].append(r)
    
    # Group R by alpha_name
    r_by_factor = {}
    for r in r_rows:
        an = r["alpha_name"]
        if an not in r_by_factor:
            r_by_factor[an] = []
        r_by_factor[an].append(r)
    
    results = []
    
    for fname, decl_dir in sorted(registry.items()):
        # Skip non-evaluable factors
        if decl_dir in ("agnostic", "unstable"):
            results.append({
                "factor_name": fname,
                "current_declared_direction": decl_dir,
                "best_ic": None,
                "ic_consistent": None,
                "classification": "NOT_MISDECLARED",
                "reasoning": f"Direction is '{decl_dir}' by design — not testable for misdeclaration",
                "best_ic_entry": None,
                "best_r_entry": None,
            })
            continue
        
        # Find best IC evidence
        ic_entries = ic_by_factor.get(fname, [])
        best_ic = None
        best_ic_row = None
        for ic in ic_entries:
            ic_val = float(ic["mean_rank_ic"])
            if best_ic is None or abs(ic_val) > abs(best_ic):
                best_ic = ic_val
                best_ic_row = ic
        
        # IC consistency: 
        #   long direction → positive IC expected (high score predicts positive return)
        #   short direction → negative IC expected (high score predicts negative return)
        ic_sign = "N/A"
        ic_consistent = None
        if best_ic is not None:
            ic_sign = "positive" if best_ic > 0 else "negative"
            if decl_dir == "long":
                ic_consistent = best_ic > 0
            elif decl_dir == "short":
                ic_consistent = best_ic < 0
        
        # Check for flipped annotations in the full inventory
        flipped = ""
        inv_path = REPO_ROOT / "reports/ALPHA_INVENTORY_FULL.csv"
        with open(inv_path) as f:
            for row in csv.DictReader(f):
                if row["name"] == fname and row["source"] == "factor_sprint_ic_leaderboard":
                    if "flipped" in row.get("tags", "").lower() or "inverted" in row.get("tags", "").lower():
                        flipped = row["tags"]
        
        # Find best R evidence
        r_entries = r_by_factor.get(fname, [])
        best_r = None
        best_r_row = None
        for r in r_entries:
            r_val = float(r.get("avg_R", 0) or 0)
            if best_r is None or abs(r_val) > abs(best_r):
                best_r = r_val
                best_r_row = r
        
        # Determine classification
        if best_ic is None:
            classification = "BLOCKED_DATA_MISSING"
            reasoning = f"No IC data available for factor '{fname}'"
        elif ic_consistent is None:
            classification = "UNCLEAR"
            reasoning = f"IC={best_ic:.4f} but direction is '{decl_dir}' — cannot determine"
        elif ic_consistent:
            classification = "NOT_MISDECLARED"
            reasoning = f"IC={best_ic:.4f} ({ic_sign}), direction='{decl_dir}' → CONSISTENT"
            if flipped:
                reasoning += f" (note: IC entry flagged '{flipped}' but this may be a labeling issue)"
        else:
            classification = "CONFIRMED_MISDECLARED"
            reasoning = f"IC={best_ic:.4f} ({ic_sign}), direction='{decl_dir}' → INCONSISTENT"
            if flipped:
                reasoning += f" (IC entry flagged '{flipped}')"
        
        results.append({
            "factor_name": fname,
            "current_declared_direction": decl_dir,
            "best_ic": round(best_ic, 4) if best_ic is not None else None,
            "ic_sign": ic_sign if best_ic is not None else "N/A",
            "ic_consistent": ic_consistent,
            "flipped_tag": flipped,
            "classification": classification,
            "reasoning": reasoning,
            "best_r": round(best_r, 4) if best_r is not None else None,
            "retest_required": classification == "CONFIRMED_MISDECLARED",
        })
        
        status = "✓" if classification == "NOT_MISDECLARED" else "✗" if classification == "CONFIRMED_MISDECLARED" else "?"
        print(f"  {status} {fname:35s} dir={decl_dir:7s} IC={str(best_ic or 'N/A'):>8s} {classification}")
    
    # Summary
    counts = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    
    print(f"\n--- Summary ---")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    
    confirmed = [r for r in results if r["classification"] == "CONFIRMED_MISDECLARED"]
    print(f"\nConfimed misdeclared: {[r['factor_name'] for r in confirmed]}")
    
    # Write output
    output_path = REPO_ROOT / "reports/v7_lite/auto_loop/recovery/direction_audit_verified.json"
    output_path.write_text(json.dumps({"results": results, "summary": counts}, indent=2))
    print(f"\nWrote {output_path}")

if __name__ == "__main__":
    main()
