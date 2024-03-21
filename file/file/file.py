"""File"""

from session import session

class File:
    """File"""

    def __init__(self, source, work_session):
        self.source = source
        self.session = work_session

    def filter_file(self, param=None):
        if not param:
            param = {'fileSource': self.source}
        else:
            param['fileSource'] = self.source

        val = self.session.get('/static/file/query/', param)
        if val and val['errorCode'] == 0:
            return val['file']
        print('--------filter_file-----------')
        print(val['reason'])
        return None

    def delete_file(self, file_id, param = None):
        if not param:
            param = {'fileSource': self.source}
        else:
            param['fileSource'] = self.source

        val = self.session.delete('/static/file/delete/{0}'.format(file_id), param)
        if val and val['errorCode'] == 0:
            return val['file']

        print('--------delete_file-----------')
        print(val['reason'])
        return None

    def upload_file(self, file_path):
        params = {'fileSource': self.source, 'key-name': 'file'}
        files = {'file': open(file_path, 'rb')}
        val = self.session.upload('/static/file/upload/', files=files, params=params)
        if val and val['errorCode'] == 0:
            return val['file']
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
    app = File("autotest", work_session)
    file_path = "./file/file.py"
    new_file = app.upload_file(file_path)
    if not new_file:
        print('upload file failed')
        return False

    print(new_file)
    file_list = app.filter_file()
    if not file_list or len(file_list) < 0:
        print('filter file failed')
        return False

    new_file_path = "./file/file.py_new"
    file_val = app.download_file(new_file['token'], new_file_path)
    if not file_val:
        print('download file failed')
        return False

    old_file = app.delete_file(new_file['id'])
    if not old_file:
        print('delete file failed')
        return False

    return True
