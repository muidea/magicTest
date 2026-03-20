import unittest

from test_support import CasE2EBase, STATUS_DISABLE, STATUS_ENABLE, UNSET, unique_name


class NamespaceTestCase(CasE2EBase):
    def test_panel_namespace_is_default_governance_namespace(self):
        namespaces = self.namespace_app.filter_namespace({"name": self.panel_namespace})
        self.assertIsNotNone(namespaces, "查询 panel namespace 失败")
        self.assertTrue(namespaces, "panel namespace 不存在")

        panel_namespace = namespaces[0]
        self.assertEqual(panel_namespace["name"], self.panel_namespace)
        self.assertEqual(panel_namespace["scope"], "*", "panel 的治理 scope 应为全局")
        self.assertEqual(panel_namespace["status"], STATUS_ENABLE)

    def test_namespace_defaults_scope_to_its_own_name(self):
        namespace = self.create_namespace(scope=UNSET)
        self.assertEqual(namespace["scope"], namespace["name"], "未显式指定 scope 时应回填 namespace 自身名称")

    def test_super_namespace_can_manage_scoped_child_namespace(self):
        child_name = unique_name("child")
        manager_name = unique_name("manager")

        manager_namespace = self.create_namespace(name=manager_name, scope=f"{manager_name};{child_name}:*")
        child_namespace = self.create_namespace(name=child_name, scope=UNSET)

        manager_apps = self.bind_namespace_apps(manager_namespace["name"])
        update_payload = dict(child_namespace)
        update_payload["description"] = "managed by scoped namespace"

        updated_namespace = manager_apps["namespace"].update_namespace(update_payload)
        self.assertIsNotNone(updated_namespace, "超级 namespace 应能更新其 scope 内的子 namespace")
        self.assertEqual(updated_namespace["description"], "managed by scoped namespace")

        deleted_namespace = manager_apps["namespace"].delete_namespace(child_namespace["id"])
        self.assertIsNotNone(deleted_namespace, "超级 namespace 应能删除其 scope 内的子 namespace")
        self.assertEqual(deleted_namespace["id"], child_namespace["id"])

    def test_out_of_scope_namespace_cannot_manage_other_namespace(self):
        operator_namespace = self.create_namespace(name=unique_name("operator"), scope=UNSET)
        target_namespace = self.create_namespace(name=unique_name("target"), scope=UNSET)

        operator_apps = self.bind_namespace_apps(operator_namespace["name"])
        update_payload = dict(target_namespace)
        update_payload["description"] = "should be rejected"

        updated_namespace = operator_apps["namespace"].update_namespace(update_payload)
        self.assertIsNone(updated_namespace, "scope 外 namespace 不应能更新其他 namespace")

        queried_target = self.namespace_app.query_namespace(target_namespace["id"])
        self.assertIsNotNone(queried_target)
        self.assertNotEqual(queried_target["description"], "should be rejected")

    def test_disabled_namespace_remains_queryable_but_not_valid_for_management(self):
        namespace = self.create_namespace(name=unique_name("disabled"), scope=UNSET)
        update_payload = dict(namespace)
        update_payload["status"] = STATUS_DISABLE
        update_payload["description"] = "disabled namespace"

        disabled_namespace = self.namespace_app.update_namespace(update_payload)
        self.assertIsNotNone(disabled_namespace)
        self.assertEqual(disabled_namespace["status"], STATUS_DISABLE)

        disabled_apps = self.bind_namespace_apps(namespace["name"])
        managed_target = self.create_namespace(name=unique_name("managed"), scope=UNSET)
        target_update = dict(managed_target)
        target_update["description"] = "disabled operator should fail"

        updated_namespace = disabled_apps["namespace"].update_namespace(target_update)
        self.assertIsNone(updated_namespace, "禁用 namespace 不应拥有治理权限")

    def test_duplicate_namespace_name_is_rejected(self):
        namespace_name = unique_name("dup_namespace")
        first_namespace = self.create_namespace(name=namespace_name, scope=UNSET)
        self.assertIsNotNone(first_namespace)

        duplicate_namespace = self.namespace_app.create_namespace({
            "name": namespace_name,
            "description": "duplicate namespace",
            "status": STATUS_ENABLE,
            "startTime": first_namespace["startTime"],
            "expireTime": first_namespace["expireTime"],
        })
        self.assertIsNone(duplicate_namespace, "重复 namespace 名称应被拒绝")


if __name__ == "__main__":
    unittest.main()
