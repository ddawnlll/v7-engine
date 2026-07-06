"""Run SCALP WFV with a custom label config. Usage: python3 run_label_config.py <config_id>"""
import sys, json, importlib
sys.path.insert(0, 'alphaforge/src')

# Load configs
with open('/tmp/alpha_configs.json') as f:
    ALL_CONFIGS = json.load(f)

config_id = int(sys.argv[1])
cfg = ALL_CONFIGS[str(config_id)]
print(f'Alpha {config_id}: {cfg["name"]}')
print(f'Config: {cfg}')

# Patch MODE_CONFIG for SCALP
import alphaforge.train as train_mod
train_mod.MODE_CONFIG['SCALP'] = {
    'primary': '1h', 'max_hold': cfg['max_hold'],
    'stop_mult': cfg['stop_mult'], 'target_mult': cfg['target_mult'],
    'ambiguity_margin_r': cfg['ambiguity_margin_r'],
    'min_edge_r': cfg['min_edge_r'],
}

# Run training
import alphaforge.train
result = alphaforge.train.main()
print(f'\n===== RESULT =====')
print(json.dumps({'alpha': config_id, 'name': cfg['name'], 'net_r': result['net_expectancy_r'], 'active_trades': result['total_active_trades'], 'accuracy': result['accuracy']}))
