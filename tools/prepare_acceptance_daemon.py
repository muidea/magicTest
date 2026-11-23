#!/usr/bin/env python3
"""Create an isolated acceptance daemon through the durable lifecycle owner."""
import argparse
from pathlib import Path

from acceptance_resources import Resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--state', type=Path, default=Path.home() / '.local/state/platform-acceptance/resources')
    args = parser.parse_args()
    with Resources(args.state).locked() as owner:
        record = owner.create(args.run, args.root)
        print('run=' + record['runId'] + ' phase=' + record['phase'])


if __name__ == '__main__':
    main()
