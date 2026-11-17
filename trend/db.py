"""SQLite unit of work and the public archive facade."""
import sqlite3
from contextlib import contextmanager
from . import codec


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES('version','1');
CREATE TABLE IF NOT EXISTS revisions(
 revision INTEGER PRIMARY KEY AUTOINCREMENT, series TEXT NOT NULL,
 payload TEXT NOT NULL, sdk1_state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS heads(
 series TEXT PRIMARY KEY, revision INTEGER NOT NULL REFERENCES revisions);
CREATE TABLE IF NOT EXISTS apply_receipts(
 request TEXT PRIMARY KEY, payload TEXT NOT NULL,
 revision INTEGER NOT NULL REFERENCES revisions, receipt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
 task TEXT PRIMARY KEY, revision INTEGER NOT NULL REFERENCES revisions,
 prefix INTEGER NOT NULL, queries TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','done','error')),
 error TEXT);
CREATE TABLE IF NOT EXISTS reports(
 task TEXT PRIMARY KEY REFERENCES tasks, result TEXT NOT NULL,
 sdk1_checkpoint TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_receipts(
 task TEXT PRIMARY KEY REFERENCES tasks, receipt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calibration_revisions(
 calibration_revision INTEGER PRIMARY KEY AUTOINCREMENT,
 calibration TEXT NOT NULL, mean TEXT NOT NULL, variance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calibration_heads(
 calibration TEXT PRIMARY KEY,
 calibration_revision INTEGER NOT NULL REFERENCES calibration_revisions);
CREATE TABLE IF NOT EXISTS calibration_receipts(
 request TEXT PRIMARY KEY, payload TEXT NOT NULL,
 calibration_revision INTEGER NOT NULL REFERENCES calibration_revisions,
 receipt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS joint_tasks(
 task TEXT PRIMARY KEY,
 calibration_revision INTEGER NOT NULL REFERENCES calibration_revisions,
 bindings TEXT NOT NULL, queries TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','done','error')),
 error TEXT);
CREATE TABLE IF NOT EXISTS joint_reports(
 task TEXT PRIMARY KEY REFERENCES joint_tasks,
 result TEXT NOT NULL, checkpoint TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS joint_task_receipts(
 task TEXT PRIMARY KEY REFERENCES joint_tasks, receipt TEXT NOT NULL);
"""


class Store:
    """Single-worker archive. before_commit(label) is a maintenance/test hook."""
    def __init__(self, path=':memory:', before_commit=None):
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.before_commit = before_commit
        try:
            self.connection.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if self.schema_version != 1:
                raise codec.Invalid('unsupported archive version')
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            self.connection.close()
            raise

    @property
    def schema_version(self):
        return int(self.connection.execute(
            "SELECT value FROM metadata WHERE key='version'").fetchone()[0])

    @contextmanager
    def transaction(self, label):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self.connection
            if self.before_commit is not None:
                self.before_commit(label)
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def maintenance(self, operation):
        """Run a single-worker maintenance callable inside one atomic transaction."""
        with self.transaction('maintenance') as connection:
            return operation(connection)

    def apply(self, series, request, model, observations):
        from .series import apply
        return apply(self, series, request, model, observations)

    def head(self, series):
        from .series import head
        return head(self, series)

    def revision(self, revision):
        from .series import revision as read
        return read(self, revision)

    def create_task(self, task, revision, prefix, queries):
        from .tasks import create_task
        return create_task(self, task, revision, prefix, queries)

    def task(self, task):
        from .tasks import task as read
        return read(self, task)

    def analyze(self, task):
        from .analysis import analyze
        return analyze(self, task)

    def read_report(self, task):
        from .reports import read_report
        return read_report(self, task)

    def apply_calibration(self, calibration, request, mean, variance):
        from .calibration import apply_calibration
        return apply_calibration(self, calibration, request, mean, variance)

    def calibration_head(self, calibration):
        from .calibration import calibration_head
        return calibration_head(self, calibration)

    def calibration_revision(self, calibration_revision):
        from .calibration import calibration_revision as read_calibration
        return read_calibration(self, calibration_revision)

    def create_joint_task(self, task, calibration_revision, bindings, queries):
        from .joint import create_joint_task
        return create_joint_task(self, task, calibration_revision, bindings, queries)

    def joint_task(self, task):
        from .joint import joint_task
        return joint_task(self, task)

    def analyze_joint(self, task):
        from .joint_analysis import analyze_joint
        return analyze_joint(self, task)

    def read_joint_report(self, task):
        from .joint_reports import read_joint_report
        return read_joint_report(self, task)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
