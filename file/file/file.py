"""File"""

import os

from session import session

class File:
    """File"""

    def __init__(self, scope, source, path, work_session):
        self.scope = scope
        self.source = source
        self.path = path
        self.session = work_session

    def filter_file(self, param=None):
        if self.source:
            if not param:
                param = {'fileSource': self.source}
            else:
                param['fileSource'] = self.source
        if self.scope:
            if not param:
                param = {'fileScope': self.scope}
            else:
                param['fileScope'] = self.scope

        val = self.session.get('/api/v1/static/file/filter/', param)
        if val and val['errorCode'] == 0:
            return val['values']
        print('--------filter_file-----------')
        print(val['reason'])
        return None

    def query_file(self, file_id, param = None):
        if not param:
            param = {'fileSource': self.source}
        else:
            param['fileSource'] = self.source
        if self.scope:
            if not param:
                param = {'fileScope': self.scope}
            else:
                param['fileScope'] = self.scope

        val = self.session.get('/api/v1/static/file/query/{0}'.format(file_id), param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------query_file-----------')
        print(val['reason'])
        return None

    def delete_file(self, file_id, param = None):
        if not param:
            param = {'fileSource': self.source}
        else:
            param['fileSource'] = self.source
        if self.scope:
            if not param:
                param = {'fileScope': self.scope}
            else:
                param['fileScope'] = self.scope

        val = self.session.delete('/api/v1/static/file/delete/{0}'.format(file_id), param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------delete_file-----------')
        print(val['reason'])
        return None

    def upload_file(self, file_path, params = None):
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope
        if self.path:
            if not params:
                params = {'filePath': self.path}
            else:
                params['filePath'] = self.path
        if not params:
            params = {'key-name': 'file'}
        else:
            params['key-name'] = 'file'

        files = {'file': open(file_path, 'rb')}
        val = self.session.upload('/static/file/', files=files, params=params)
        if val and val['errorCode'] == 0:
            return val['value']
        print('--------upload_file-----------')
        print(val['reason'])
        return None

    def download_file(self, file_token, file_path):
        params = {'fileToken': file_token, 'fileSource': self.source}
        val = self.session.download('/static/file/', file_path, params)
        if val:
            return val

        print('--------download_file failed-----------')
        return None


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = File("abc","xyz", None, work_session)
    file_path = "./file/file.py"
    new_file = app.upload_file(file_path)
    if not new_file:
        print('upload file failed')
        return False

    file_list = app.filter_file()
    if not file_list or len(file_list) < 0:
        print('filter file failed')
        return False

    new_file_path = "./file/file.py_new"
    file_val = app.download_file(new_file['token'], new_file_path)
    if not file_val:
        print('download file failed')
        return False
    os.remove(new_file_path)

    cur_file = app.query_file(new_file['id'])
    if not cur_file:
        print('query file failed')
        return False
    if cur_file['token'] != new_file['token']:
        print('query file failed, mismatch file')
        return False

    old_file = app.delete_file(new_file['id'])
    if not old_file:
        print('delete file failed')
        return False

    return True
