import ldap
import ssl
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.user import User


class LDAPAuthService:
    """Service for LDAP authentication"""
    
    def __init__(self):
        self.server = settings.ldap_server
        self.port = settings.ldap_port
        self.bind_dn = settings.ldap_bind_dn
        self.bind_password = settings.ldap_bind_password
        self.base_dn = settings.ldap_base_dn
        self.user_dn_template = settings.ldap_user_dn_template
        self.user_search_base = settings.ldap_user_search_base
        self.user_filter = settings.ldap_user_filter
        self.timeout = settings.ldap_connection_timeout
        
        # Configure LDAP options
        if settings.ldap_ignore_tls_errors:
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    
    def _get_connection(self):
        """Create LDAP connection"""
        try:
            # Build LDAP URL
            protocol = "ldaps" if settings.ldap_use_ssl else "ldap"
            url = f"{protocol}://{self.server}:{self.port}"
            
            # Initialize connection
            conn = ldap.initialize(url)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.timeout)
            conn.set_option(ldap.OPT_TIMEOUT, self.timeout)
            
            # Start TLS if configured
            if settings.ldap_start_tls and not settings.ldap_use_ssl:
                conn.start_tls_s()
            
            return conn
        except Exception as e:
            logger.error(f"Failed to create LDAP connection: {e}")
            raise
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user against LDAP"""
        conn = None
        try:
            conn = self._get_connection()
            
            # Bind with service account
            conn.simple_bind_s(self.bind_dn, self.bind_password)
            
            # Search for user
            search_filter = f"(&{self.user_filter}({settings.ldap_user_attr_uid}={username}))"
            result = conn.search_s(
                self.user_search_base,
                ldap.SCOPE_SUBTREE,
                search_filter,
                [settings.ldap_user_attr_email, settings.ldap_user_attr_name, settings.ldap_user_attr_uid]
            )
            
            if not result:
                logger.warning(f"User {username} not found in LDAP")
                return None
            
            user_dn, user_attrs = result[0]
            
            # Try to bind as the user
            user_bind_dn = self.user_dn_template.format(username=username)
            try:
                test_conn = self._get_connection()
                test_conn.simple_bind_s(user_bind_dn, password)
                test_conn.unbind_s()
            except ldap.INVALID_CREDENTIALS:
                logger.warning(f"Invalid credentials for user {username}")
                return None
            
            # Extract user attributes
            user_data = {
                "ldap_uid": username,
                "email": self._get_attr_value(user_attrs, settings.ldap_user_attr_email),
                "display_name": self._get_attr_value(user_attrs, settings.ldap_user_attr_name),
            }
            
            logger.info(f"Successfully authenticated user {username}")
            return user_data
            
        except Exception as e:
            logger.error(f"LDAP authentication error: {e}")
            return None
        finally:
            if conn:
                try:
                    conn.unbind_s()
                except:
                    pass
    
    def _get_attr_value(self, attrs: Dict[str, list], attr_name: str) -> Optional[str]:
        """Extract attribute value from LDAP attributes"""
        values = attrs.get(attr_name, [])
        if values and isinstance(values[0], bytes):
            return values[0].decode('utf-8')
        elif values:
            return str(values[0])
        return None
    
    async def get_or_create_user(self, db: AsyncSession, ldap_data: Dict[str, Any]) -> User:
        """Get existing user or create new one from LDAP data"""
        # Check if user exists
        result = await db.execute(
            select(User).where(User.ldap_uid == ldap_data["ldap_uid"])
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update last login
            user.last_login = datetime.utcnow()
            user.email = ldap_data.get("email") or user.email
            user.display_name = ldap_data.get("display_name") or user.display_name
        else:
            # Create new user
            user = User(
                ldap_uid=ldap_data["ldap_uid"],
                email=ldap_data.get("email"),
                display_name=ldap_data.get("display_name"),
                last_login=datetime.utcnow()
            )
            db.add(user)
        
        await db.commit()
        await db.refresh(user)
        
        return user