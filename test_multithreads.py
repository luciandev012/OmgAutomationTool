r"""Two-MuMu Excel login test: five successful accounts per instance by default.

Run with .venv\Scripts\python.exe test_multithreads.py from this repository.
Uses only test_script.xlsx (STT 1-10); backs up and clears Status/days on each run.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import argparse
import json
import signal
import threading
import shutil

from emulator_instances import detect_emulators
from excel_login_test import ExcelLoginTest
from omg3q_tool import DEFAULT_MANAGER, input_text, launch_game, run_adb
from task_sessions import SessionRegistry
from account_excel import AccountWorkbook

ROOT = Path(__file__).resolve().parent
TEST_WORKBOOK = ROOT / 'test_script.xlsx'


def reset_test_workbook(path=TEST_WORKBOOK, backup_dir=None):
    path = Path(path).resolve()
    if path.name.casefold() != 'test_script.xlsx':
        raise ValueError('Only test_script.xlsx may be reset.')
    backup_dir = Path(backup_dir or ROOT / 'runtime')
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = backup_dir / f'test_script-before-reset-{stamp}.xlsx'
    shutil.copy2(path, backup)
    result = AccountWorkbook(path).reset_test_progress()
    return {**result, 'backup': str(backup)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=5,
                        help='Successful logins per instance (default: 5); ERR does not count.')
    parser.add_argument('--instances', nargs=2, default=['0', '1'], metavar=('FIRST', 'SECOND'),
                        help='Two distinct MuMu instance indexes (default: 0 1).')
    parser.add_argument('--dry-run', action='store_true',
                        help='List selected instances without opening games or editing Excel.')
    args = parser.parse_args(argv)
    if args.rounds < 1 or len(set(args.instances)) != 2:
        parser.error('Use positive --rounds and two distinct --instances indexes.')
    provider = next((p for p in detect_emulators(DEFAULT_MANAGER, None) if p.kind == 'mumu'), None)
    if provider is None:
        parser.error('MuMu was not found; set OMG_MUMU_MANAGER if installed elsewhere.')
    available = {i.index: i for i in provider.instances()}
    if any(index not in available for index in args.instances):
        parser.error('A selected MuMu instance does not exist.')
    instances = [available[index] for index in args.instances]
    if not TEST_WORKBOOK.is_file():
        parser.error('test_script.xlsx does not exist; copy STT 1-10 from account.xlsx first.')
    print(json.dumps({'test': 'test_multithreads', 'rounds_per_instance': args.rounds,
                      'instances': [{'index': i.index, 'name': i.name} for i in instances],
                      'workbook': str(TEST_WORKBOOK), 'dry_run': args.dry_run}, ensure_ascii=True), flush=True)
    if args.dry_run:
        return 0
    # One reset before either worker starts; recovery must never reset again.
    print(json.dumps({'event': 'test_workbook_reset', **reset_test_workbook()}, ensure_ascii=True), flush=True)
    registry = SessionRegistry()
    output_lock = threading.Lock()
    def progress(session, text):
        with output_lock:
            print(json.dumps({'instance': session.name, 'stage': text}, ensure_ascii=True), flush=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    log = ROOT / 'runtime' / f'test_multithreads-{stamp}.jsonl'
    test = ExcelLoginTest(registry, provider, TEST_WORKBOOK, run_adb, input_text,
                         launch_game, progress, rounds=args.rounds, log_path=log,
                         wait_forever=False, fixed_waits=False)
    # Create sessions before installing cancellation so both workers are stoppable.
    for instance in instances:
        registry.instance(provider, instance)
    previous = signal.signal(signal.SIGINT, lambda *_: registry.stop_all())
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(test.worker, instances))
    finally:
        signal.signal(signal.SIGINT, previous)
    test.audit('test_done', test_name='test_multithreads', results=results)
    summary = {'test': 'test_multithreads', 'log': str(log), 'results': results}
    summary_path = log.with_suffix('.summary.json')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    return 0 if all(r['completed'] == args.rounds and not r['error'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
