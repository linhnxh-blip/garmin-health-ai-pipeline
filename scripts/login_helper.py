import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
    GarminConnectConnectionError
)
from config.settings import settings

ENV_PATH = BASE_DIR / ".env"
ENV_TXT_PATH = BASE_DIR / ".env.txt"
target_env = ENV_PATH if ENV_PATH.exists() else (ENV_TXT_PATH if ENV_TXT_PATH.exists() else ENV_PATH)
if target_env.exists():
    load_dotenv(dotenv_path=target_env, override=True)

PRIMARY_TOKEN_DIR = BASE_DIR / "data" / ".garmin_tokens"
SECONDARY_TOKEN_DIR = BASE_DIR / ".garminconnect"

def mfa_prompt_handler() -> str:
    print("\n🔐 Garmin account requires Multi-Factor Authentication (MFA).")
    code = input("👉 Enter the 6-digit MFA code sent to your email/phone: ").strip()
    return code

def parse_and_extract_tokens(raw_input: str) -> Dict[str, Any]:
    """Parse raw string input (JSON, browser localStorage dump, cookies, or key-value pairs)
    and extract oauth2_token, oauth1_token, and garmin_tokens structures.
    """
    raw_str = raw_input.strip()
    data: Dict[str, Any] = {}

    try:
        parsed = json.loads(raw_str)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        pass

    if not data:
        # Regex search for access_token, refresh_token, etc.
        acc = re.search(r'["\']?access_token["\']?\s*[:=]\s*["\']?([^"\'\s,;{}]+)["\']?', raw_str, re.IGNORECASE)
        ref = re.search(r'["\']?refresh_token["\']?\s*[:=]\s*["\']?([^"\'\s,;{}]+)["\']?', raw_str, re.IGNORECASE)
        scope_m = re.search(r'["\']?scope["\']?\s*[:=]\s*["\']?([^"\'\s,;{}]+)["\']?', raw_str, re.IGNORECASE)

        if acc:
            data["access_token"] = acc.group(1)
        if ref:
            data["refresh_token"] = ref.group(1)
        if scope_m:
            data["scope"] = scope_m.group(1)

    access_token = data.get("access_token") or data.get("di_token") or data.get("token")
    refresh_token = data.get("refresh_token") or data.get("di_refresh_token")
    scope = data.get("scope") or "COMMUNITY_READ COMMUNITY_WRITE"
    token_type = data.get("token_type") or "Bearer"
    expires_at = data.get("expires_at") or (int(time.time()) + (30 * 86400))

    oauth2_token = {
        "scope": scope,
        "jti": data.get("jti") or "dummy_jti",
        "token_type": token_type,
        "access_token": access_token or "dummy_access_token",
        "refresh_token": refresh_token or "dummy_refresh_token",
        "expires_in": data.get("expires_in") or 3600,
        "expires_at": expires_at,
        "refresh_token_expires_in": data.get("refresh_token_expires_in") or 7776000,
        "refresh_token_expires_at": data.get("refresh_token_expires_at") or 1799999999
    }

    oauth1_token = data.get("oauth1_token") or {
        "oauth_token": data.get("oauth_token", "dummy_oauth1_token"),
        "oauth_token_secret": data.get("oauth_token_secret", "dummy_oauth1_secret")
    }

    garmin_tokens = {
        "di_token": access_token or "dummy_di_token",
        "di_refresh_token": refresh_token or "dummy_di_refresh_token",
        "di_client_id": data.get("di_client_id", "garmin_connect")
    }

    return {
        "oauth2_token": oauth2_token,
        "oauth1_token": oauth1_token,
        "garmin_tokens": garmin_tokens
    }

def _save_token_files(tokens_dict: Dict[str, Any]) -> None:
    for target_dir in [PRIMARY_TOKEN_DIR, SECONDARY_TOKEN_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)

        f_oauth2 = target_dir / "oauth2_token.json"
        f_oauth1 = target_dir / "oauth1_token.json"
        f_garmin = target_dir / "garmin_tokens.json"

        f_oauth2.write_text(json.dumps(tokens_dict["oauth2_token"], indent=2), encoding="utf-8")
        f_oauth1.write_text(json.dumps(tokens_dict["oauth1_token"], indent=2), encoding="utf-8")
        f_garmin.write_text(json.dumps(tokens_dict["garmin_tokens"], indent=2), encoding="utf-8")

    print(f"✅ Token files saved successfully to:\n   - {PRIMARY_TOKEN_DIR}\n   - {SECONDARY_TOKEN_DIR}")

