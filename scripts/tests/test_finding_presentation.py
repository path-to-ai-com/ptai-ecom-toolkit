"""Neue Pflichtangaben und Altkompatibilität in echten Kopier- und Prüfschritten."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from audit import finding_format, state, publish, qa, report_build
from tests.test_publish import make_workspace

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'reference/finding-format'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class TestPresentation(unittest.TestCase):
    def test_target_examples_and_trend(self):
        for name in ('presentation-v2.json', 'presentation-trend-v2.json'):
            doc = load('valid/' + name)
            self.assertEqual(finding_format.document_problems(doc), [])

    def test_shared_negative_cases(self):
        for case in load('presentation-invalid.json'):
            with self.subTest(case=case['name']):
                docs = load('valid/presentation-v2.json')['findings'] + load('valid/presentation-trend-v2.json')['findings']
                finding = copy.deepcopy(next(f for f in docs if f['id'] == case['source']))
                for change in case['changes']:
                    target = finding
                    for key in change['path'][:-1]:
                        target = target[key]
                    if change.get('remove'):
                        del target[change['path'][-1]]
                    else:
                        target[change['path'][-1]] = change['value']
                self.assertTrue(finding_format.problems(finding, case['version']))

    def test_shared_sentence_cases(self):
        for case in load('presentation-sentences.json'):
            for key in ('cause', 'effect', 'recommendation'):
                with self.subTest(text=case['text'], field=key):
                    finding = copy.deepcopy(load('valid/presentation-v2.json')['findings'][0])
                    finding['reasoning'][key] = case['text']
                    self.assertEqual(finding_format.problems(finding, 2) == [], case['valid'])

    def test_month_publish_requires_file_but_accepts_explicit_empty_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = '2026-11-02-month'
            ws = make_workspace(root, run_id)
            folder = ws / 'reporting/runs' / run_id
            state.new(ws, run_id, 'month').save()
            file = folder / 'findings/cro.json'
            file.unlink()
            target = root / 'bucket'
            self.assertTrue(finding_format.run_problems(folder))
            with self.assertRaisesRegex(SystemExit, 'Befundformat'):
                publish.prepare(ws, run_id, target)
            self.assertFalse(target.exists())
            file.write_text(json.dumps({'finding_format': 2, 'findings': []}))
            self.assertEqual(finding_format.run_problems(folder), [])
            publish.prepare(ws, run_id, target)
            copied = list(target.rglob('findings/cro.json'))
            self.assertEqual(len(copied), 1)
            self.assertEqual(json.loads(copied[0].read_text()), {'finding_format': 2, 'findings': []})

    def test_incomplete_current_shape_without_marker_is_rejected(self):
        self.assertTrue(finding_format.problems({'primary_metric': {}}))

    def test_legacy_remains_valid(self):
        for name in ('full-audit.json', 'audit-light.json'):
            doc = load('valid/' + name)
            for f in doc.get('findings', [doc]):
                self.assertEqual(finding_format.problems(f), [])

    def test_state_stamps_new_runs_but_never_upgrades_existing_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = Path(temp)
            for cadence in ('audit', 'month'):
                run_id = '2026-11-02-' + cadence
                s = state.new(ws, run_id, cadence)
                s.save()
                self.assertEqual(json.loads(s.path.read_text())['finding_format'], 2)
                old = json.loads(s.path.read_text())
                del old['finding_format']
                s.path.write_text(json.dumps(old))
                state.load_or_new(ws, run_id, cadence).save()
                self.assertNotIn('finding_format', json.loads(s.path.read_text()))

    def test_publish_refuses_missing_fields_before_any_copy_and_qa_reports_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = make_workspace(root, '2026-11-02-audit')
            folder = ws / 'reporting/runs/2026-11-02-audit'
            s = state.new(ws, '2026-11-02-audit', 'audit')
            s.save()
            f = copy.deepcopy(load('valid/presentation-v2.json')['findings'][0])
            for field in ('primary_metric', 'reasoning', 'cause', 'effect', 'recommendation'):
                broken = copy.deepcopy(f)
                if field in ('cause', 'effect', 'recommendation'):
                    del broken['reasoning'][field]
                else:
                    del broken[field]
                (folder / 'findings/cro.json').write_text(json.dumps({'findings': [broken]}))
                with self.subTest(field=field):
                    target = root / 'bucket'
                    with self.assertRaisesRegex(SystemExit, 'Befundformat'):
                        publish.prepare(ws, '2026-11-02-audit', target)
                    self.assertFalse(target.exists())
                    findings = qa.check_findings(report_build.Run(ws, '2026-11-02-audit'))
                    self.assertTrue(any(x.stufe == 'fehler' and field in x.text for x in findings))

    def test_valid_current_and_legacy_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = make_workspace(root, '2026-11-02-audit')
            folder = ws / 'reporting/runs/2026-11-02-audit'
            f = load('valid/presentation-v2.json')['findings'][0]
            state.new(ws, '2026-11-02-audit', 'audit').save()
            (folder / 'findings/cro.json').write_text(json.dumps({'findings': [f]}))
            publish.prepare(ws, '2026-11-02-audit', root / 'current')
            (folder / 'state.json').write_text(json.dumps({'cadence': 'audit'}))
            (folder / 'findings/cro.json').write_text(json.dumps({'findings': [{'id': 'OLD-01'}]}))
            publish.prepare(ws, '2026-11-02-audit', root / 'legacy')

    def test_malformed_and_unknown_documents(self):
        for doc, version in (({}, 2), ({'finding_format': 3, 'findings': []}, None), ({'finding_format': 1, 'findings': []}, 2), (None, None)):
            with self.subTest(doc=doc):
                self.assertTrue(finding_format.document_problems(doc, version))
