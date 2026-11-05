import copy
import json
import tempfile
import unittest
from pathlib import Path

from regression_inventory import build_rows, resolve_reference, validate_inventory


class RegressionInventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.platform = self.root / "platform"
        self.workspace.mkdir()
        self.platform.mkdir()
        validator = Path(__file__).resolve().parent.parent / 'docs/scripts/platform_acceptance.py'
        validator_copy = self.workspace / 'docs/scripts/platform_acceptance.py'
        validator_copy.parent.mkdir(parents=True)
        validator_copy.write_text(validator.read_text())
        for name in ("cases.json", "app.md", "test.py"):
            (self.workspace / name).write_text("{}")
        self.catalog = {
            "executionSuites": {"standard": "automatic", "special": "conditional"},
            "specialPrerequisites": {"fault": {"name": "fault", "preparation": "prepare", "exitCriteria": "recover"}},
            "fixtures": {"business": "controlled fixture"},
            "features": [{"id": "F001"}, {"id": "F002"}],
            "cases": [{"id": f"F00{n}-001", "featureId": f"F00{n}", "title": "test",
                       "kind": "normal", "fixture": "business", "methods": ["live"], "priority": "P0",
                       "execution": [{"suite": "standard", "scope": "all", "prerequisites": [], "fixture": "business"}]}
                      for n in (1, 2)],
        }
        self.inventory = {
            "scope": "platform-basic", "sourceCatalog": "~/codespace/cases.json",
            "applicationSuites": ["~/codespace/app.md"],
            "assets": [{"id": "a", "path": "~/codespace/test.py", "layer": "api", "limitation": "pending"}],
            "scenarios": [{"id": "R01", "title": "test", "featureIds": ["F001", "F002"],
                           "owners": ["owner"], "candidateAssets": ["a"]}],
            "caseReviews": [],
        }

    def validate(self, inventory=None):
        validate_inventory(inventory or self.inventory, self.catalog, self.workspace, self.platform)

    def test_candidates_do_not_claim_case_coverage(self):
        self.catalog['cases'][0].update(purpose='保护精确实例读取', required=True)
        self.catalog['features'][0]['owners'] = ['read-owner']
        self.validate()
        rows = build_rows(self.inventory, self.catalog)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["candidateAssets"], ["a"])
        self.assertEqual(rows[0]["reviewedAssets"], [])
        self.assertEqual(rows[0]["status"], "unreviewed")
        self.assertEqual(rows[0]['purpose'], '保护精确实例读取')
        self.assertTrue(rows[0]['required'])
        self.assertEqual(rows[0]['owners'], ['read-owner'])

    def test_missing_or_duplicate_feature_assignment_fails(self):
        for assignment in (["F001"], ["F001", "F002", "F002"], ["F001", "F003"]):
            with self.subTest(assignment=assignment):
                inventory = copy.deepcopy(self.inventory)
                inventory["scenarios"][0]["featureIds"] = assignment
                with self.assertRaises(ValueError):
                    self.validate(inventory)

    def test_duplicate_or_unknown_case_review_fails(self):
        review = {"caseId": "F001-001", "status": "partial", "assetIds": ["a"], "finding": "missing revoke"}
        for reviews in ([review, review], [{**review, "caseId": "F999-001"}], [{**review, "status": "passed"}]):
            with self.subTest(reviews=reviews):
                self.inventory["caseReviews"] = reviews
                with self.assertRaises(ValueError):
                    self.validate()

    def test_stale_asset_and_unknown_target_fail(self):
        (self.workspace / "test.py").unlink()
        with self.assertRaisesRegex(ValueError, "不存在"):
            self.validate()
        (self.workspace / "test.py").touch()
        self.inventory["assets"][0]["target"] = "missing-target"
        with self.assertRaisesRegex(ValueError, "target"):
            self.validate()

    def test_unknown_asset_and_duplicate_scenario_fail(self):
        self.inventory["scenarios"][0]["candidateAssets"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "未知资产"):
            self.validate()
        self.inventory["scenarios"][0]["candidateAssets"] = ["a"]
        self.inventory["scenarios"].append(copy.deepcopy(self.inventory["scenarios"][0]))
        with self.assertRaisesRegex(ValueError, "重复"):
            self.validate()

    def test_reference_cannot_escape_checkout(self):
        for reference in ("~/codespace/../secret", "/tmp/test.py", "~/codespace//etc/passwd"):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    resolve_reference(reference, self.workspace, self.platform)

    def test_cli_json_lists_all_cases_without_execution(self):
        import contextlib
        import io
        from regression_inventory import main

        (self.workspace / "cases.json").write_text(json.dumps(self.catalog))
        inventory_file = self.root / "inventory.json"
        inventory_file.write_text(json.dumps(self.inventory))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--inventory", str(inventory_file), "--workspace", str(self.workspace),
                         "--platform-root", str(self.platform), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output.getvalue())["cases"]), 2)

    def test_cli_special_filter_preserves_mixed_scope_without_dropping_case_identity(self):
        import contextlib
        import io
        from regression_inventory import main

        self.catalog['cases'][0]['execution'].append(
            {'suite': 'special', 'scope': 'lost response', 'prerequisites': ['fault'], 'fixture': 'business'})
        (self.workspace / 'cases.json').write_text(json.dumps(self.catalog))
        inventory_file = self.root / 'inventory.json'
        inventory_file.write_text(json.dumps(self.inventory))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['--inventory', str(inventory_file), '--workspace', str(self.workspace),
                         '--platform-root', str(self.platform), '--suite', 'special', '--json'])
        self.assertEqual(code, 0)
        rows = json.loads(output.getvalue())['cases']
        self.assertEqual([r['caseId'] for r in rows], ['F001-001'])
        self.assertEqual(rows[0]['execution'], [self.catalog['cases'][0]['execution'][1]])

    def test_routing_validation_is_shared_with_catalogue_owner(self):
        self.catalog['cases'][0]['execution'][0]['suite'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'execution suite'):
            self.validate()


if __name__ == "__main__":
    unittest.main()
