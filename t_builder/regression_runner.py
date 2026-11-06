"""Run unchanged Z Builder tests in fresh processes to isolate native Qt lifetime state."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


def flatten(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite):yield from flatten(test)
        else:yield test


def main():
    root=Path(__file__).resolve().parents[1]
    suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_z_builder*.py')
    tests=list(flatten(suite))
    if not tests:raise RuntimeError('No Z Builder regression tests discovered')
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join([str(root/'tests'),str(root),env.get('PYTHONPATH','')])
    env['PYTHONFAULTHANDLER']='1'
    for test in tests:
        print('Isolated regression: '+test.id(),flush=True)
        result=subprocess.run([sys.executable,'-X','faulthandler','-m','unittest',test.id(),'-v'],cwd=root,env=env)
        if result.returncode:
            print(f'FAILED {test.id()}: exit {result.returncode}',flush=True)
            return 1
    print(f'PASS: {len(tests)} unchanged Z Builder regressions in isolated processes',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
