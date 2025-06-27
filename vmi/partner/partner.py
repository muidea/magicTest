from mock import common as mock
from session import session, common
from cas.cas import cas

"""
{
	"name": "test11",
	"telephone": "123456",
	"wechat": "12345886",
	"description": "test partner description",
	"referee":{
		"id": 1
	},
	"status": {
		"id": 3
	}
}
"""


def mock_partner_param():
    return {
        'name': mock.name(),
        'telephone': mock.name(),
        'wechat': mock.name(),
        'description': mock.sentence(),
        'status': {
            'id': 3
        },
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())

    partner_instance = common.MagicEntity('/vmi/partner', work_session)
    partner_param = mock_partner_param()
    new_partner001 = partner_instance.insert(partner_param)
    if not new_partner001:
        print('insert new partner failed')
        return

    cur_partner001 = partner_instance.query(new_partner001['id'])
    if not cur_partner001:
        print('query new partner failed')

    cur_partner001['description'] = mock.sentence()
    cur_partner001 = partner_instance.update(new_partner001['id'], new_partner001)
    if not cur_partner001:
        print('update new partner failed')

    partner_instance.delete(new_partner001['id'])
