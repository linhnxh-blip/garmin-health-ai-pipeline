import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="garth")
import garth
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
    GarminConnectConnectionError
)
from config.settings import settings, BASE_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure .env is explicitly loaded with absolute path
ENV_PATH = BASE_DIR / ".env"
ENV_TXT_PATH = BASE_DIR / ".env.txt"
target_env_file = ENV_PATH if ENV_PATH.exists() else (ENV_TXT_PATH if ENV_TXT_PATH.exists() else ENV_PATH)

if target_env_file.exists():
    load_dotenv(dotenv_path=target_env_file, override=True)

PRIMARY_TOKEN_DIR = BASE_DIR / "data" / ".garmin_tokens"
SECONDARY_TOKEN_DIR = BASE_DIR / ".garminconnect"

def mfa_prompt_handler() -> str:
    """Prompt user for Garmin 2FA/MFA code in terminal."""
    print("🔐 Garmin account requires Multi-Factor Authentication (MFA).")
    code = input("👉 Enter the 6-digit MFA code sent to your email/phone: ").strip()
    return code

def _find_existing_token_dir() -> Optional[Path]:
    """Check for existing token directory containing oauth2_token.json, garmin_tokens.json, or oauth1_token.json."""
    for d in [PRIMARY_TOKEN_DIR, SECONDARY_TOKEN_DIR, Path(settings.garmin_token_dir)]:
        if (
            (d / "oauth2_token.json").exists()
            or (d / "garmin_tokens.json").exists()
            or (d / "oauth1_token.json").exists()
        ):
            return d
    return None

def get_garmin_client(
    email: Optional[str] = None,
    password: Optional[str] = None,
    token_dir: Optional[str] = None
) -> Garmin:
    """Initialize and return authenticated Garmin Connect client.
    
    STRICT 429 / 403 CLOUDFLARE SAFEGUARD:
    Loads cached garth token files (`oauth1_token.json`, `oauth2_token.json`) directly from disk.
    Bypasses `_load_social_profile()` and NEVER calls network SSO login endpoints when tokens exist.
    Verifies session using a lightweight data endpoint (`get_user_summary`).
    """
    user_email = (
        email
        or settings.effective_garmin_username
        or os.getenv("GARMIN_USERNAME")
        or os.getenv("GARMIN_EMAIL")
        or ""
    ).strip()

    user_password = (
        password
        or settings.garmin_password
        or os.getenv("GARMIN_PASSWORD")
        or ""
    ).strip()

    token_path = Path(token_dir or settings.garmin_token_dir)
    if not token_path.is_absolute():
        token_path = BASE_DIR / token_path

    # 1. CHECK FOR SAVED TOKEN DIRECTORY
    existing_token_dir = _find_existing_token_dir() or (token_path if (token_path / "oauth2_token.json").exists() else None)

    if existing_token_dir:
        token_store_str = str(existing_token_dir)
        print(f"🔑 Found saved Garmin token directory at '{existing_token_dir}'. Loading tokens via garth...")

        # Resume garth session from disk
        try:
            garth.resume(token_store_str)
            print("✅ Garth session resumed successfully from disk tokens.")
        except Exception as g_err:
            print(f"ℹ️ Garth resume note: {g_err}")

        # Instantiate Garmin WITHOUT credentials so garminconnect CANNOT call SSO network auth
        client = Garmin(prompt_mfa=mfa_prompt_handler)
        
        try:
            # Direct token load into underlying HTTP client (bypasses _load_profile_and_settings)
            client.client.load(token_store_str)
            print("✅ Session tokens loaded cleanly into Garmin HTTP client.")

            # Retrieve real displayName from socialProfile API endpoint to prevent 403 on user summary queries
            try:
                prof = client.connectapi("/userprofile-service/socialProfile")
                if isinstance(prof, dict) and prof.get("displayName"):
                    client.display_name = prof["displayName"]
                    print(f"👤 Resolved Garmin display name: '{client.display_name}'")
                elif user_email:
                    client.display_name = user_email
            except Exception as prof_err:
                print(f"ℹ️ Could not resolve social profile display name ({prof_err}), using fallback.")
                if user_email:
                    client.display_name = user_email

            # Lightweight verification call using actual data endpoint
            today_str = datetime.now().strftime("%Y-%m-%d")
            try:
                summary = client.get_user_summary(today_str)
                print("✅ Verified session with lightweight data endpoint query (get_user_summary).")
            except Exception as data_err:
                print(f"ℹ️ Token restored (data query info: {data_err})")

            return client
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            resp_text = getattr(getattr(exc, "response", None), "text", None)

            print(f"❌ Saved token load failed: {exc}", file=sys.stderr)
            if status_code:
                print(f"   - HTTP Status Code: {status_code}", file=sys.stderr)
            if resp_text:
                print(f"   - Response Snippet: {resp_text[:300]}", file=sys.stderr)

            print("⚠️ [429/403 SAFEGUARD ACTIVATED] Garmin network SSO login was NOT attempted to protect your IP.", file=sys.stderr)
            print("👉 Please run `python scripts/interactive_login.py` to refresh or import valid token files.", file=sys.stderr)
            raise RuntimeError(
                f"Saved token error (HTTP {status_code or 'N/A'}): {exc}. Please update tokens using `python scripts/interactive_login.py`."
            )

    # 2. NO TOKEN FILES FOUND - ATTEMPT INITIAL NETWORK LOGIN
    if not user_email or not user_password:
        print("⚠️ Warning: No cached token found and Garmin credentials in .env are empty!", file=sys.stderr)
        raise ValueError(
            "Garmin username/password not found. Please configure GARMIN_USERNAME and GARMIN_PASSWORD in .env "
            "or run `python scripts/interactive_login.py` to generate tokens."
        )

    print(f"⚠️ No cached token files found in '{token_path}'. Attempting initial network login as '{user_email}'...")
    token_path.mkdir(parents=True, exist_ok=True)
    token_store_str = str(token_path)

    try:
        garth.configure(domain="garmin.com")
        garth.login(user_email, user_password, prompt_mfa=mfa_prompt_handler)
        garth.save(token_store_str)
        print(f"✅ Login successful via garth! Session tokens cached at '{token_store_str}'.")

        client = Garmin(prompt_mfa=mfa_prompt_handler)
        client.display_name = user_email
        client.client.load(token_store_str)
        return client
    except GarminConnectTooManyRequestsError as e:
        print(f"\n❌ Garmin 429 Rate Limit hit: {e}", file=sys.stderr)
        print("💡 Solution: Run `python scripts/interactive_login.py` to authenticate interactively.", file=sys.stderr)
        raise RuntimeError(f"Garmin 429 Rate Limit: {e}") from e
    except GarminConnectAuthenticationError as e:
        raise RuntimeError(f"❌ Garmin Authentication failed: Invalid username or password ({e})")
    except GarminConnectConnectionError as e:
        raise RuntimeError(f"❌ Network connection error reaching Garmin servers ({e})")
    except Exception as e:
        raise RuntimeError(f"❌ Garmin Login failed with error: {e}")
