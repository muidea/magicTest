
class MagicEntity:
    def __init__(self, base_url, work_session):
        self.session = work_session
        self.base_url = base_url

    def filter(self, filter_val):
        url = '{0}s'.format(self.base_url)

        val = self.session.post(url, filter_val)
        if val and (val.get('error') is None):
            return val['values']

        print('--------filter validation error,url:{0}, filter:{1}-----------'.format(url, filter_val))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def query(self, id_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.get(url)
        if val and (val.get('error') is None):
            return val['value']

        print('--------query execution error, url:{0}-----------'.format(url))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def create(self, param_val):
        url = '{0}s'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        print('--------create operation error, url:{0}, param:{1}-----------'.format(url, param_val))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def destroy(self, id_val):
        url = '{0}/destroy/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and (val.get('error') is None):
            return val['value']

        print('--------destroy execution error, url:{0}-----------'.format(url))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def insert(self, param_val):
        url = '{0}/insert/'.format(self.base_url)
        val = self.session.post(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        print('--------insert operation error, url:{0}, param:{1}-----------'.format(url, param_val))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def update(self, id_val, param_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.put(url, param_val)
        if val and (val.get('error') is None):
            return val['value']

        print('--------update validation error, url:{0}, param:{1}-----------'.format(url, param_val))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def delete(self, id_val):
        url = '{0}s/{1}'.format(self.base_url, id_val)
        val = self.session.delete(url)
        if val and (val.get('error') is None):
            return val['value']

        print('--------delete execution error, url:{0}-----------'.format(url))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None

    def count(self):
        url = '{0}/count/'.format(self.base_url)
        val = self.session.get(url)
        if val and (val.get('error') is None):
            return val['total']

        print('--------count operation error, url:{0}-----------'.format(url))
        print('Code: {0}, Message: {1}'.format(val['error']['code'], val['error']['message']))
        return None
