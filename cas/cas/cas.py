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
        val = self.session.post('/cas/account/login/', params)
        if 'error' in val:
            print(f"登录失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return False
        self.session_token = val.get('sessionToken')
        self.current_entity = val.get('entity')
        return self.session_token is not None

    def logout(self, session_token):
        """logout"""
        self.session.bind_token(session_token)
        val = self.session.delete('/cas/account/logout/')
        if 'error' in val:
            print(f"注销失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return False
        return True

    def verify(self, session_token):
        """verify"""
        self.session.bind_token(session_token)
        val = self.session.get('/cas/session/verify/')
        if 'error' in val:
            print(f"验证失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        self.session_token = val.get('sessionToken')
        self.current_entity = val.get('entity')
        return self.session_token


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.verify(app.session_token)
    app.logout(app.session_token)
