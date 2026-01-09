"""Cas"""

from session import session


class Cas:
    """Cas"""

    def __init__(self, work_session):
        self.session = work_session
        self.session_token = None
        self.current_entity = None

    def get_session_token(self):
        """get_session_token"""
        return self.session_token

    def get_current_entity(self):
        return self.current_entity

    def login(self, account, password):
        """login"""
        params = {'account': account, 'password': password}
        val = self.session.post('/cas/session/login/', params)
        if val.get('error') is not None:
            print("登录失败 Code: {0}, Message: {1}".format(val['error']['code'], val['error']['message']))
            return False
        self.session_token = val.get('sessionToken')
        self.current_entity = val.get('entity')
        return self.session_token is not None

    def logout(self, session_token):
        """logout"""
        self.session.bind_token(session_token)
        val = self.session.delete('/cas/session/logout/')
        if val.get('error') is not None:
            print("注销失败 Code: {0}, Message: {1}".format(val['error']['code'], val['error']['message']))
            return False
        return True

    def refresh(self, session_token):
        """verify"""
        self.session.bind_token(session_token)
        val = self.session.get('/cas/session/refresh/')
        if val.get('error') is not None:
            print("验证失败 Code: {0}, Message: {1}".format(val['error']['code'], val['error']['message']))
            return None
        self.session_token = val.get('sessionToken')
        self.current_entity = val.get('entity')
        return self.session_token


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.refresh(app.session_token)
    app.logout(app.session_token)