def attempt_login_with_retry(max_retries: int = 3, initial_delay: int = 5) -> bool:
    """Attempt Garmin login with retry backoff to bypass rate limiting."""
    user_email = settings.effective_garmin_username
    user_password = settings.garmin_password

    if not user_email or not user_password:
        print("❌ Error: GARMIN_USERNAME/GARMIN_EMAIL or GARMIN_PASSWORD missing in .env.")
        user_email = input("👉 Enter Garmin Email/Username: ").strip()
        user_password = input("👉 Enter Garmin Password: ").strip()

    if not user_email or not user_password:
        print("❌ Credentials empty. Aborting login.")
        return False

    PRIMARY_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    token_store_str = str(PRIMARY_TOKEN_DIR)

    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        print(f"\n🔐 Attempting Garmin Connect login ({attempt}/{max_retries}) as '{user_email}'...")
        client = Garmin(email=user_email, password=user_password, prompt_mfa=mfa_prompt_handler)
        try:
            client.login(tokenstore=token_store_str)
            client.dump(token_store_str)

            token_data = {
                "access_token": getattr(client.client, "di_token", None),
                "refresh_token": getattr(client.client, "di_refresh_token", None),
            }
            tokens_dict = parse_and_extract_tokens(json.dumps(token_data))
            _save_token_files(tokens_dict)

            print(f"🎉 Login successful! Session tokens cached.")
            return True
        except GarminConnectTooManyRequestsError as e:
            print(f"⚠️ 429 Rate Limit encountered on attempt {attempt}: {e}")
            if attempt < max_retries:
                print(f"⏳ Waiting {delay} seconds before retrying...")
                time.sleep(delay)
                delay *= 2
            else:
                print("\n❌ Garmin Rate Limit (429) active. Automated login blocked by Garmin Cloudflare protection.")
                print_manual_token_instructions()
                return False
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            resp_text = getattr(getattr(e, "response", None), "text", None)
            print(f"❌ Login failed: {e}")
            if status_code:
                print(f"   - HTTP Status Code: {status_code}")
            if resp_text:
                print(f"   - Response Body Snippet: {resp_text[:300]}")

            if attempt < max_retries and ("429" in str(e).lower() or "403" in str(e).lower()):
                print(f"⏳ Waiting {delay} seconds before retrying...")
                time.sleep(delay)
                delay *= 2
            else:
                print_manual_token_instructions()
                return False
    return False

