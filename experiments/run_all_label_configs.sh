#!/bin/bash
# Run all 5 label configs and collect results
cd /home/daskomputer/src/v7-engine

python3 -c "
import json
with open('/tmp/alpha_configs.json') as f:
    configs = json.load(f)

results = []
for cid, cfg in sorted(configs.items(), key=lambda x: int(x[0])):
    print(f'\\n{\"=\"*60}')
    print(f'Alpha {cid}: {cfg[\"name\"]}')
    print(f'{\"=\"*60}')
    
    # Patch train.py MODE_CONFIG before running
    import alphaforge.train as t
    t.MODE_CONFIG['SCALP'] = {
        'primary': '1h',
        'max_hold': cfg['max_hold'],
        'stop_mult': cfg['stop_mult'],
        'target_mult': cfg['target_mult'],
        'ambiguity_margin_r': cfg['ambiguity_margin_r'],
        'min_edge_r': cfg['min_edge_r'],
    }
    
    # Run in subprocess with patched module
    import subprocess, sys, os
    env = os.environ.copy()
    env['PYTHONPATH'] = 'alphaforge/src'
    env['ALPHA_CONFIG_ID'] = str(cid)
    
    # We need to patch the file and run
    # Write a temp runner
    runner = f'''import sys, json
sys.path.insert(0, 'alphaforge/src')
import alphaforge.train as t
import json
with open('/tmp/alpha_configs.json') as f:
    cfg = json.load(f)['{cid}']
t.MODE_CONFIG['SCALP'] = {json.dumps(cfg)}
r = t.main()
print('==RESULT_JSON==' + json.dumps({{'alpha': {cid}, 'name': '{cfg['name']}', 'net_r': r['net_expectancy_r'], 'active_trades': r['total_active_trades'], 'accuracy': r['accuracy'], 'exposure': r['exposure_pct']}}))
'''
    with open('/tmp/_runner_{cid}.py', 'w') as f:
        f.write(runner)
    
    r = subprocess.run([sys.executable, '/tmp/_runner_{cid}.py'], capture_output=True, text=True, timeout=600, env=env)
    out = r.stdout
    # Extract result JSON
    if '==RESULT_JSON==' in out:
        result_json = out.split('==RESULT_JSON==')[1].strip().split(chr(10))[0]
        results.append(json.loads(result_json))
        print(f'  net_r={json.loads(result_json)[\"net_r\"]:.6f}')
    else:
        print(f'  FAILED - no result marker')
        print(out[-500:] if out else 'no stdout')
        if r.stderr: print('stderr:', r.stderr[-500:])

print(f'\\n{\"=\"*60}')
print('ALL RESULTS')
print(json.dumps(results, indent=2))
print(f'{\"=\"*60}')
" 2>&1
