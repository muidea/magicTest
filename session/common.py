
import logging

# 配置日志
logger = logging.getLogger(__name__)

class MagicEntity:
    def __init__(self, base_url, work_session):
        self.session = work_session
        self.base_url = base_url

    def filter(self, filter_val):
        url = '{0}s'.format(self.base_url)

        val = self.session.get(url, filter_val)
        if val and (val.get('error') is None):
            return val['values']

        if val:
            logger.error('过滤验证错误, URL: %s, 过滤条件: %s', url, filter_val)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('过滤请求失败, URL: %s, 过滤条件: %s', url, filter_val)
        return None

    def query(self, id_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.get(url)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('查询执行错误, URL: %s', url)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('查询请求失败, URL: %s', url)
        return None

    def create(self, param_val):
        url = '{0}s'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('创建操作错误, URL: %s, 参数: %s', url, param_val)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('创建请求失败, URL: %s, 参数: %s', url, param_val)
        return None

    def destroy(self, id_val):
        url = '{0}/destroy/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('销毁执行错误, URL: %s', url)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('销毁请求失败, URL: %s', url)
        return None

    def insert(self, param_val):
        url = '{0}s'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('插入操作错误, URL: %s, 参数: %s', url, param_val)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('插入请求失败, URL: %s, 参数: %s', url, param_val)
        return None

    def update(self, id_val, param_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.put(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('更新验证错误, URL: %s, 参数: %s', url, param_val)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('更新请求失败, URL: %s, 参数: %s', url, param_val)
        return None

    def delete(self, id_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and (val.get('error') is None):
            return val['value']

        if val:
            logger.error('删除执行错误, URL: %s', url)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('删除请求失败, URL: %s', url)
        return None

    def count(self):
        url = '{0}/count/'.format(self.base_url)
        val = self.session.get(url)
        if val and (val.get('error') is None):
            return val['total']

        if val:
            logger.error('计数操作错误, URL: %s', url)
            logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
        else:
            logger.error('计数请求失败, URL: %s', url)
        return None