def import_token_json_interactive() -> bool:
    """Import token JSON/dump from file or direct text paste."""
    print("\n--- IMPORT GARMIN SESSION TOKEN / LOCALSTORAGE DUMP ---")
    print("1. Enter file path to token/localStorage JSON dump")
    print("2. Paste raw JSON text / access_token directly")
    choice = input("Select option (1 or 2): ").strip()

    raw_text = ""
    if choice == "1":
        path_str = input("Enter path to file: ").strip().strip('"').strip("'")
        file_p = Path(path_str)
        if not file_p.exists():
            print(f"❌ File not found at '{file_p}'")
            return False
        raw_text = file_p.read_text(encoding="utf-8")
    else:
        print("Paste your Garmin token/localStorage content below (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if not line and lines:
                break
            lines.append(line)
        raw_text = "\n".join(lines).strip()

    if not raw_text:
        print("❌ Empty input content.")
        return False

    try:
        tokens_dict = parse_and_extract_tokens(raw_text)
        _save_token_files(tokens_dict)
        print("✨ Validating saved token offline with Garmin client...")
        return check_token_status()
    except Exception as err:
        print(f"❌ Failed to parse and save token: {err}")
        return False

def check_token_status() -> bool:
    """Check if token files exist and can restore session offline, printing detailed HTTP errors on failure."""
    print("\n🔍 Checking existing Garmin token status...")
    token_files = []
    for d in [PRIMARY_TOKEN_DIR, SECONDARY_TOKEN_DIR]:
        for fname in ["oauth2_token.json", "garmin_tokens.json", "oauth1_token.json"]:
            fp = d / fname
            if fp.exists() and fp.stat().st_size > 0:
                token_files.append(fp)

    if not token_files:
        print("❌ No token files found in `data/.garmin_tokens/` or `.garminconnect/`.")
        return False

    print(f"🔑 Found {len(token_files)} token file(s) across token directories:")
    for tf in token_files:
        print(f"   - {tf}")

    target_dir = token_files[0].parent
    user_email = settings.effective_garmin_username

    client = Garmin(prompt_mfa=mfa_prompt_handler)

    try:
        # Direct token load into underlying HTTP client (bypasses _load_profile_and_settings)
        client.client.load(str(target_dir))
        print("✅ Session tokens loaded cleanly into Garmin HTTP client.")

        try:
            prof = client.connectapi("/userprofile-service/socialProfile")
            if isinstance(prof, dict) and prof.get("displayName"):
                client.display_name = prof["displayName"]
                print(f"👤 Resolved Garmin display name: '{client.display_name}'")
            elif user_email:
                client.display_name = user_email
        except Exception:
            if user_email:
                client.display_name = user_email

        today_str = time.strftime("%Y-%m-%d")
        try:
            summary = client.get_user_summary(today_str)
            print("✅ Successfully verified session with lightweight data query (get_user_summary).")
            if isinstance(summary, dict):
                total_steps = summary.get("totalSteps")
                rhr = summary.get("restingHeartRate")
                print(f"📊 Summary data fetched: Total Steps = {total_steps or 'N/A'}, RHR = {rhr or 'N/A'} bpm")
            return True
        except Exception as data_err:
            status_code = getattr(getattr(data_err, "response", None), "status_code", None)
            resp_text = getattr(getattr(data_err, "response", None), "text", None)
            print(f"⚠️ Token loaded but data endpoint query failed: {data_err}")
            if status_code:
                print(f"   - HTTP Status Code: {status_code}")
            if resp_text:
                print(f"   - Response Body Snippet: {resp_text[:300]}")
            return False
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        resp_text = getattr(getattr(exc, "response", None), "text", None)
        print(f"❌ Saved token failed to load: {exc}")
        if status_code:
            print(f"   - HTTP Status Code: {status_code}")
        if resp_text:
            print(f"   - Response Body Snippet: {resp_text[:300]}")
        print("💡 The token in 'data/.garmin_tokens/' may be expired or invalid.")
        return False

def print_manual_token_instructions() -> None:
    print("\n============================================================")
    print("💡 HƯỚNG DẪN NẠP TOKEN THỦ CÔNG KHI BỊ GARMIN CHẶN 429/403:")
    print("============================================================")
    print("Nếu bạn có token session từ một trình duyệt hoặc thiết bị khác:")
    print(f"1. Tạo thư mục: {PRIMARY_TOKEN_DIR}")
    print(f"2. Tạo file {PRIMARY_TOKEN_DIR / 'oauth2_token.json'} với định dạng:")
    print("""   {
     "scope": "COMMUNITY_READ COMMUNITY_WRITE",
     "token_type": "Bearer",
     "access_token": "<YOUR_ACCESS_TOKEN>",
     "refresh_token": "<YOUR_REFRESH_TOKEN>",
     "expires_at": 1770000000
   }""")
    print("3. Chạy `python scripts/login_helper.py check` để kiểm tra.")
    print("============================================================\n")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "login":
            attempt_login_with_retry()
        elif cmd in ("import", "import-json"):
            import_token_json_interactive()
        elif cmd == "check":
            check_token_status()
        else:
            print(f"Unknown command '{cmd}'. Usage: python scripts/login_helper.py [login|import|check]")
        return

    # Interactive Menu if run without arguments
    while True:
        print("\n==========================================")
        print("   GARMIN LOGIN & TOKEN HELPER (429 SAFE) ")
        print("==========================================")
        print("1. Thử đăng nhập tự động (Login with Retry/Delay)")
        print("2. Nạp file / dán trực tiếp Token JSON / localStorage (Import Token)")
        print("3. Kiểm tra trạng thái Token hiện tại (Check Token)")
        print("4. Thoát (Exit)")
        choice = input("👉 Chọn thao tác (1-4): ").strip()

        if choice == "1":
            attempt_login_with_retry()
        elif choice == "2":
            import_token_json_interactive()
        elif choice == "3":
            check_token_status()
        elif choice in ("4", "q", "exit"):
            print("Bye!")
            break

if __name__ == "__main__":
    main()
