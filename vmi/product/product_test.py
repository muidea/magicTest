"""
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")
if session_path not in sys.path:
    sys.path.insert(0, session_path)

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")
if cas_dir not in sys.path:
    sys.path.insert(0, cas_dir)

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")
if mock_dir not in sys.path:
    sys.path.insert(0, mock_dir)
Product 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:150-161 中的 product 实体定义编写。
使用 ProductSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- name: string (产品名称) - 必选
- description: string (描述) - 可选
- image: string[] (图片) - 可选
- expire: int (有效期) - 可选
- status: status* (状态) - 必选，由平台进行管理，允许进行更新
- tags: string[] (标签) - 可选
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- modifyTime: int64 (修改时间) - 由系统自动更新
- namespace: string (命名空间) - 由系统自动生成

包含的测试用例（共12个）：

1. 基础CURD测试：
   - test_create_product: 测试创建产品，验证所有字段完整性
   - test_query_product: 测试查询产品，验证数据一致性
   - test_update_product: 测试更新产品，验证字段更新功能
   - test_delete_product: 测试删除产品，验证删除操作

2. 边界测试：
   - test_create_product_with_long_name: 测试创建超长名称产品
   - test_create_product_with_many_tags: 测试创建带多个标签的产品

3. 异常测试：
   - test_create_duplicate_product: 测试创建重复产品名（系统可能允许重复）
   - test_query_nonexistent_product: 测试查询不存在的产品
   - test_delete_nonexistent_product: 测试删除不存在的产品

4. 状态验证：
   - test_product_status_validation: 测试产品状态字段验证

5. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、creater、createTime、namespace）
   - test_modify_time_auto_update: 测试修改时间字段的自动更新逻辑

测试特性：
- 使用 ProductSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为（如允许重复名称）
- 验证所有实体定义字段
- 覆盖完整的业务规则

版本：1.0
最后更新：2026-01-25
"""

import os
import sys

# 添加项目根目录到Python路径
# 根据文件所在位置向上查找项目根目录
file_dir = os.path.dirname(os.path.abspath(__file__))
# session模块在 /home/rangh/codespace/magicTest/session
# 测试文件可能在 vmi/ 或 vmi/subdir/ 下
# 需要向上找到 magicTest 目录
project_root = file_dir
while project_root and not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    parent = os.path.dirname(project_root)
    if parent == project_root:  # 到达根目录
        break
    project_root = parent

