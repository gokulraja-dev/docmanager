import json
import base64
import requests
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwcrypto import jwt, jwk
from redis.asyncio import StrictRedis
from dotenv import load_dotenv
import os

# ------------------------
# Constants
# ------------------------
load_dotenv()

JWKS_URL = os.getenv("JWKS_URL", "http://10.10.10.113:8000/v1/auth/.well-known/jwks.json")
EXPECTED_AUD = os.getenv("IAM_EXPECTED_AUD", "orchestrator_service")
JWKS_CACHE_KEY = os.getenv("JWKS_CACHE_KEY", "jwks_cache")
JWKS_CACHE_TTL = int(os.getenv("JWKS_CACHE_TTL", 300))    # 5 minutes
LEEWAY = int(os.getenv("JWT_LEEWAY", 60))                 # 60 seconds for exp/iat tolerance

# ------------------------
# Security dependencies
# ------------------------
# auto_error=False so a missing Authorization header surfaces as our own 401
# below, instead of HTTPBearer's default 403 ("Not authenticated").
security = HTTPBearer(auto_error=False)
#--------------------------

redis_client = StrictRedis(host="localhost", port=6379, db=0, decode_responses=True)

def get_current_timestamp():
    return int(datetime.now(timezone.utc).timestamp())


def decode_jwt_header(token: str):
    """Extract and decode the JWT header (base64)."""
    try:
        header_b64 = token.split(".")[0]
        padding = "=" * (-len(header_b64) % 4)
        decoded = base64.urlsafe_b64decode(header_b64 + padding)
        return json.loads(decoded)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid JWT header")



async def fetch_jwks_from_iam():
    """Fetch JWKS directly from IAM."""
    try:
        res = requests.get(JWKS_URL, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch JWKS from IAM")


async def get_jwks_from_cache():
    """Return JWKS from Redis cache if available, else fetch from IAM."""
    cached = await redis_client.get(JWKS_CACHE_KEY)
    if cached:
        return json.loads(cached)

    jwks = await fetch_jwks_from_iam()
    await redis_client.set(JWKS_CACHE_KEY, json.dumps(jwks), ex=JWKS_CACHE_TTL)
    return jwks


def select_key_from_jwks(jwks: dict, kid: str):
    """Return matching JWK object for the given KID."""
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return jwk.JWK.from_json(json.dumps(k))
    return None


def verify_signature_with_key(token: str, key_obj: jwk.JWK):
    """Verify RSA signature using the selected JWK."""
    try:
        verified = jwt.JWT(key=key_obj, jwt=token)
        return json.loads(verified.claims)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token signature")


def validate_time_claims(claims: dict):
    """Validate exp, iat (JWT time-based security claims)."""
    now = get_current_timestamp()

    # exp
    if "exp" not in claims:
        raise HTTPException(status_code=401, detail="Token missing exp claim")
    exp = int(claims["exp"])
    if now > exp + LEEWAY:
        raise HTTPException(status_code=401, detail="Token expired")

    # iat
    if "iat" in claims:
        iat = int(claims["iat"])
        if iat - LEEWAY > now:
            raise HTTPException(status_code=401, detail="Token used before issued")

    return True


def validate_audience_claim(claims: dict):
    """Validate token's audience (aud)."""
    aud = claims.get("aud")

    if not aud:
        raise HTTPException(status_code=403, detail="Missing service access")

    if isinstance(aud, list):
        if EXPECTED_AUD not in aud:
            raise HTTPException(status_code=403, detail="Unauthorized service access")
    else:
        if aud != EXPECTED_AUD:
            raise HTTPException(status_code=403, detail="Unauthorized service access")


async def verify_token(token: str):
    """Main function: Verify token → KID → JWKS → public key → signature → claims."""
    header = decode_jwt_header(token)
    kid = header.get("kid")

    if not kid:
        raise HTTPException(status_code=401, detail="Missing kid in token header")

    # 1. Load JWKS from Redis cache
    jwks = await get_jwks_from_cache()

    # 2. Find matching key
    key_obj = select_key_from_jwks(jwks, kid)

    # 3. If not found, force refresh JWKS from IAM once
    if key_obj is None:
        jwks = await fetch_jwks_from_iam()
        await redis_client.set(JWKS_CACHE_KEY, json.dumps(jwks), ex=JWKS_CACHE_TTL)
        key_obj = select_key_from_jwks(jwks, kid)

        if key_obj is None:
            raise HTTPException(status_code=401, detail="Unknown kid in token")

    # 4. Verify JWS signature (RSA)
    claims = verify_signature_with_key(token, key_obj)

    # 5. Validate exp / iat
    validate_time_claims(claims)

    # 6. Validate audience
    validate_audience_claim(claims)

    return claims


def check_permission(required_permission: str):
    async def permission_dependency(creds: HTTPAuthorizationCredentials | None = Depends(security)):

        if creds is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        cred_token = creds.credentials
        verified_claims = await verify_token(cred_token)
        if not verified_claims:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
        if required_permission not in verified_claims.get("scopes", []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        
        return verified_claims
    
    return permission_dependency
