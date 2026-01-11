"""MagicSession - HTTP client session with authentication support"""

import json
import logging
import os
from typing import Any, Dict, Optional, Union
import requests
import urllib3

# Configure logger
logger = logging.getLogger(__name__)

# Disable SSL warnings only in development environment
if os.getenv('ENVIRONMENT', 'development') == 'development':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

    def new_session(self) -> 'MagicSession':
        """Create a new session with same configuration.
        
        Returns:
            A new MagicSession instance
        """
        return MagicSession(self.base_url, self.namespace)

    def bind_token(self, token: str) -> None:
        """Bind bearer token for authentication.
        
        Args:
            token: Bearer token string
        """
        self.session_token = token

    def bind_auth_secret(self, endpoint: str, auth_token: str) -> None:
        """Bind signature authentication credentials.
        
        Args:
            endpoint: Authentication endpoint
            auth_token: Authentication token
        """
        self.session_auth_endpoint = endpoint
        self.session_auth_token = auth_token

    def bind_application(self, application: str) -> None:
        """Bind application identifier.
        
        Args:
            application: Application identifier string
        """
        self.application = application

    def header(self) -> Dict[str, str]:
        """Generate request headers with authentication.
        
        Returns:
            Dictionary of HTTP headers
        """
        header = {}

        if self.namespace:
            header['X-Mp-Namespace'] = self.namespace

        if self.application:
            header['X-Mp-Application'] = self.application

        # Priority: signature auth over bearer token
        if self.session_auth_endpoint and self.session_auth_token:
            credential_val = f"Credential={self.session_auth_endpoint}"
            signature_val = f"Signature={self.session_auth_token}"
            token_val = f"{credential_val},{signature_val}"
            header["Authorization"] = f'Sig {token_val}'
        elif self.session_token:
            header["Authorization"] = f'Bearer {self.session_token}'

        return header

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
        
        # Set default parameters
        kwargs.setdefault('headers', self.header())
        kwargs.setdefault('verify', self.verify_ssl)
        kwargs.setdefault('timeout', self.timeout)
        
        try:
            logger.debug('Making %s request to %s', method.upper(), full_url)
            response = self.current_session.request(method, full_url, **kwargs)
            response.raise_for_status()
            
            # Handle download case (non-JSON response)
            if 'files' in kwargs or 'data' in kwargs:
                return response
            
            # Parse JSON response
            try:
                return response.json()
            except ValueError as e:
                logger.error('Failed to parse JSON response: %s', e)
                return {
                    "error": {
                        "code": 100,
                        "message": f"JSON解析失败: {str(e)}",
                        "status_code": response.status_code
                    }
                }
                
        except requests.exceptions.RequestException as e:
            logger.error('HTTP request failed: %s', e)
            status_code = getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0
            return {
                "error": {
                    "code": 100,
                    "message": f"HTTP请求失败: {str(e)}",
                    "status_code": status_code
                }
            }
        except Exception as e:
            logger.error('Unexpected error: %s', e)
            return {
                "error": {
                    "code": 500,
                    "message": f"内部错误: {str(e)}"
                }
            }

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
            params: Additional parameters
            
        Returns:
            Response data as dictionary
        """
        logger.debug('Uploading files to %s', url)
        return self._request('post', url, files=files, data=params)

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

