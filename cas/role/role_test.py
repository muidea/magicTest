import unittest

from test_support import CasE2EBase, STATUS_DISABLE, STATUS_ENABLE, UNSET


class RoleTestCase(CasE2EBase):
    def setUp(self):
        super().setUp()
        self.tenant = self.create_namespace(scope=UNSET)
        self.tenant_apps = self.bind_namespace_apps(self.tenant["name"])

    def test_role_create_preserves_explicit_status(self):
        disabled_role = self.create_role(self.tenant_apps["role"], status=STATUS_DISABLE)
        self.assertEqual(disabled_role["status"], STATUS_DISABLE, "显式禁用状态应被保留")

    def test_role_can_hold_explicit_privileges(self):
        role = self.create_role(self.tenant_apps["role"])
        self.assertIn("privilege", role)
        self.assertTrue(role["privilege"], "role 应保留显式 privilege")
        self.assertEqual(role["privilege"][0]["module"], "*")
        self.assertEqual(role["privilege"][0]["uriPath"], "*")

    def test_role_update_changes_status_without_losing_identity(self):
        role = self.create_role(self.tenant_apps["role"])
        payload = dict(role)
        payload["description"] = "updated role"
        payload["status"] = STATUS_DISABLE

        updated_role = self.tenant_apps["role"].update_role(payload)
        self.assertIsNotNone(updated_role)
        self.assertEqual(updated_role["id"], role["id"])
        self.assertEqual(updated_role["description"], "updated role")
        self.assertEqual(updated_role["status"], STATUS_DISABLE)

        queried_role = self.tenant_apps["role"].query_role(role["id"])
        self.assertIsNotNone(queried_role)
        self.assertEqual(queried_role["status"], STATUS_DISABLE)

    def test_role_filter_isolated_by_namespace(self):
        role = self.create_role(self.tenant_apps["role"])
        filtered_roles = self.tenant_apps["role"].filter_role({"name": role["name"]})
        self.assertIsNotNone(filtered_roles)
        self.assertTrue(any(item["id"] == role["id"] for item in filtered_roles))

        panel_roles = self.role_app.filter_role({"name": role["name"]})
        if panel_roles:
            self.assertFalse(any(item["id"] == role["id"] for item in panel_roles), "panel namespace 查询不应直接返回 tenant role")

    def test_duplicate_role_name_is_rejected(self):
        role_name = "shared_role"
        first_role = self.create_role(self.tenant_apps["role"], name=role_name)
        payload = {
            "name": role_name,
            "description": "updated by duplicate create",
            "group": "changed",
            "privilege": first_role["privilege"],
            "status": STATUS_DISABLE,
        }
        second_role = self.tenant_apps["role"].create_role(payload)
        self.assertIsNone(second_role, "同 namespace 下重复 role 名称应被拒绝")


if __name__ == "__main__":
    unittest.main()
