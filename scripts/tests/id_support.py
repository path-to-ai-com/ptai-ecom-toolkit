"""M-Nummern ohne Cockpit für Tests, die `measures.create()` aufrufen. Kein Test.

Seit 25.10.2026 holt `create()` jede Nummer über `measures.reserve_id()` beim
Zähler der Marke im Cockpit. Ein Test geht nie ins Netz; er ersetzt die
Funktion durch `local_ids` oder durch einen eigenen Zähler.

`local_ids` antwortet wie ein Cockpit, dessen Zähler nie vor der Datei liegt:
die Nummer ist `next_id` der Liste. So bleiben die Erwartungen der älteren
Tests (M-001 für eine leere Liste) gültig. Wie sich `create()` verhält, wenn
das Cockpit weiter gezählt hat, prüft `test_measures.py` mit eigenen Zählern.
"""
import unittest
from unittest import mock

from audit import measures

#: Die echte Funktion, gemerkt beim Import, bevor ein Test sie ersetzt.
REAL_RESERVE_ID = measures.reserve_id


def local_ids(backlog: dict, workspace=".") -> tuple[int, int]:
    """Nummer und `next_id` wie aus einem Zähler, der genau bei der Datei steht."""
    return backlog["next_id"], backlog["next_id"] + 1


def offline_ids() -> None:
    """Ersetzt `measures.reserve_id` für alle Tests eines Moduls.

    Aufruf in `setUpModule()`; zurückgesetzt wird über `addModuleCleanup`.
    """
    patcher = mock.patch.object(measures, "reserve_id", local_ids)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
