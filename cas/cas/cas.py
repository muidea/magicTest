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
        if val and val['errorCode'] == 0:
            self.session_token = val['sessionToken']
            self.current_entity = val['entity']
            return True

        print(val)
        print('--------login-----------')
        print(val['reason'])
        return False

    def logout(self, session_token):
        """logout"""
        self.session.bind_token(session_token)
        val = self.session.delete('/cas/account/logout/')
        if val and val['errorCode'] == 0:
            return True

        print('--------logout-----------')
        print(val['reason'])
        return False

    def verify(self, session_token):
        """verify"""
        self.session.bind_token(session_token)
        val = self.session.get('/cas/session/verify/')
        if val and val['errorCode'] == 0:
            self.session_token = val['sessionToken']
            self.current_entity = val['entity']
            return self.session_token

        print('--------verify-----------')
        print(val['reason'])
        return None


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.verify(app.session_token)
    app.logout(app.session_token)
