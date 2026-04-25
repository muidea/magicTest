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

    def test_system_context_filters_panel_and_portal_areas_by_surface(self):
        panel_context = self.system_context_client.query("panel")
        self.assertEqual(panel_context.get("surface"), "panel", f"panel surface 不正确: {panel_context}")
        self.assertTrue(
            panel_context.get("entryVisibility", {}).get("panel"),
            f"panel 管理员上下文应展示 panel 入口: {panel_context}",
        )

        panel_area_visibility = panel_context.get("areaVisibility") or {}
        self.assertTrue(
            self._prefixed_area_keys(panel_area_visibility, "panel."),
            f"panel surface 应返回 panel.* 功能区: {panel_context}",
        )
        self.assertFalse(
            self._prefixed_area_keys(panel_area_visibility, "portal."),
            f"panel surface 不应返回 portal.* 功能区: {panel_context}",
        )

        portal_context = self.system_context_client.query("portal")
        self.assertEqual(portal_context.get("surface"), "portal", f"portal surface 不正确: {portal_context}")
        self.assertTrue(
            portal_context.get("entryVisibility", {}).get("panel"),
            f"panel 管理员上下文仍应保留 panel 入口可见性: {portal_context}",
        )

        portal_area_visibility = portal_context.get("areaVisibility") or {}
        self.assertTrue(
            self._prefixed_area_keys(portal_area_visibility, "portal."),
            f"portal surface 应返回 portal.* 功能区: {portal_context}",
        )
        self.assertFalse(
            self._prefixed_area_keys(portal_area_visibility, "panel."),
            f"portal surface 不应返回 panel.* 功能区: {portal_context}",
        )

    def test_system_context_non_page_surfaces_skip_panel_and_portal_page_areas(self):
        for surface in ("workbench", "app", "other"):
            context = self.system_context_client.query(surface)
            self.assertEqual(context.get("surface"), surface, f"{surface} surface 不正确: {context}")
            area_visibility = context.get("areaVisibility") or {}
            panel_keys = self._prefixed_area_keys(area_visibility, "panel.")
            portal_keys = self._prefixed_area_keys(area_visibility, "portal.")
            self.assertFalse(
                panel_keys,
                f"{surface} surface 不应返回 panel.* 页面功能区: surface={surface}, context={context}",
            )
            self.assertFalse(
                portal_keys,
                f"{surface} surface 不应返回 portal.* 页面功能区: surface={surface}, context={context}",
            )


if __name__ == "__main__":
    unittest.main()
