"""Keep the vendored names implementation identical across independently built images.

B2B is the source. Default: check only. --write updates the Agents copies.
"""
import argparse
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agents-root', type=Path, default=root.parent/'ms-dpia-agents')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    for name in ('task_names.py', 'task_name_backfill.py'):
        source = root/'src/services'/name
        target = args.agents_root/'src/services'/name
        if args.write:
            target.write_bytes(source.read_bytes())
        if not target.exists() or source.read_bytes() != target.read_bytes():
            raise SystemExit('Different naming implementation: '+str(target))
        print('Identical: '+name)


if __name__ == '__main__':
    main()
