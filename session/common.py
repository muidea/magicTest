
class MagicEntity:
    def __init__(self, base_url, work_session):
        self.session = work_session
        self.base_url = base_url

    def filter(self, filter_val):
        url = '{0}/filter/'.format(self.base_url)

        val = self.session.post(url, filter_val)
        if val and val['errorCode'] == 0:
            return val['values']

        print('--------filter failed,url:{0}, filter:{1}-----------'.format(url, filter_val))
        print(val['reason'])
        return None

    def query(self, id_val):
        url = '{0}/query/{1}'.format(self.base_url, id_val)
        val = self.session.get(url)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------query failed, url:{0}-----------'.format(url))
        print(val['reason'])
        return None

    def create(self, param_val):
        url = '{0}/create/'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------create failed, url:{0}, param:{1}-----------'.format(url, param_val))
        print(val['reason'])
        return None

    def destroy(self, id_val):
        url = '{0}/destroy/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------destroy failed, url:{0}-----------'.format(url))
        print(val['reason'])
        return None

    def insert(self, param_val):
        url = '{0}/insert/'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------insert failed, url:{0}, param:{1}-----------'.format(url, param_val))
        print(val['reason'])
        return None

    def update(self, id_val, param_val):
        url = '{0}/update/{1}'.format(self.base_url, id_val)
        val = self.session.put(url, param_val)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------update failed, url:{0}, param:{1}-----------'.format(url, param_val))
        print(val['reason'])
        return None

    def delete(self, id_val):
        url = '{0}/delete/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------delete failed, url:{0}-----------'.format(url))
        print(val['reason'])
        return None

    def count(self):
        url = '{0}/count/'.format(self.base_url)
        val = self.session.get(url)
        if val and val['errorCode'] == 0:
            return val['total']

        print('--------count failed, url:{0}-----------'.format(url))
        print(val['reason'])
        return None
