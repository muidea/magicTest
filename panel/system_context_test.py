import unittest

from panel_test_support import PanelE2EBase


class SystemContextClient:
    def __init__(self, work_session):
        self.session = work_session

    def query(self, surface):
        response = self.session.get("/system/context/", {"surface": surface})
        if response is None or response.get("error") is not None:
            raise AssertionError(f"查询 system context 失败: surface={surface}, response={response}")
        return response.get("value") or {}


class PanelSystemContextTestCase(PanelE2EBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system_context_client = SystemContextClient(cls.work_session)

    @staticmethod
    def _prefixed_area_keys(area_visibility, prefix):
        return sorted(key for key in (area_visibility or {}) if key.startswith(prefix))

    def test_system_context_keeps_complete_authority_projection_across_surfaces(self):
        contexts = {
            surface: self.system_context_client.query(surface)
            for surface in ("panel", "portal", "workbench", "app", "other")
        }
        baseline = contexts["panel"]
        self.assertTrue(
            baseline.get("entryVisibility", {}).get("panel"),
            f"panel 管理员上下文应展示 panel 入口: {baseline}",
        )

        panel_keys = self._prefixed_area_keys(
            baseline.get("areaVisibility") or {}, "panel."
        )
        self.assertTrue(panel_keys, f"授权投影应包含 panel.* 功能区: {baseline}")

        for surface, context in contexts.items():
            self.assertEqual(
                context.get("surface"),
                surface,
                f"{surface} surface 不正确: {context}",
            )
            self.assertEqual(
                context.get("entryVisibility") or {},
                baseline.get("entryVisibility") or {},
                f"入口投影不应随 surface 漂移: surface={surface}, context={context}",
            )
            self.assertEqual(
                context.get("areaVisibility") or {},
                baseline.get("areaVisibility") or {},
                f"区域投影不应随 surface 漂移: surface={surface}, context={context}",
            )
            self.assertEqual(
                context.get("capabilities") or [],
                baseline.get("capabilities") or [],
                f"capability 投影不应随 surface 漂移: surface={surface}, context={context}",
            )

    def test_system_context_capabilities_are_stable_and_explicit(self):
        context = self.system_context_client.query("panel")
        capabilities = context.get("capabilities") or []
        self.assertTrue(capabilities, f"system context 缺少有效 capability: {context}")
        self.assertEqual(
            capabilities,
            sorted(set(capabilities)),
            f"capability 必须去空、去重并稳定排序: {capabilities}",
        )
        self.assertTrue(
            all(isinstance(item, str) and item.strip() for item in capabilities),
            f"capability 必须使用非空字符串: {capabilities}",
        )


if __name__ == "__main__":
    unittest.main()
