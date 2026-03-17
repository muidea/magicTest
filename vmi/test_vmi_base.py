#!/usr/bin/env python3
"""
VMI 模块测试基类
为所有模块测试提供统一的初始化和清理逻辑

使用方法：
    from test_vmi_base import VMITestCase

    class TestStore(VMITestCase):
        def test_create_store(self):
            # 使用 self.store_sdk
            pass
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)


from session import MagicSession
from cas.cas import Cas
import logging
import unittest
import warnings
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

try:
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
except Exception:  # pragma: no cover - optional dependency in local tooling only
    urllib3 = None
    InsecureRequestWarning = None


logger = logging.getLogger(__name__)


class VMITestCase(unittest.TestCase):
    """VMI 模块测试基类

    提供统一的：
    1. 会话初始化和登录
    2. SDK 实例管理
    3. 测试数据清理
    4. 便捷的断言方法
    """

    namespace = ""

    _cleanup_ids: Dict[str, List[str]] = {}

    @classmethod
    def log_suite_start(cls, message: Optional[str] = None) -> None:
        logger.info("%s", message or f"{cls.__name__} 测试开始")

    @classmethod
    def log_suite_end(cls, message: Optional[str] = None) -> None:
        logger.info("%s", message or f"{cls.__name__} 测试结束")

    def log_test_step(self, message: str) -> None:
        logger.info("%s", message)

    def log_test_success(self, message: str) -> None:
        logger.info("%s", message)

    def log_test_observation(self, message: str) -> None:
        logger.warning("%s", message)

    @staticmethod
    def _resolve_callable(
        owner: Any, callable_ref: Union[str, Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Resolve and invoke a callable or owner-bound method name."""
        target = getattr(owner, callable_ref) if isinstance(callable_ref, str) else callable_ref
        return target(*args, **kwargs)

    @staticmethod
    def build_cleanup_registry(*entity_types: str) -> Dict[str, List[int]]:
        """Create a cleanup registry with stable entity buckets."""
        return {entity_type: [] for entity_type in entity_types}

    @staticmethod
    def clear_cleanup_registry(registry: Dict[str, List[int]]) -> None:
        """Clear all buckets in a cleanup registry in place."""
        for entity_ids in registry.values():
            entity_ids.clear()

    @staticmethod
    def merge_cleanup_registry(
        target: Dict[str, List[int]], source: Dict[str, List[int]]
    ) -> None:
        """Append per-test cleanup ids into the class-level cleanup registry."""
        for entity_type, entity_ids in source.items():
            if entity_ids:
                target.setdefault(entity_type, []).extend(entity_ids)

    @classmethod
    def cleanup_registry_entries(
        cls,
        registry: Dict[str, List[int]],
        cleanup_plan: Iterable[Tuple[str, Union[str, Any], str]],
        *,
        owner: Optional[Any] = None,
        remove_from: Optional[Dict[str, List[int]]] = None,
        log_prefix: Optional[str] = None,
    ) -> None:
        """Delete registered entities following the supplied cleanup plan."""
        owner = owner or cls
        prefix = f"{log_prefix}: " if log_prefix else ""

        for entity_type, sdk_ref, entity_name in cleanup_plan:
            entity_ids = registry.get(entity_type, [])
            if not entity_ids:
                logger.debug("%s没有需要清理的%s", prefix, entity_name)
                continue

            sdk = getattr(owner, sdk_ref) if isinstance(sdk_ref, str) else sdk_ref
            deleted_count = 0
            failed_ids: List[int] = []

            logger.info(
                "%s开始清理 %s 个%s: %s",
                prefix,
                len(entity_ids),
                entity_name,
                entity_ids,
            )

            for entity_id in list(entity_ids):
                try:
                    logger.debug("%s尝试删除%s ID: %s", prefix, entity_name, entity_id)
                    result = sdk.delete(entity_id)
                    if result is not None:
                        deleted_count += 1
                        logger.debug("%s成功删除%s %s", prefix, entity_name, entity_id)
                    else:
                        logger.debug(
                            "%s删除%s %s 返回None，视为已不存在",
                            prefix,
                            entity_name,
                            entity_id,
                        )

                    if remove_from and entity_id in remove_from.get(entity_type, []):
                        remove_from[entity_type].remove(entity_id)
                except Exception as err:
                    logger.error(
                        "%s删除%s %s 失败: %s", prefix, entity_name, entity_id, err
                    )
                    failed_ids.append(entity_id)

            if deleted_count > 0:
                logger.info("%s成功清理 %s 个%s", prefix, deleted_count, entity_name)

            if failed_ids:
                logger.warning("%s清理%s异常ID: %s", prefix, entity_name, failed_ids)

    @classmethod
    def cleanup_id_list(
        cls,
        entity_ids: List[int],
        sdk_ref: Union[str, Any],
        entity_name: str,
        *,
        owner: Optional[Any] = None,
        remove_from: Optional[List[int]] = None,
        log_prefix: Optional[str] = None,
    ) -> None:
        """Delete a flat id list for simple single-entity test suites."""
        owner = owner or cls
        prefix = f"{log_prefix}: " if log_prefix else ""
        if not entity_ids:
            logger.debug("%s没有需要清理的%s", prefix, entity_name)
            return

        sdk = getattr(owner, sdk_ref) if isinstance(sdk_ref, str) else sdk_ref
        deleted_count = 0
        failed_ids: List[int] = []

        logger.info(
            "%s开始清理 %s 个%s: %s",
            prefix,
            len(entity_ids),
            entity_name,
            entity_ids,
        )

        for entity_id in list(entity_ids):
            try:
                logger.debug("%s尝试删除%s ID: %s", prefix, entity_name, entity_id)
                result = sdk.delete(entity_id)
                if result is not None:
                    deleted_count += 1
                    logger.debug("%s成功删除%s %s", prefix, entity_name, entity_id)
                else:
                    logger.debug(
                        "%s删除%s %s 返回None，视为已不存在",
                        prefix,
                        entity_name,
                        entity_id,
                    )

                if remove_from and entity_id in remove_from:
                    remove_from.remove(entity_id)
            except Exception as err:
                logger.error("%s删除%s %s 失败: %s", prefix, entity_name, entity_id, err)
                failed_ids.append(entity_id)

        if deleted_count > 0:
            logger.info("%s成功清理 %s 个%s", prefix, deleted_count, entity_name)

        if failed_ids:
            logger.warning("%s清理%s异常ID: %s", prefix, entity_name, failed_ids)

    @classmethod
    def get_entity_count(
        cls,
        sdk_ref: Union[str, Any],
        count_method_name: str,
        filter_method_name: str,
        *,
        entity_name: str,
        owner: Optional[Any] = None,
        count_args: Tuple[Any, ...] = (),
        filter_args: Tuple[Any, ...] = (),
    ) -> int:
        """Get entity count via count API first, then fall back to filter length."""
        owner = owner or cls
        sdk = getattr(owner, sdk_ref) if isinstance(sdk_ref, str) else sdk_ref

        try:
            count = getattr(sdk, count_method_name)(*count_args)
            if count is not None:
                return count
        except Exception as err:
            logger.warning("获取%s数量失败: %s", entity_name, err)

        try:
            entities = getattr(sdk, filter_method_name)(*filter_args)
            if entities is not None:
                return len(entities)
        except Exception as err:
            logger.warning("通过过滤获取%s数量失败: %s", entity_name, err)

        return 0

    @classmethod
    def record_initial_count(
        cls,
        attr_name: str,
        count_getter: Union[str, Any],
        *,
        entity_name: str,
        owner: Optional[Any] = None,
    ) -> int:
        """Capture the initial entity count for later cleanup verification."""
        owner = owner or cls
        count = cls._resolve_callable(owner, count_getter)
        setattr(cls, attr_name, count)
        logger.info("测试开始前%s数量: %s", entity_name, count)
        return count

    @classmethod
    def verify_cleanup_count(
        cls,
        initial_count_attr: str,
        count_getter: Union[str, Any],
        *,
        entity_name: str,
        owner: Optional[Any] = None,
        remaining_sdk_ref: Optional[Union[str, Any]] = None,
        remaining_filter_method_name: Optional[str] = None,
        remaining_filter_args: Tuple[Any, ...] = (),
        remaining_describe: Optional[Any] = None,
    ) -> int:
        """Verify that class-level cleanup restored the entity count baseline."""
        owner = owner or cls
        final_count = cls._resolve_callable(owner, count_getter)
        logger.info("测试类清理完成: 最终%s数量: %s", entity_name, final_count)

        if not hasattr(cls, initial_count_attr):
            return final_count

        expected_count = getattr(cls, initial_count_attr)
        if final_count > expected_count:
            logger.warning(
                "可能存在%s数据残留: 期望数量 %s, 实际数量 %s",
                entity_name,
                expected_count,
                final_count,
            )
            if remaining_sdk_ref and remaining_filter_method_name:
                cls.log_remaining_entities(
                    remaining_sdk_ref,
                    remaining_filter_method_name,
                    expected_count,
                    entity_name=entity_name,
                    owner=owner,
                    filter_args=remaining_filter_args,
                    describe=remaining_describe,
                )
        else:
            logger.info(
                "数据清理验证通过: 最终数量 %s <= 初始数量 %s",
                final_count,
                expected_count,
            )

        return final_count

    @classmethod
    def log_remaining_entities(
        cls,
        sdk_ref: Union[str, Any],
        filter_method_name: str,
        expected_count: int,
        *,
        entity_name: str,
        owner: Optional[Any] = None,
        filter_args: Tuple[Any, ...] = (),
        describe: Optional[Any] = None,
    ) -> None:
        """Log remaining entities when final count is greater than expected."""
        owner = owner or cls
        sdk = getattr(owner, sdk_ref) if isinstance(sdk_ref, str) else sdk_ref

        try:
            entities = getattr(sdk, filter_method_name)(*filter_args) or []
            current_count = len(entities)
            if current_count <= expected_count:
                return

            logger.warning(
                "发现 %s 个残留%s:", current_count - expected_count, entity_name
            )
            if not describe:
                return

            for entity in entities:
                description = describe(entity)
                if description:
                    logger.warning("  %s", description)
        except Exception as err:
            logger.warning("查找残留%s失败: %s", entity_name, err)

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        from config_helper import get_credentials, get_server_url

        warnings.simplefilter("ignore", ResourceWarning)
        if urllib3 and InsecureRequestWarning:
            warnings.filterwarnings("ignore", category=InsecureRequestWarning)
            urllib3.disable_warnings(InsecureRequestWarning)

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)

        if not cls.cas_session.login(
            cls.credentials["username"], cls.credentials["password"]
        ):
            logger.error("CAS登录失败")
            raise Exception("CAS登录失败")

        cls.work_session.bind_token(cls.cas_session.get_session_token())

        cls._cleanup_ids = {}
        cls._init_sdk()

        logger.info(f"{cls.__name__}: 初始化完成")

    @classmethod
    def _init_sdk(cls):
        """初始化SDK实例 - 子类可重写"""
        pass

    @classmethod
    def tearDownClass(cls):
        """测试类清理 - 清理测试数据"""
        cls._cleanup_test_data()

        if hasattr(cls, "work_session"):
            try:
                cls.cas_session.logout()
            except:
                pass

        logger.info(f"{cls.__name__}: 清理完成")

    @classmethod
    def _cleanup_test_data(cls):
        """清理测试数据 - 子类可重写"""
        pass

    @classmethod
    def _register_cleanup(cls, entity_type: str, entity_id: str):
        """注册需要清理的实体ID"""
        if entity_type not in cls._cleanup_ids:
            cls._cleanup_ids[entity_type] = []
        cls._cleanup_ids[entity_type].append(entity_id)

    def assertEntityCreated(self, entity: Dict[str, Any], entity_type: str = "实体"):
        """断言实体创建成功"""
        self.assertIsNotNone(entity, f"{entity_type}创建失败：返回None")
        self.assertIn("id", entity, f"{entity_type}创建失败：缺少id字段")
        self._register_cleanup(entity_type, entity["id"])

    def assertEntityField(
        self, entity: Dict[str, Any], field: str, expected_value: Any = None
    ):
        """断言实体字段值"""
        self.assertIn(field, entity, f"实体缺少字段: {field}")
        if expected_value is not None:
            self.assertEqual(
                entity[field],
                expected_value,
                f"字段{field}值不匹配: 期望{expected_value}, 实际{entity[field]}",
            )

    def assertEntityNotEmpty(self, entity: Dict[str, Any], fields: List[str]):
        """断言实体字段非空"""
        for field in fields:
            self.assertIn(field, entity, f"实体缺少字段: {field}")
            self.assertIsNotNone(entity[field], f"字段{field}为空")
            if isinstance(entity[field], str):
                self.assertTrue(len(entity[field]) > 0, f"字段{field}为空字符串")


class StoreTestCase(VMITestCase):
    """Store 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ShelfSDK, StoreSDK

        cls.store_sdk = StoreSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)


class ProductTestCase(VMITestCase):
    """Product 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ProductInfoSDK, ProductSDK

        cls.product_sdk = ProductSDK(cls.work_session)
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)


class WarehouseTestCase(VMITestCase):
    """Warehouse 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ShelfSDK, WarehouseSDK

        cls.warehouse_sdk = WarehouseSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)


class CreditTestCase(VMITestCase):
    """Credit 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import CreditSDK, PartnerSDK

        cls.credit_sdk = CreditSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)


class OrderTestCase(VMITestCase):
    """Order 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import GoodsItemSDK, OrderSDK

        cls.order_sdk = OrderSDK(cls.work_session)
        cls.goods_item_sdk = GoodsItemSDK(cls.work_session)


class PartnerTestCase(VMITestCase):
    """Partner 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import PartnerSDK

        cls.partner_sdk = PartnerSDK(cls.work_session)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("VMI 模块测试基类")
    logger.info("提供 VMITestCase 及各模块专用测试基类")
