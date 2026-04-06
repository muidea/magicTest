import json
import unittest
from pathlib import Path


class DefinitionAlignmentTestCase(unittest.TestCase):
    def test_magic_project_repo_matches_magic_orm_vmi_baseline(self):
        orm_root = Path("/home/rangh/codespace/magicOrm/test/vmi/entity")
        project_root = Path("/home/rangh/codespace/magicProjectRepo/vmi/entity")

        orm_files = sorted(path for path in orm_root.rglob("*.json"))
        mismatches = []

        for orm_file in orm_files:
            relative_path = orm_file.relative_to(orm_root)
            project_file = project_root / relative_path
            self.assertTrue(project_file.exists(), f"缺少定义文件: {project_file}")

            with orm_file.open("r", encoding="utf-8") as f:
                orm_definition = json.load(f)
            with project_file.open("r", encoding="utf-8") as f:
                project_definition = json.load(f)

            if orm_definition != project_definition:
                mismatches.append(str(relative_path))

        self.assertFalse(
            mismatches,
            f"magicProjectRepo 与 magicOrm VMI 定义不一致: {mismatches}",
        )


if __name__ == "__main__":
    unittest.main()
