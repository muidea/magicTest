"""Bounded HTTPS Gateway client using only a subscription ApiKey."""
import http.client
import os
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from .common import Failure, OPERATIONS, dumps, gateway_result, home_path, identity, require, secret, strict_json
from .config import endpoint


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Failure('Gateway redirect refused')


class RemoteFailure(Failure):
    def __init__(self, status=0, code=None):
        self.status, self.code = status, code
        super().__init__(f'Gateway request failed (HTTP {status}, business code {code}); response body withheld')


def _make_https_handler(context):
    target = (os.environ.get('MAGICTEST_TARGET_ADDRESS') or '').strip()
    if not target:
        return HTTPSHandler(context=context)

    class _TargetHTTPSHandler(HTTPSHandler):
        def https_open(self, req):
            class _SniConn(http.client.HTTPSConnection):
                def __init__(self, host, port=None, **kwargs):
                    parsed = urlsplit(f'https://{host}')
                    self._sni_host = parsed.hostname or host
                    super().__init__(target, port=parsed.port or port or 443, **kwargs)

                def connect(self):
                    sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
                    if self._tunnel_host:
                        self.sock = sock
                        self._tunnel()
                    self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)

            return self.do_open(_SniConn, req, context=self._context)

    return _TargetHTTPSHandler(context=context)


class Gateway:
    def __init__(self, config, journal):
        self.config, self.journal = config, journal
        self.origin, self.prefix = endpoint(config['serviceUrl'])
        self.key = secret(home_path(config['credentialFile']))
        context = ssl.create_default_context(cafile=str(home_path(config['tls']['caFile'])))
        if config['tls'].get('trustLeaf'):
            require(hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'), 'TLS leaf-anchor verification unsupported by this Python/OpenSSL')
            # The configured local cert is an explicit trust anchor; hostname verification stays enabled.
            context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        self.opener = build_opener(NoRedirect(), _make_https_handler(context))
        self.last_request = 0.0

    def call(self, entity, operation, fields=None, value_id=None, query=None):
        require(entity in OPERATIONS and operation in OPERATIONS[entity], 'operation not permitted by simulator')
        method = {'query': 'GET', 'get': 'GET', 'create': 'POST', 'update': 'PUT'}[operation]
        path = self.prefix + '/' + entity + '_' + operation
        if operation in ('get', 'update'):
            path += '/' + identity(value_id)
        if query:
            path += '?' + urlencode(query)
        def wire(value):
            if isinstance(value, dict):
                return {k: int(identity(v)) if k in ('id', 'version') and v is not None else wire(v) for k, v in value.items()}
            return value
        raw = dumps(wire(fields)).encode() if fields is not None else None
        attempts = 4 if method == 'GET' else 1
        for attempt in range(attempts):
            self.journal.consume_request(self.config['run']['maxRequests'])
            time.sleep(max(0, 1 / self.config['run']['qps'] - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = Request(self.origin + path, data=raw, method=method,
                              headers={'Authorization': 'ApiKey ' + self.key, 'Accept': 'application/json', 'Content-Type': 'application/json'})
            try:
                with self.opener.open(request, timeout=30) as response:
                    require(response.status == 200 and response.headers.get_content_type() == 'application/json', 'invalid Gateway response type/status')
                    payload = response.read((4 << 20) + 1)
                    require(len(payload) <= 4 << 20, 'Gateway response size exceeded')
                    result = strict_json(payload)
                    require(isinstance(result, dict), 'invalid Gateway response envelope')
                    error = result.get('error')
                    if error is not None:
                        code = error.get('code') if isinstance(error, dict) and type(error.get('code')) is int else None
                        raise RemoteFailure(200, code)
                    return gateway_result(result)
            except HTTPError as error:
                status = error.code
                error.close()
                failure = RemoteFailure(status)
            except (URLError, TimeoutError, OSError):
                failure = RemoteFailure()
            except RemoteFailure as error:
                # Business failures are not transient read transport errors.
                raise error from None
            if attempt + 1 >= attempts or failure.status in (400, 401, 403, 404, 409) or 300 <= failure.status < 400:
                raise failure from None
            time.sleep(2 ** attempt)
        raise Failure('unreachable HTTP retry state')

    def get(self, entity, value_id):
        value = self.call(entity, 'get', value_id=value_id).get('value')
        require(isinstance(value, dict) and identity(value.get('id')) == identity(value_id), 'Gateway get returned wrong/missing identity')
        return value

    def scan(self, entity):
        result, previous, total = [], 0, None
        budget = self.config['run']['maxReadRows']
        for number in range(1, budget // 100 + 2):
            response = self.call(entity, 'query', query={'_pageNum': number, '_pageSize': 100, '_needTotal': 'true',
                '_viewType': 'detail', '_sortFilter': dumps({'fieldName': 'id', 'ascFlag': True})})
            page, rows = response.get('pagination'), response.get('values')
            require(isinstance(page, dict), 'missing complete pagination')
            require(type(page.get('total')) is int and 0 <= page['total'] <= budget, 'invalid/over-budget total')
            total = page['total'] if total is None else total
            require(page['total'] == total and page.get('pageNum') == number and page.get('pageSize') == 100
                    and not page.get('nextCursor') and not page.get('hasMore'), 'pagination changed or unsupported')
            if rows is None:
                require(total == 0, 'missing rows for nonempty query')
                rows = []
            require(isinstance(rows, list) and len(rows) <= 100, 'invalid query rows')
            for row in rows:
                require(isinstance(row, dict), 'invalid query record')
                value_id = int(identity(row.get('id')))
                require(value_id > previous, 'query IDs duplicated or not in stable ascending order')
                previous = value_id
            result.extend(rows)
            require(len(result) <= total, 'query exceeded reported total')
            if len(result) == total:
                return result
            require(len(rows) == 100, 'incomplete query page')
        raise Failure('query page budget exceeded')
