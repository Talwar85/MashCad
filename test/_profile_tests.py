"""Test suite profiler — runs each test file with a timeout to find hangs."""
import subprocess
import time
import sys
import os
import re

# Use script location to determine paths (portable across machines)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
test_dir = script_dir

os.chdir(project_root)

test_files = sorted([f for f in os.listdir(test_dir) 
                     if f.startswith('test_') and f.endswith('.py')])

out_file = os.path.join(project_root, 'test_profile_log.txt')

with open(out_file, 'w', encoding='utf-8') as f_out:
    f_out.write(f'Profiling {len(test_files)} test files (45s timeout each)...\n')
    f_out.write(f'{"TIME":>6s} {"ST":4s} {"FILE":50s} {"INFO"}\n')
    f_out.write('-' * 100 + '\n')
    f_out.flush()

    total_tests = 0
    total_pass = 0
    total_fail = 0
    hangs = []
    slow = []

    for f in test_files:
        start = time.time()
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'pytest', f'test/{f}', '-q', '--tb=no', '--no-header'],
                capture_output=True, text=True, timeout=45, cwd=project_root
            )
            elapsed = time.time() - start
            lines = [l for l in r.stdout.strip().split('\n') if l.strip()]
            last = lines[-1] if lines else 'NO_OUT'
            
            m = re.search(r'(\d+) passed', last)
            passed = int(m.group(1)) if m else 0
            m = re.search(r'(\d+) failed', last)
            failed = int(m.group(1)) if m else 0
            
            total_tests += passed + failed
            total_pass += passed
            total_fail += failed
            
            status = 'OK' if r.returncode == 0 else 'FAIL'
            msg = f'{elapsed:5.1f}s {status:4s} {f:50s} {last}'
            f_out.write(msg + '\n')
            f_out.flush()
            
            if elapsed > 10:
                slow.append((elapsed, f))
        except subprocess.TimeoutExpired:
            msg = f' 45+s HANG {f:50s} TIMEOUT >45s'
            f_out.write(msg + '\n')
            f_out.flush()
            hangs.append(f)
        except Exception as e:
            msg = f'  ERR ERR  {f:50s} {e}'
            f_out.write(msg + '\n')
            f_out.flush()

    f_out.write('\n' + '=' * 100 + '\n')
    f_out.write(f'Total: {total_tests} tests, {total_pass} passed, {total_fail} failed, {len(hangs)} hangs\n')
    f_out.write(f'\nHANGING (>45s):\n')
    for h in hangs:
        f_out.write(f'  - {h}\n')
    f_out.flush()
