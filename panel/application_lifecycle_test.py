from panel_test_support import PanelE2EBase
from lifecycle import LifecycleClient

class PanelApplicationLifecycleTestCase(PanelE2EBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lifecycle_client = LifecycleClient(cls.work_session)

    def test_fetch_running_applications(self):
        app_list = self.lifecycle_client.fetch_running_applications()
        self.assertIsNotNone(app_list, "查询运行中应用失败")
        self.assertIsInstance(app_list, list, "运行中应用结果不是列表")
