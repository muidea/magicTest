"""MagicSession - HTTP client session with authentication support"""

import json
import logging
import os
import threading
import time
import base64
from typing import Any, Callable, Dict, Optional, Union
import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.cookies import RequestsCookieJar

# Configure logger
logger = logging.getLogger(__name__)

# Disable SSL warnings whenever SSL verification is explicitly disabled.
if os.getenv('VERIFY_SSL', 'false').lower() == 'false':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    requests.packages.urllib3.disable_warnings(  # type: ignore[attr-defined]
        urllib3.exceptions.InsecureRequestWarning
    )

class MagicSession:
    """HTTP client session with authentication and request methods.
    
    Attributes:
        base_url: Base URL for all requests
        namespace: Namespace for API requests
        session_token: Bearer token for authentication
        session_auth_endpoint: Endpoint for signature authentication
        session_auth_token: Token for signature authentication
        application: Application identifier
        verify_ssl: Whether to verify SSL certificates
        timeout: Request timeout in seconds
    """

    def __init__(self, base_url: str, namespace: str = None):
        """Initialize MagicSession.
        
        Args:
            base_url: Base URL for all requests
            namespace: Optional namespace for API requests
        """
        self.current_session = requests.Session()
        self.base_url = base_url
        self.namespace = namespace
        self.session_token = None
        self.session_auth_endpoint = None
        self.session_auth_token = None
        self.application = None
        self.verify_ssl = os.getenv('VERIFY_SSL', 'false').lower() != 'false'
        self.timeout = float(os.getenv('REQUEST_TIMEOUT', '30.0'))
        self.trust_env = self._resolve_trust_env()
        self.http_pool_connections = int(os.getenv('REQUEST_POOL_CONNECTIONS', '100'))
        self.http_pool_maxsize = int(os.getenv('REQUEST_POOL_MAXSIZE', '100'))
        self.request_observer: Optional[Callable[..., None]] = None
        self._auth_lock = threading.RLock()
        self._configure_transport()

    @staticmethod
    def _resolve_trust_env() -> bool:
        explicit = os.getenv('REQUEST_TRUST_ENV')
        if explicit is not None:
            return explicit.lower() != 'false'
        return False

    def _configure_transport(self) -> None:
        """Apply session transport settings for high-concurrency workloads."""
        self.current_session.trust_env = self.trust_env
        adapter = HTTPAdapter(
            pool_connections=self.http_pool_connections,
            pool_maxsize=self.http_pool_maxsize,
            max_retries=0,
            pool_block=False,
        )
        self.current_session.mount('http://', adapter)
        self.current_session.mount('https://', adapter)

    @staticmethod
    def _mask_token(token: Optional[str]) -> str:
        if not token:
            return ""
        if len(token) <= 12:
            return token
        return f"{token[:8]}...{token[-4:]}"

    @classmethod
    def _describe_authorization(cls, header: str) -> str:
        if not header:
            return "none"
        if header.startswith("Bearer "):
            token = header[len("Bearer "):]
            session_id = ""
            expire_at = ""
            try:
                parts = token.split(".")
                if len(parts) == 3:
                    payload = parts[1] + "=" * (-len(parts[1]) % 4)
                    claims = json.loads(
                        base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
                    )
                    session_id = claims.get("_sessionID", "") or ""
                    expire_val = claims.get("authExpireTime") or claims.get(
                        "innerExpireTime"
                    )
                    expire_at = str(expire_val or "")
            except Exception:
                session_id = ""
                expire_at = ""
            return (
                f"bearer token={cls._mask_token(token)} "
                f"session_id={session_id} expire={expire_at}"
            ).strip()
        if header.startswith("Sig "):
            return f"sig {header[len('Sig '):]}"
        return header

    def _auth_state_snapshot(self) -> Dict[str, Any]:
        with self._auth_lock:
            return {
                "base_url": self.base_url,
                "namespace": self.namespace,
                "session_token": self.session_token,
                "session_auth_endpoint": self.session_auth_endpoint,
                "session_auth_token": self.session_auth_token,
                "application": self.application,
                "verify_ssl": self.verify_ssl,
                "timeout": self.timeout,
                "trust_env": self.trust_env,
                "http_pool_connections": self.http_pool_connections,
                "http_pool_maxsize": self.http_pool_maxsize,
                "request_observer": self.request_observer,
            }

    def _clone_cookie_jar(self) -> RequestsCookieJar:
        jar = RequestsCookieJar()
        jar.update(self.current_session.cookies)
        return jar

    def sync_cookies_from(self, other: 'MagicSession') -> None:
        if other is None:
            return
        with self._auth_lock:
            self.current_session.cookies = other._clone_cookie_jar()

    def auth_summary(self) -> str:
        snapshot = self._auth_state_snapshot()
        auth_mode = "none"
        auth_ref = ""
        if snapshot["session_auth_endpoint"] and snapshot["session_auth_token"]:
            auth_mode = "sig"
            auth_ref = snapshot["session_auth_endpoint"]
        elif snapshot["session_token"]:
            auth_mode = "bearer"
            auth_ref = self._mask_token(snapshot["session_token"])
        return (
            f"session_obj=0x{id(self):x} "
            f"namespace={snapshot['namespace'] or ''} "
            f"auth_mode={auth_mode} "
            f"auth_ref={auth_ref}"
        )

    def new_session(self) -> 'MagicSession':
        """Create a new session with same configuration.
        
        Returns:
            A new MagicSession instance
        """
        snapshot = self._auth_state_snapshot()
        new_session = MagicSession(snapshot["base_url"], snapshot["namespace"])
        new_session.verify_ssl = snapshot["verify_ssl"]
        new_session.timeout = snapshot["timeout"]
        new_session.application = snapshot["application"]
        new_session.trust_env = snapshot["trust_env"]
        new_session.http_pool_connections = snapshot["http_pool_connections"]
        new_session.http_pool_maxsize = snapshot["http_pool_maxsize"]
        new_session.session_token = snapshot["session_token"]
        new_session.session_auth_endpoint = snapshot["session_auth_endpoint"]
        new_session.session_auth_token = snapshot["session_auth_token"]
        new_session._configure_transport()
        new_session.current_session.cookies = self._clone_cookie_jar()
        new_session.request_observer = snapshot["request_observer"]
        return new_session

    def set_request_observer(self, observer: Optional[Callable[..., None]]) -> None:
        """Register a request observer for every business HTTP call."""
        self.request_observer = observer

    def bind_token(self, token: Optional[str]) -> None:
        """Bind bearer token for authentication.
        
        Args:
            token: Bearer token string
        """
        with self._auth_lock:
            old_token = self.session_token
            self.session_token = token
            if token:
                self.session_auth_endpoint = None
                self.session_auth_token = None
        if old_token != token:
            logger.info(
                "MagicSession bind_token changed %s old=%s new=%s",
                self.auth_summary(),
                self._mask_token(old_token),
                self._mask_token(token),
            )

    def bind_auth_secret(self, endpoint: str, auth_token: str) -> None:
        """Bind signature authentication credentials.
        
        Args:
            endpoint: Authentication endpoint
            auth_token: Authentication token
        """
        with self._auth_lock:
            self.session_auth_endpoint = endpoint
            self.session_auth_token = auth_token
            if endpoint and auth_token:
                self.session_token = None
        logger.info(
            "MagicSession bind_auth_secret updated %s endpoint=%s",
            self.auth_summary(),
            endpoint,
        )

    def bind_application(self, application: str) -> None:
        """Bind application identifier.
        
        Args:
            application: Application identifier string
        """
        with self._auth_lock:
            self.application = application

    def sync_from(self, other: 'MagicSession') -> None:
        """Synchronize runtime/auth state from another session instance."""
        if other is None:
            return

        if other is self:
            return

        first, second = (self, other) if id(self) <= id(other) else (other, self)
        with first._auth_lock:
            with second._auth_lock:
                before_summary = self.auth_summary()
                before_token = self._mask_token(self.session_token)
                before_sig = self.session_auth_endpoint

                self.base_url = other.base_url
                self.namespace = other.namespace
                self.session_token = other.session_token
                self.session_auth_endpoint = other.session_auth_endpoint
                self.session_auth_token = other.session_auth_token
                self.application = other.application
                self.verify_ssl = other.verify_ssl
                self.timeout = other.timeout
                self.trust_env = other.trust_env
                self.http_pool_connections = other.http_pool_connections
                self.http_pool_maxsize = other.http_pool_maxsize
                self.request_observer = other.request_observer
                self._configure_transport()
                self.current_session.cookies = other._clone_cookie_jar()
        logger.info(
            "MagicSession sync_from updated session_obj=0x%x from_session_obj=0x%x old_token=%s old_sig=%s new_state=%s",
            id(self),
            id(other),
            before_token,
            before_sig or "",
            self.auth_summary(),
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        try:
            self.current_session.close()
        except Exception:
            logger.debug('Close requests session failed', exc_info=True)

    def header(self) -> Dict[str, str]:
        """Generate request headers with authentication.
        
        Returns:
            Dictionary of HTTP headers
        """
        snapshot = self._auth_state_snapshot()
        header = {}

        if snapshot["namespace"] and snapshot["namespace"] != '':
            header['X-Mp-Namespace'] = snapshot["namespace"]

        if snapshot["application"] and snapshot["application"] != '':
            header['X-Mp-Application'] = snapshot["application"]

        # Priority: signature auth over bearer token
        if snapshot["session_auth_endpoint"] and snapshot["session_auth_token"]:
            credential_val = f"Credential={snapshot['session_auth_endpoint']}"
            signature_val = f"Signature={snapshot['session_auth_token']}"
            token_val = f"{credential_val},{signature_val}"
            header["Authorization"] = f'Sig {token_val}'
        elif snapshot["session_token"]:
            header["Authorization"] = f"Bearer {snapshot['session_token']}"

        return header

    def _notify_request_observer(
        self,
        method: str,
        url: str,
        full_url: str,
        elapsed: float,
        status_code: int,
        response: Any,
        error: Optional[BaseException] = None,
    ) -> None:
        if self.request_observer is None:
            return

        try:
            self.request_observer(
                method=method.upper(),
                url=url,
                full_url=full_url,
                elapsed=elapsed,
                status_code=status_code,
                response=response,
                error=error,
            )
        except Exception as exc:
            logger.debug('Request observer failed: %s', exc)

    def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Internal method to make HTTP requests with error handling.
        
        Args:
            method: HTTP method (get, post, put, delete)
            url: Relative URL path
            **kwargs: Additional arguments for requests.request
            
        Returns:
            Response data as dictionary, or error dictionary
        """
        full_url = f'{self.base_url}{url}'
        start_time = time.perf_counter()
        
        # Set default parameters
        kwargs.setdefault('headers', self.header())
        kwargs.setdefault('verify', self.verify_ssl)
        kwargs.setdefault('timeout', self.timeout)
        auth_header = kwargs.get('headers', {}).get('Authorization', '')
        if not auth_header and '/api/v1/cas/session/login/' not in url:
            logger.warning(
                'Request without Authorization %s method=%s url=%s',
                self.auth_summary(),
                method.upper(),
                url,
            )

        try:
            logger.debug('Making %s request to %s', method.upper(), full_url)
            response = self.current_session.request(method, full_url, **kwargs)
            response.raise_for_status()
            
            # Handle download case (non-JSON response)
            # If stream=True is set, return the response object directly
            # Also return response for file upload/download cases
            if 'files' in kwargs or 'data' in kwargs or kwargs.get('stream', False):
                self._notify_request_observer(
                    method,
                    url,
                    full_url,
                    time.perf_counter() - start_time,
                    response.status_code,
                    response,
                )
                return response
            
            # Parse JSON response
            try:
                payload = response.json()
                self._notify_request_observer(
                    method,
                    url,
                    full_url,
                    time.perf_counter() - start_time,
                    response.status_code,
                    payload,
                )
                return payload
            except ValueError as e:
                logger.error('Failed to parse JSON response: %s', e)
                payload = {
                    "error": {
                        "code": 100,
                        "message": f"JSON解析失败: {str(e)}",
                        "status_code": response.status_code
                    }
                }
                self._notify_request_observer(
                    method,
                    url,
                    full_url,
                    time.perf_counter() - start_time,
                    response.status_code,
                    payload,
                    e,
                )
                return payload
                
        except requests.exceptions.RequestException as e:
            logger.error('HTTP request failed: %s', e)
            status_code = getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0
            if status_code in (401, 403):
                logger.error(
                    'Auth failure request_state=%s sent_auth=%s method=%s url=%s',
                    self.auth_summary(),
                    self._describe_authorization(auth_header),
                    method.upper(),
                    url,
                )
            payload = {
                "error": {
                    "code": 100,
                    "message": f"HTTP请求失败: {str(e)}",
                    "status_code": status_code
                }
            }
            self._notify_request_observer(
                method,
                url,
                full_url,
                time.perf_counter() - start_time,
                status_code,
                payload,
                e,
            )
            return payload
        except Exception as e:
            logger.error('Unexpected error: %s', e)
            payload = {
                "error": {
                    "code": 500,
                    "message": f"内部错误: {str(e)}"
                }
            }
            self._notify_request_observer(
                method,
                url,
                full_url,
                time.perf_counter() - start_time,
                500,
                payload,
                e,
            )
            return payload

    def post(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request.
        
        Args:
            url: Relative URL path
            params: Request body parameters
            
        Returns:
            Response data as dictionary
        """
        return self._request('post', url, json=params)

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request.
        
        Args:
            url: Relative URL path
            params: Query parameters
            
        Returns:
            Response data as dictionary
        """
        return self._request('get', url, params=params)

    def put(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make PUT request.
        
        Args:
            url: Relative URL path
            params: Request body parameters
            
        Returns:
            Response data as dictionary
        """
        return self._request('put', url, json=params)

    def delete(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make DELETE request.
        
        Args:
            url: Relative URL path
            params: Query parameters
            
        Returns:
            Response data as dictionary
        """
        return self._request('delete', url, params=params)

    def upload(self, url: str, files: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Upload files.
        
        Args:
            url: Relative URL path
            files: Files to upload (dict compatible with requests files parameter)
            params: Additional parameters (will be sent as query string)
            
        Returns:
            Response data as dictionary
        """
        logger.debug('Uploading files to %s', url)
        return self._request('post', url, files=files, params=params)

    def download(self, url: str, dst_file: str, params: Optional[Dict[str, Any]] = None) -> Union[str, Dict[str, Any]]:
        """Download file to local path.
        
        Args:
            url: Relative URL path
            dst_file: Destination file path
            params: Query parameters
            
        Returns:
            Destination file path on success, error dictionary on failure
        """
        try:
            response = self._request('get', url, params=params, stream=True)
            
            # Check if response is an error
            if isinstance(response, dict) and 'error' in response:
                return response
            
            # Write file
            with open(dst_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.debug('File downloaded to %s', dst_file)
            return dst_file
            
        except Exception as e:
            logger.error('File download failed: %s', e)
            return {
                "error": {
                    "code": 100,
                    "message": f"文件下载失败: {str(e)}"
                }
            }
