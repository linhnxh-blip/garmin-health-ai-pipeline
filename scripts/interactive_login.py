import os
import sys
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Ensure root project directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import garth
from config.settings import settings

ENV_PATH = BASE_DIR / ".env"
ENV_TXT_PATH = BASE_DIR / ".env.txt"
target_env = ENV_PATH if ENV_PATH.exists() else (ENV_TXT_PATH if ENV_TXT_PATH.exists() else ENV_PATH)
if target_env.exists():
    load_dotenv(dotenv_path=target_env, override=True)

PRIMARY_TOKEN_DIR = BASE_DIR / "data" / ".garmin_tokens"
SECONDARY_TOKEN_DIR = BASE_DIR / ".garminconnect"

def mfa_prompt_handler() -> str:
    print("\n🔐 Garmin account requires Multi-Factor Authentication (MFA/2FA).")
    code = input("👉 Enter the 6-digit OTP code sent to your email/phone: ").strip()
    return code

def main():
    print("=========================================================")
    print("   GARMIN INTERACTIVE LOGIN & OAUTH TOKEN GENERATOR")
    print("=========================================================")

    username = (
        settings.effective_garmin_username
        or os.getenv("GARMIN_USERNAME")
        or os.getenv("GARMIN_EMAIL")
        or ""
    ).strip()

    password = (
        settings.garmin_password
        or os.getenv("GARMIN_PASSWORD")
        or ""
    ).strip()

    if not username:
        username = input("👉 Enter Garmin Email/Username: ").strip()
    if not password:
        password = input("👉 Enter Garmin Password: ").strip()

    if not username or not password:
        print("❌ Username or password missing. Aborting.")
        sys.exit(1)

    print(f"🔄 Configuring garth (domain='garmin.com')...")
    garth.configure(domain="garmin.com")

    print(f"🔐 Logging in as '{username}' via garth SSO...")
    try:
        garth.login(username, password, prompt_mfa=mfa_prompt_handler)
        print("✅ Login successful via garth SSO!")
    except Exception as exc:
        print(f"❌ Garth login failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Clean old token files
    print("🧹 Cleaning old token caches in data/.garmin_tokens/ and .garminconnect/...")
    for d in [PRIMARY_TOKEN_DIR, SECONDARY_TOKEN_DIR]:
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        d.mkdir(parents=True, exist_ok=True)

    # Save fresh garth tokens
    print(f"💾 Saving OAuth tokens to '{PRIMARY_TOKEN_DIR}'...")
    garth.save(str(PRIMARY_TOKEN_DIR))

    # Also save to secondary dir
    print(f"💾 Syncing OAuth tokens to '{SECONDARY_TOKEN_DIR}'...")
    garth.save(str(SECONDARY_TOKEN_DIR))

    # Verify session with test API call
    print(f"✨ Testing session with API endpoint call (/usersummary-service/usersummary/daily/{username})...")
    try:
        res = garth.connectapi(f"/usersummary-service/usersummary/daily/{username}")
        if res:
            print(f"🎉 SUCCESS! Received valid user summary response from Garmin Connect API.")
            if isinstance(res, dict):
                total_steps = res.get("totalSteps")
                rhr = res.get("restingHeartRate")
                print(f"📊 Summary Data: Total Steps = {total_steps or 'N/A'}, RHR = {rhr or 'N/A'} bpm")
    except Exception as test_err:
        print(f"⚠️ Test API call warning: {test_err}")

    print("\n✅ Interactive login completed successfully!")
    print(f"📁 Tokens saved at: {PRIMARY_TOKEN_DIR / 'oauth2_token.json'}")

if __name__ == "__main__":
    main()