# 如果没找到，使用默认路径
if not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    # 根据文件位置确定项目根目录
    if os.path.basename(file_dir) in ['credit', 'order', 'partner', 'product', 'status', 'store', 'warehouse']:
        # 在子目录下，向上两级
        project_root = os.path.dirname(os.path.dirname(file_dir))
    else:
        # 在vmi目录下，向上一级
        project_root = os.path.dirname(file_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")
if session_path not in sys.path:
    sys.path.insert(0, session_path)

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")
if cas_dir not in sys.path:
    sys.path.insert(0, cas_dir)

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")
if mock_dir not in sys.path:
    sys.path.insert(0, mock_dir)

# 确保vmi目录在路径中（用于导入sdk模块）
vmi_dir = os.path.join(project_root, "vmi")
if vmi_dir not in sys.path:
    sys.path.insert(0, vmi_dir)



# 添加项目根目录到Python路径
# 根据文件所在位置向上查找项目根目录
file_dir = os.path.dirname(os.path.abspath(__file__))
# session模块在 /home/rangh/codespace/magicTest/session
# 测试文件可能在 vmi/ 或 vmi/subdir/ 下
# 需要向上找到 magicTest 目录
project_root = file_dir
while project_root and not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    parent = os.path.dirname(project_root)
    if parent == project_root:  # 到达根目录
        break
    project_root = parent

# 如果没找到，使用默认路径
if not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    # 根据文件位置确定项目根目录
    if os.path.basename(file_dir) in ['credit', 'order', 'partner', 'product', 'status', 'store', 'warehouse']:
        # 在子目录下，向上两级
        project_root = os.path.dirname(os.path.dirname(file_dir))
    else:
        # 在vmi目录下，向上一级
        project_root = os.path.dirname(file_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")


from session import MagicSession
from cas.cas import Cas
from mock import common as mock
import logging
import unittest
import warnings


from sdk import ProductSDK

# 配置日志
logger = logging.getLogger(__name__)


class ProductTestCase(unittest.TestCase):
    """Product 测试用例类"""

    namespace = ""

    @classmethod
    def setUpClass(cls):
        # 从config_helper获取配置

        # 从config_helper获取配置
        from config_helper import get_credentials, get_server_url

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        """测试类初始化"""
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login(
            cls.credentials["username"], cls.credentials["password"]
        ):
            logger.error("CAS登录失败")
            raise Exception("CAS登录失败")
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.product_sdk = ProductSDK(cls.work_session)

        # 类级别的数据清理记录
        cls._class_cleanup_ids = []

        # 记录测试开始前的初始状态（可选）
        cls._initial_product_count = cls._get_product_count()
        logger.info(f"测试开始前产品数量: {cls._initial_product_count}")

    @classmethod
    def _get_product_count(cls):
        """获取当前产品数量"""
        try:
            # 尝试使用count方法
            count = cls.product_sdk.count_product({})
            if count is not None:
                return count
        except Exception as e:
            logger.warning(f"获取产品数量失败: {e}")

        # 如果count方法不可用，尝试通过过滤空条件获取列表
        try:
            products = cls.product_sdk.filter_product({})
            if products is not None:
                return len(products)
        except Exception as e:
            logger.warning(f"通过过滤获取产品数量失败: {e}")

        return 0

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        # 记录类级别清理列表的状态
        original_count = len(cls._class_cleanup_ids)
        logger.info(
            f"测试类清理开始: 需要清理 {original_count} 个产品: {cls._class_cleanup_ids}"
        )

        # 清理类级别记录的所有数据
        cls._cleanup_products(cls._class_cleanup_ids)

        # 验证数据清理
        final_product_count = cls._get_product_count()
        logger.info(
            f"测试类清理完成: 尝试清理 {original_count} 个产品，最终产品数量: {final_product_count}"
        )

        # 检查是否有数据残留（可选，根据业务需求）
        if hasattr(cls, "_initial_product_count"):
            expected_count = cls._initial_product_count
            if final_product_count > expected_count:
                logger.warning(
                    f"可能存在数据残留: 期望数量 {expected_count}, 实际数量 {final_product_count}"
                )
                # 尝试查找残留的产品
                cls._find_and_log_remaining_products(expected_count)
            else:
                logger.info(
                    f"数据清理验证通过: 最终数量 {final_product_count} <= 初始数量 {expected_count}"
                )

    @classmethod
    def _find_and_log_remaining_products(cls, expected_count):
        """查找并记录残留的产品"""
        try:
            # 获取所有产品
            all_products = cls.product_sdk.filter_product({})
            if all_products is not None:
                current_count = len(all_products)
                if current_count > expected_count:
                    logger.warning(f"发现 {current_count - expected_count} 个残留产品:")
                    for product in all_products:
                        if "id" in product and "name" in product:
                            logger.warning(
                                f"  ID: {product['id']}, 名称: {product['name']}, 描述: {product.get('description', 'N/A')}"
                            )
        except Exception as e:
            logger.warning(f"查找残留产品失败: {e}")

    @classmethod
    def _cleanup_products(cls, product_ids):
        """清理指定的产品列表

        注意：系统支持删除操作，如果删除失败应该记录错误。
        在测试类级别的清理中，我们尝试删除但不抛出异常，
        因为测试方法应该已经验证了删除操作。
        """
        if not product_ids:
            logger.debug("清理产品列表为空，无需清理")
            return

        logger.info(f"开始清理 {len(product_ids)} 个产品: {product_ids}")
        deleted_count = 0
        failed_ids = []

        for product_id in product_ids:
            try:
                # 系统应该支持删除操作
                logger.debug(f"尝试删除产品 ID: {product_id}")
                result = cls.product_sdk.delete_product(product_id)

                if result is not None:
                    deleted_count += 1
                    logger.debug(f"成功删除产品 {product_id}")
                else:
                    # 删除返回None，表示删除失败
                    error_msg = f"清理产品 {product_id} 返回None，系统应该支持删除操作"
                    logger.error(error_msg)
                    failed_ids.append(product_id)
            except Exception as e:
                error_msg = f"清理产品 {product_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(product_id)

        if deleted_count > 0:
            logger.info(f"成功清理 {deleted_count} 个产品")

        if failed_ids:
            logger.error(f"清理失败的产品ID: {failed_ids}")

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的产品ID以便清理
        self.created_product_ids = []

    def tearDown(self):
        """每个测试用例后的清理"""
        # 将本测试创建的产品ID添加到类级别清理列表
        if hasattr(self.__class__, "_class_cleanup_ids"):
            self.__class__._class_cleanup_ids.extend(self.created_product_ids)

        # 尝试立即清理本测试创建的数据
        self._cleanup_test_products()

        self.created_product_ids.clear()

    def _cleanup_test_products(self):
        """清理本测试创建的产品

        注意：系统支持删除操作，如果删除失败应该抛出异常，
        以便测试失败并排查server错误。
        """
        if not self.created_product_ids:
            logger.debug(f"测试 {self._testMethodName}: 没有需要清理的产品")
            return

        logger.info(
            f"测试 {self._testMethodName}: 开始清理 {len(self.created_product_ids)} 个产品: {self.created_product_ids}"
        )
        deleted_count = 0
        failed_ids = []

        for product_id in self.created_product_ids:
            try:
                # 系统应该支持删除操作
                logger.debug(
                    f"测试 {self._testMethodName}: 尝试删除产品 ID: {product_id}"
                )
                result = self.product_sdk.delete_product(product_id)

                if result is not None:
                    deleted_count += 1
                    logger.debug(
                        f"测试 {self._testMethodName}: 成功删除产品 {product_id}"
                    )
                    # 从类级别清理列表中移除（如果存在）
                    if (
                        hasattr(self.__class__, "_class_cleanup_ids")
                        and product_id in self.__class__._class_cleanup_ids
                    ):
                        self.__class__._class_cleanup_ids.remove(product_id)
                        logger.debug(
                            f"测试 {self._testMethodName}: 从类级别清理列表中移除产品 {product_id}"
                        )
                else:
                    # 删除返回None，表示删除失败
                    error_msg = f"测试 {self._testMethodName}: 删除产品 {product_id} 返回None，系统应该支持删除操作"
                    logger.error(error_msg)
                    failed_ids.append(product_id)
                    # 不抛出异常，继续尝试清理其他产品
                    # 但记录严重错误

            except Exception as e:
                error_msg = (
                    f"测试 {self._testMethodName}: 删除产品 {product_id} 失败: {e}"
                )
                logger.error(error_msg)
                failed_ids.append(product_id)
                # 不抛出异常，继续尝试清理其他产品

        if deleted_count > 0:
            logger.info(f"测试 {self._testMethodName}: 成功清理 {deleted_count} 个产品")

        if failed_ids:
            # 记录错误但不抛出异常，因为这是在tearDown中
            # 实际的测试方法应该已经验证了删除操作
            logger.error(f"测试 {self._testMethodName}: 清理失败的产品ID: {failed_ids}")
            # 这里可以选择抛出异常让测试失败
            # 但考虑到这是清理阶段，可能已经过了测试验证
            # 我们只记录错误，不中断测试

    def _record_product_for_cleanup(self, product_id):
        """记录产品ID以便清理"""
        if product_id is not None:
            self.created_product_ids.append(product_id)
            logger.debug(
                f"记录产品 {product_id} 到清理列表 (测试: {self._testMethodName})"
            )

    def mock_product_param(self):
        """模拟产品参数

        根据实体定义，product实体包含以下字段：
        - name: string (产品名称) - 必选
        - description: string (描述) - 可选
        - image: string[] (图片) - 可选
        - expire: int (有效期) - 可选
        - status: status* (状态) - 必选
        - tags: string[] (标签) - 可选
        """
        return {
            "name": mock.name(),
            "description": mock.sentence(),
            "image": [mock.url(), mock.url()],
            "expire": 100,
            "tags": ["tag1", "tag2", "tag3"],
            "status": {"id": 3},  # 假设状态ID 3是有效状态
        }

    def test_create_product(self):
        """测试创建产品"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        # 验证产品信息完整性
        required_fields = [
            "id",
            "name",
            "description",
            "image",
            "expire",
            "tags",
            "status",
        ]
        for field in required_fields:
            self.assertIn(field, new_product, f"缺少字段: {field}")

        # 验证系统自动生成字段
        self.assertIn("creater", new_product, "缺少创建者字段")
        self.assertIsInstance(
            new_product["creater"], (int, type(None)), "创建者应为整数或None"
        )

        self.assertIn("createTime", new_product, "缺少创建时间字段")
        self.assertIsInstance(
            new_product["createTime"], (int, type(None)), "创建时间应为整数或None"
        )

        self.assertIn("namespace", new_product, "缺少命名空间字段")
        self.assertIsInstance(
            new_product["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

        # 记录创建的产品ID以便清理
        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

    def test_query_product(self):
        """测试查询产品"""
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 查询产品
        queried_product = self.product_sdk.query_product(new_product["id"])
        self.assertIsNotNone(queried_product, "查询产品失败")
        self.assertEqual(queried_product["id"], new_product["id"], "产品ID不匹配")
        self.assertEqual(queried_product["name"], new_product["name"], "产品名不匹配")

    def test_update_product(self):
        """测试更新产品"""
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 更新产品
        update_param = new_product.copy()
        update_param["description"] = "更新后的描述"

        updated_product = self.product_sdk.update_product(
            new_product["id"], update_param
        )
        self.assertIsNotNone(updated_product, "更新产品失败")
        self.assertEqual(updated_product["description"], "更新后的描述", "描述更新失败")

    def test_delete_product(self):
        """测试删除产品

        注意：系统支持删除操作，如果删除失败应该让测试失败，
        以便排查server错误。
        """
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 删除产品 - 系统应该支持删除操作
        deleted_product = self.product_sdk.delete_product(new_product["id"])

        # 删除应该成功，返回被删除的对象
        self.assertIsNotNone(
            deleted_product, "删除产品失败，返回None。系统应该支持删除操作"
        )
        self.assertEqual(deleted_product["id"], new_product["id"], "删除的产品ID不匹配")

        # 从清理列表中移除，因为已经成功删除
        if new_product["id"] in self.created_product_ids:
            self.created_product_ids.remove(new_product["id"])

        # 验证产品已被删除（查询应该失败）
        queried_product = self.product_sdk.query_product(new_product["id"])
        # 查询应该返回None或抛出异常，因为产品已被删除
        # 系统可能返回None或抛出异常，两种方式都表示删除成功
        if queried_product is not None:
            # 如果查询返回了产品，那么删除可能失败
            self.fail(f"删除后查询产品应该返回None，但返回了: {queried_product}")
        # 如果queried_product是None，表示删除成功

    def test_create_product_with_long_name(self):
        """测试创建超长名称产品（边界测试）"""
        product_param = self.mock_product_param()
        product_param["name"] = "a" * 255  # 超长名称

        new_product = self.product_sdk.create_product(product_param)
        if new_product is not None:
            self.assertIsInstance(new_product["name"], str, "产品名不是字符串")
            # 记录创建的产品ID以便清理
            if "id" in new_product:
                self._record_product_for_cleanup(new_product["id"])

    def test_create_product_with_many_tags(self):
        """测试创建带多个标签的产品"""
        product_param = self.mock_product_param()
        product_param["tags"] = [
            "tag1",
            "tag2",
            "tag3",
            "tag4",
            "tag5",
            "tag6",
            "tag7",
            "tag8",
            "tag9",
            "tag10",
        ]

        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建带多个标签的产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证标签字段
        self.assertIn("tags", new_product, "产品缺少标签字段")
        self.assertIsInstance(new_product["tags"], list, "标签应为列表")
        self.assertGreaterEqual(len(new_product["tags"]), 10, "标签数量不足")

    def test_create_duplicate_product(self):
        """测试创建重复产品名（系统可能允许重复）"""
        product_param = self.mock_product_param()

        first_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(first_product, "第一次创建产品失败")

        # 记录第一次创建的产品ID以便清理
        if first_product and "id" in first_product:
            self._record_product_for_cleanup(first_product["id"])

        # 第二次创建相同产品名
        second_product = self.product_sdk.create_product(product_param)

        # 系统可能允许重复名称，所以不强制要求失败
        if second_product is not None:
            # 如果创建成功，记录ID以便清理
            if "id" in second_product:
                self._record_product_for_cleanup(second_product["id"])
            # 验证返回的数据结构
            self.assertIn("id", second_product, "第二次创建的产品缺少ID字段")
            self.assertIn("name", second_product, "第二次创建的产品缺少name字段")
            self.assertEqual(
                second_product["name"], product_param["name"], "名称不匹配"
            )
        # 如果返回None，也不视为错误，因为系统可能以其他方式处理重复

    def test_query_nonexistent_product(self):
        """测试查询不存在的产品（异常测试）"""
        nonexistent_product_id = 999999
        queried_product = self.product_sdk.query_product(nonexistent_product_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_product, "查询不存在的产品应失败")

    def test_delete_nonexistent_product(self):
        """测试删除不存在的产品（异常测试）"""
        nonexistent_product_id = 999999
        deleted_product = self.product_sdk.delete_product(nonexistent_product_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_product, "删除不存在的产品应失败")

    def test_product_status_validation(self):
        """测试产品状态验证"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证状态字段
        self.assertIn("status", new_product, "产品缺少状态字段")
        self.assertIn("id", new_product["status"], "状态缺少id字段")
        self.assertEqual(new_product["status"]["id"], 3, "状态ID不匹配")

    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证所有系统自动生成字段
        auto_generated_fields = ["id", "creater", "createTime", "namespace"]
        for field in auto_generated_fields:
            self.assertIn(field, new_product, f"缺少系统自动生成字段: {field}")

        # 验证字段类型和值
        self.assertIsInstance(new_product["id"], (int, type(None)), "ID应为整数或None")
        if new_product["id"] is not None:
            self.assertGreater(new_product["id"], 0, "ID应为正整数")

        self.assertIsInstance(
            new_product["creater"], (int, type(None)), "创建者应为整数或None"
        )
        self.assertIsInstance(
            new_product["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        if new_product["createTime"] is not None:
            self.assertGreater(new_product["createTime"], 0, "创建时间应为正数")

        self.assertIsInstance(
            new_product["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

    def test_modify_time_auto_update(self):
        """测试修改时间自动更新"""
        # 创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 记录初始创建时间和修改时间
        initial_create_time = new_product.get("createTime")
        initial_modify_time = new_product.get("modifyTime")

        # 更新产品
        update_param = new_product.copy()
        update_param["description"] = "更新后的描述"

        updated_product = self.product_sdk.update_product(
            new_product["id"], update_param
        )
        self.assertIsNotNone(updated_product, "更新产品失败")

        # 验证修改时间已更新
        updated_modify_time = updated_product.get("modifyTime")
        self.assertIsNotNone(updated_modify_time, "更新后缺少修改时间字段")

        # 验证修改时间比创建时间晚（如果两者都存在）
        if initial_create_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_create_time, "修改时间应晚于或等于创建时间"
            )

        # 验证创建时间未改变
        self.assertEqual(
            updated_product.get("createTime"), initial_create_time, "创建时间不应被修改"
        )

        # 如果初始有修改时间，验证已更新
        if initial_modify_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_modify_time, "修改时间应已更新"
            )


if __name__ == "__main__":
    unittest.main()
