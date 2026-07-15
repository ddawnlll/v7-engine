"""Regression-to-decision analysis module."""
import numpy as np

def run_reg2dec_analysis(X, net_r_values, y_int, mode, min_folds=6, timestamps=None):
    """Regression-to-decision: train regression, convert predictions to trades."""
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from alphaforge.train import _get_training_config

    n = len(X)
    fold_size = n // (min_folds + 1)
    cfg = _get_training_config(mode)
    label_horizon = cfg.label_horizon
    purge_bars = 2 * label_horizon
    embargo_bars = 2 * label_horizon

    thresholds = [0.001, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
    all_thr_results = {thr: [] for thr in thresholds}

    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            break

        if timestamps is not None:
            unique_ts, first_rows = np.unique(timestamps, return_index=True)
            boundary_ts = timestamps[val_start]
            boundary_pos = int(np.searchsorted(unique_ts, boundary_ts, side="left"))
            train_pos = max(0, boundary_pos - purge_bars)
            val_pos = min(len(unique_ts) - 1, boundary_pos + embargo_bars)
            effective_train_end = int(first_rows[train_pos])
            effective_val_start = int(first_rows[val_pos])
        else:
            effective_train_end = train_end - purge_bars
            effective_val_start = val_start + embargo_bars

        if effective_train_end <= 0 or effective_val_start >= val_end:
            continue

        X_train = X[:effective_train_end]
        r_train = net_r_values[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        r_val = net_r_values[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]

        if len(X_train) < 50 or len(X_val) < 10:
            continue

        # Train regression model
        reg_trainer = XGBoostTrainer(mode=mode, objective="reg:squarederror")
        reg_result = reg_trainer.train(X_train, r_train)
        y_pred_r = reg_result.model.inplace_predict(X_val)

        for thr in thresholds:
            y_pred_c = np.full(len(X_val), 2, dtype=int)
            y_pred_c[y_pred_r > thr] = 0
            y_pred_c[y_pred_r < -thr] = 1

            active_mask = y_pred_c != 2
            n_active = int(np.sum(active_mask))

            if n_active > 0:
                active_r = r_val[active_mask]
                mean_r = float(np.mean(active_r))
                active_preds = y_pred_c[active_mask]
                correct = active_preds == y_val[active_mask]
                winrate = float(np.mean(correct))

                # Wilson CI
                p_hat = winrate
                nn = n_active
                z = 1.96
                denom = 1 + z**2 / nn
                center = (p_hat + z**2 / (2*nn)) / denom
                margin = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4*nn)) / nn) / denom
                ci_low = max(0.0, center - margin)
                ci_high = min(1.0, center + margin)

                all_thr_results[thr].append({
                    "n_active": n_active,
                    "mean_r": mean_r,
                    "winrate": winrate,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                })

    # Print results
    sep = "=" * 70
    print()
    print(sep)
    print("  REGRESSION-TO-DECISION RESULTS")
    print(sep)
    print("  %-8s  %6s  %10s  %8s  %12s" % ("Thresh", "Active", "MeanR", "Winrate", "95% CI"))
    print("  " + "-" * 70)

    best_thr = None
    best_r = -999

    for thr in thresholds:
        results = all_thr_results[thr]
        if results:
            total_active = sum(r["n_active"] for r in results)
            avg_r = float(np.mean([r["mean_r"] for r in results]))
            avg_wr = float(np.mean([r["winrate"] for r in results]))
            avg_ci_low = float(np.mean([r["ci_low"] for r in results]))
            avg_ci_high = float(np.mean([r["ci_high"] for r in results]))
            n_folds = len(results)

            if avg_r > best_r and total_active >= 20:
                best_r = avg_r
                best_thr = thr

            print("  %-8.3f  %6d  %+10.6f  %7.2f%%  [%5.1f%%, %5.1f%%]  (n=%d)" % (
                thr, total_active, avg_r, avg_wr * 100,
                avg_ci_low * 100, avg_ci_high * 100, n_folds))

    print("  " + "-" * 70)
    if best_thr is not None:
        print("  BEST: threshold=%.3f, meanR=%+.6f" % (best_thr, best_r))
    else:
        print("  No threshold with >=20 active trades found")
    print(sep)

    return all_thr_results, best_thr, best_r
