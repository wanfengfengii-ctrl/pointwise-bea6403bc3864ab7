"""Revisions, fixed tasks, diffuse results, and durable report retrieval."""
import tempfile
from pathlib import Path
from .db import Store
from .samples import build
from .codec import dumps


def main():
    with tempfile.TemporaryDirectory(prefix='trend-demo-') as directory:
        path = Path(directory) / 'archive.sqlite'
        with Store(path) as store:
            manifest = build(store)
            old = store.analyze('one-reading')
            assert old['report']['items'][0]['status'] == 'unidentified'
            assert old['report']['mean'] == [0]
            assert store.analyze('two-readings')['report']['mean'] == [9, 11]
            assert store.read_report('contradiction')['report'] is None
        with Store(path) as store:
            assert store.read_report('one-reading') == old
            assert store.analyze('frozen-pending')['report']['estimable'] == []
            print(dumps({'archive_version': store.schema_version,
                         'reports': {name: store.read_report(name) for name in manifest['tasks']}}))


if __name__ == '__main__':
    main()
