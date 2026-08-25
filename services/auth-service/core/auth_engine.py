"""
Authentication & Authorization Service

Centralized authentication, token management, and access control.
"""

import jwt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AuthEngine:
    """Authentication and authorization engine."""
    
    def __init__(
        self,
        secret_key: str = "your-secret-key-change-in-production",
        algorithm: str = "HS256",
        token_expiry_minutes: int = 1440  # 24 hours
    ):
        """
        Initialize Auth Engine.
        
        Args:
            secret_key: JWT secret key
            algorithm: JWT algorithm
            token_expiry_minutes: Token expiry time
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.token_expiry_minutes = token_expiry_minutes
    
    def hash_password(self, password: str) -> str:
        """Hash a password."""
        salt = secrets.token_hex(32)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return f"{salt}${pwd_hash.hex()}"
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            salt, pwd_hash = password_hash.split('$')
            pwd_verify = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return pwd_verify.hex() == pwd_hash
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def create_access_token(self, user_id: str, username: str) -> str:
        """Create JWT access token."""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=self.token_expiry_minutes)
        
        payload = {
            'sub': user_id,
            'username': username,
            'iat': now.isoformat(),
            'exp': expiry.isoformat()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Access token created for user: {username}")
        return token
    
    def create_api_key(self, user_id: str) -> str:
        """Create API key for service-to-service authentication."""
        key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        logger.info(f"API key created for user: {user_id}")
        return key, key_hash
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            logger.info(f"Token verified for user: {payload.get('username')}")
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            return None
    
    def verify_api_key(self, key: str, key_hash: str) -> bool:
        """Verify API key."""
        key_check = hashlib.sha256(key.encode()).hexdigest()
        return key_check == key_hash
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create refresh token."""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=7)  # 7 days
        
        payload = {
            'sub': user_id,
            'type': 'refresh',
            'iat': now.isoformat(),
            'exp': expiry.isoformat()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Refresh token created for user: {user_id}")
        return token


class RBACEngine:
    """Role-Based Access Control engine."""
    
    # Define roles and permissions
    ROLES = {
        'admin': [
            'create_strategy',
            'edit_strategy',
            'delete_strategy',
            'deploy_strategy',
            'stop_strategy',
            'pause_strategy',
            'view_all_strategies',
            'view_all_trades',
            'manage_users',
            'view_logs'
        ],
        'trader': [
            'create_strategy',
            'edit_strategy',
            'deploy_strategy',
            'pause_strategy',
            'view_own_strategies',
            'view_own_trades',
            'stop_own_strategy'
        ],
        'viewer': [
            'view_own_strategies',
            'view_own_trades'
        ],
        'analyst': [
            'view_all_strategies',
            'view_all_trades',
            'create_report',
            'view_performance'
        ]
    }
    
    def __init__(self):
        """Initialize RBAC engine."""
        pass
    
    def has_permission(self, role: str, permission: str) -> bool:
        """Check if role has permission."""
        role_perms = self.ROLES.get(role, [])
        return permission in role_perms
    
    def get_role_permissions(self, role: str) -> list:
        """Get all permissions for a role."""
        return self.ROLES.get(role, [])
    
    def validate_access(self, user_role: str, required_permission: str) -> bool:
        """Validate user has required permission."""
        return self.has_permission(user_role, required_permission)


__all__ = ['AuthEngine', 'RBACEngine']
