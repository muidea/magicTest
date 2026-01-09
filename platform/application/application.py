from mock import common as mock
from session import session
import concurrent.futures
import argparse

class DatabaseDeclare:
    def __init__(self, id, db_server, db_name, username, password, char_set, max_conn_num):
        self.id = id
        self.db_server = db_server
        self.db_name = db_name
        self.username = username
        self.password = password
        self.char_set = char_set
        self.max_conn_num = max_conn_num

    def to_dict(self):
        return {
            "id": self.id,
            "dbServer": self.db_server,
            "dbName": self.db_name,
            "username": self.username,
            "password": self.password,
            "charSet": self.char_set,
            "maxConnNum": self.max_conn_num
        }

class ApplicationDeclare:
    def __init__(self, id, uuid, name, show_name, pkg_prefix, icon, catalog, domain, email, author, description, database, hosted_by, artifact, status):
        self.id = id
        self.uuid = uuid
        self.name = name
        self.show_name = show_name
        self.pkg_prefix = pkg_prefix
        self.icon = icon
        self.catalog = catalog
        self.domain = domain
        self.email = email
        self.author = author
        self.description = description
        self.database = database
        self.hosted_by = hosted_by
        self.artifact = artifact
        self.status = status

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "name": self.name,
            "showName": self.show_name,
            "pkgPrefix": self.pkg_prefix,
            "icon": self.icon,
            "catalog": self.catalog,
            "domain": self.domain,
            "email": self.email,
            "author": self.author,
            "description": self.description,
            "database": self.database.to_dict() if self.database else None,
            "hostedBy": self.hosted_by,
            "artifact": self.artifact,
            "status": self.status
        }

class Application:
    """Application"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_application(self, filter):
        url = '/core/applications'

        val = self.session.post(url, filter)
        if 'error' in val:
            print("过滤应用失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('values')

    def query_application(self, id):
        val = self.session.get('/core/applications/{0}'.format(id))
        if 'error' in val:
            print("查询应用失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def create_application(self, param):
        val = self.session.post('/core/applications', param)
        if 'error' in val:
            print("创建应用失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def update_application(self, id, param):
        val = self.session.put('/core/applications/{0}'.format(id), param)
        if 'error' in val:
            print("更新应用失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def delete_application(self, id):
        val = self.session.delete('/core/application/destroy/{0}'.format(id))
        if 'error' in val:
            print("删除应用失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

def mock_application_param():
    database = DatabaseDeclare(
        id=1,
        db_server='mysql:3306',
        db_name='testdb',
        username='root',
        password='rootkit',
        char_set='utf8',
        max_conn_num=10
    )

    return ApplicationDeclare(
        id=1,
        uuid=mock.uuid(),
        name=mock.word(),  # Updated to use mock.word()
        show_name='Test Application',
        pkg_prefix='com.test',
        icon='icon.png',
        catalog='Test',
        domain=mock.url(),
        email=mock.email(),
        author='TestAuthor',  # Updated to only contain English characters
        description=mock.sentence(),
        database=database,
        hosted_by='magicMock',  # Updated hosted_by value
        artifact='magicMock@v1.3.0',
        status=1
    ).to_dict()

def smoke_test(server_url, namespace):
    """Smoke test: basic CRUD operations"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    app_instance = Application(work_session)

    # Create a new application
    app001 = mock_application_param()
    new_app10 = app_instance.create_application(app001)
    if not new_app10:
        print('create new application failed')
        return

    # Update the application
    new_app10['description'] = mock.sentence()
    new_app11 = app_instance.update_application(new_app10['id'], new_app10)
    if new_app11['description'] != new_app10['description']:
        print('update application failed')

    # Query the application
    queried_app = app_instance.query_application(new_app10['id'])
    if not queried_app:
        print('query application failed')

    # Delete the application
    app_instance.delete_application(new_app10['id'])

    print("Smoke test completed successfully.")

def batch_create_applications(app_instance, count, concurrency):
    def create_app():
        app_param = mock_application_param()
        return app_instance.create_application(app_param)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(create_app) for _ in range(count)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    return results

def batch_update_applications(app_instance, apps, concurrency):
    def update_app(app):
        app['description'] = mock.sentence()
        return app_instance.update_application(app['id'], app)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(update_app, app) for app in apps]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    return results

def batch_delete_applications(app_instance, apps, concurrency):
    def delete_app(app):
        return app_instance.delete_application(app['id'])

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(delete_app, app) for app in apps]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    return results

def stress_test(server_url, namespace, count, concurrency):
    """Stress test: batch CRUD operations"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    app_instance = Application(work_session)

    # Batch create applications
    print("Creating %d applications with concurrency %d..." % (count, concurrency))
    created_apps = batch_create_applications(app_instance, count, concurrency)
    if not all(created_apps):
        print('Batch create applications failed')
        return

    # Batch update applications
    print("Updating %d applications with concurrency %d..." % (count, concurrency))
    updated_apps = batch_update_applications(app_instance, created_apps, concurrency)
    if not all(updated_apps):
        print('Batch update applications failed')
        return

    # Batch delete applications
    print("Deleting %d applications with concurrency %d..." % (count, concurrency))
    deleted_apps = batch_delete_applications(app_instance, created_apps, concurrency)
    if not all(deleted_apps):
        print('Batch delete applications failed')
        return

    print("Stress test completed successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run smoke or stress tests on applications.")
    parser.add_argument("--server_url", type=str, required=True, help="The server URL.")
    parser.add_argument("--namespace", type=str, required=True, help="The namespace.")
    parser.add_argument("--test_type", type=str, choices=["smoke", "stress"], required=True, help="The type of test to run (smoke or stress).")
    parser.add_argument("--count", type=int, default=10, help="The number of applications to createss (for stress test).")
    parser.add_argument("--concurrency", type=int, default=5, help="The number of concurrent operations (for stress test).")

    args = parser.parse_args()

    if args.test_type == "smoke":
        smoke_test(args.server_url, args.namespace)
    elif args.test_type == "stress":
        stress_test(args.server_url, args.namespace, args.count, args.concurrency)