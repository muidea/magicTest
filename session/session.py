"""MagicSession"""

import json
import requests


class MagicSession(object):
    """MagicSession"""

    def __init__(self, base_url, namespace):
        self.current_session = requests.Session()
        self.base_url = base_url
        self.namespace = namespace
        self.session_token = None
        self.session_auth_endpoint = None
        self.session_auth_token = None
        self.application = None

    def new_session(self):
        """fork new session"""
        return MagicSession(self.base_url, self.namespace)

    def bind_token(self, token):
        self.session_token = token

    def bind_auth_secret(self, endpoint, auth_token):
        self.session_auth_endpoint = endpoint
        self.session_auth_token = auth_token

    def bind_application(self, application):
        self.application = application

    def header(self):
        header = {}

        if self.namespace:
            header['X-Namespace'] = self.namespace

        if self.application:
            header['X-Application'] = self.application

        if self.session_token:
            header["Authorization"] = 'Bearer %s' % self.session_token

        if self.session_auth_endpoint and self.session_auth_token:
            credential_val = "{0}={1}".format("Credential", self.session_auth_endpoint)
            signature_val = "{0}={1}".format("Signature", self.session_auth_token)
            token_val = "{0},{1}".format(credential_val, signature_val)
            header["Authorization"] = 'Sig %s' % token_val

        return header

    def post(self, url, params):
        """Post"""
        ret = None
        try:
            response = self.current_session.post('%s%s' % (self.base_url, url), headers=self.header(), json=params)
            ret = json.loads(response.text)
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "HTTP请求失败: {}".format(str(except_value))
                }
            }
        return ret

    def get(self, url, params=None):
        """Get"""
        ret = None
        try:
            response = self.current_session.get('%s%s' % (self.base_url, url), headers=self.header(), params=params)
            ret = json.loads(response.text)
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "HTTP请求失败: {}".format(str(except_value))
                }
            }
        return ret

    def put(self, url, params):
        """Put"""
        ret = None
        try:
            response = self.current_session.put('%s%s' % (self.base_url, url), headers=self.header(), json=params)
            ret = json.loads(response.text)
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "HTTP请求失败: {}".format(str(except_value))
                }
            }
        return ret

    def delete(self, url, params=None):
        """Delete"""
        ret = None
        try:
            response = self.current_session.delete('%s%s' % (self.base_url, url), headers=self.header(), params=params)
            ret = json.loads(response.text)
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "HTTP请求失败: {}".format(str(except_value))
                }
            }
        return ret

    def upload(self, url, files, params=None):
        """Upload"""
        ret = None
        try:
            print('%s%s' % (self.base_url, url))
            response = self.current_session.post('%s%s' % (self.base_url, url),
                                                 headers=self.header(), params=params, files=files)
            ret = json.loads(response.text)
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "HTTP请求失败: {}".format(str(except_value))
                }
            }
        return ret

    def download(self, url, dst_file, params=None):
        """Download"""
        ret = None
        try:
            response = self.current_session.get('%s%s' % (self.base_url, url), headers=self.header(), params=params)
            with open(dst_file, "wb") as code:
                code.write(response.content)
            ret = dst_file
        except ValueError as except_value:
            ret = {
                "error": {
                    "code": 100,
                    "message": "文件下载失败: {}".format(str(except_value))
                }
            }
        return ret

