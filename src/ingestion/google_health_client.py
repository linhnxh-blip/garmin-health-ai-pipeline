import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.db.connection import get_db_connection, init_db
from src.ingestion.garmin_client import get_garmin_client

SCOPES = [
    "https://www.googleapis.com/auth/fitness.body.read",
]

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CREDENTIALS_PATH = BASE_DIR / "credentials.json"
DEFAULT_TOKEN_PATH = BASE_DIR / "token.json"

def get_google_fit_credentials(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH
) -> Optional[Credentials]:
    """Retrieve or authenticate Google OAuth 2.0 Credentials."""
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as err:
            print(f"⚠️ Failed to load existing Google token from {token_path}: {err}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as refresh_err:
                print(f"⚠️ Refreshing Google OAuth token failed: {refresh_err}. Re-authenticating...")
                creds = None

        if not creds:
            if not credentials_path.exists():
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())

    return creds

def parse_google_fit_dataset_points(dataset: Dict[str, Any]) -> Dict[str, float]:
    """Extract weight and body fat values from Google Fit dataset/bucket structure."""
    results: Dict[str, float] = {}
    for point in dataset.get("point", []):
        data_type_name = point.get("dataTypeName", "")
        value_list = point.get("value", [])
        if not value_list:
            continue
        val = value_list[0].get("fpVal") if "fpVal" in value_list[0] else value_list[0].get("intVal")
        if val is None:
            continue

        if "weight" in data_type_name or "com.google.weight" in data_type_name:
            results["weight_kg"] = round(float(val), 2)
        elif "body.fat" in data_type_name or "com.google.body.fat" in data_type_name:
            results["body_fat_pct"] = round(float(val), 2)
    return results

def fetch_and_store_google_health_data(
    target_date: str,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
    verbose: bool = True
) -> Optional[Dict[str, float]]:
    """Fetch Weight and Body Fat from Google Fitness REST API for target_date (YYYY-MM-DD),
    save to SQLite daily_metrics, and sync to Garmin Connect cloud if available.
    """
    creds = get_google_fit_credentials(credentials_path, token_path)
    if not creds:
        if verbose:
            print(f"ℹ️ Google Fitness credentials file (`credentials.json`) not found at {credentials_path}. Skipping Google Health sync.")
        return None

    try:
        service = build("fitness", "v1", credentials=creds)

        start_dt = datetime.strptime(target_date, "%Y-%m-%d")
        end_dt = start_dt + timedelta(days=1) - timedelta(milliseconds=1)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        # 1. Aggregate Query
        aggregate_body = {
            "aggregateBy": [
                {"dataTypeName": "com.google.weight"},
                {"dataTypeName": "com.google.body.fat.percentage"}
            ],
            "startTimeMillis": start_ms,
            "endTimeMillis": end_ms
        }

        agg_res = service.users().dataset().aggregate(userId="me", body=aggregate_body).execute()

        extracted_metrics: Dict[str, float] = {}
        for bucket in agg_res.get("bucket", []):
            for ds in bucket.get("dataset", []):
                parsed = parse_google_fit_dataset_points(ds)
                extracted_metrics.update(parsed)

        # 2. Fallback to direct merged dataSources if aggregate returned missing fields
        if "weight_kg" not in extracted_metrics or "body_fat_pct" not in extracted_metrics:
            start_ns = start_ms * 1_000_000
            end_ns = end_ms * 1_000_000
            dataset_id = f"{start_ns}-{end_ns}"

            data_sources = [
                ("weight_kg", "derived:com.google.weight:com.google.android.gms:merge_weight"),
                ("body_fat_pct", "derived:com.google.body.fat.percentage:com.google.android.gms:merged")
            ]

            for metric_key, ds_id in data_sources:
                if metric_key not in extracted_metrics:
                    try:
                        ds_res = service.users().dataSources().datasets().get(
                            userId="me",
                            dataSourceId=ds_id,
                            datasetId=dataset_id
                        ).execute()
                        parsed = parse_google_fit_dataset_points(ds_res)
                        if metric_key in parsed:
                            extracted_metrics[metric_key] = parsed[metric_key]
                    except Exception:
                        pass

        if not extracted_metrics:
            if verbose:
                print(f"ℹ️ No Google Health weight or body fat data found for date: {target_date}")
            return {}

        weight_kg = extracted_metrics.get("weight_kg")
        body_fat_pct = extracted_metrics.get("body_fat_pct")

        # 3. Save / Upsert to SQLite daily_metrics
        init_db()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO daily_metrics (date, weight_kg, body_fat_pct, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    weight_kg = COALESCE(excluded.weight_kg, daily_metrics.weight_kg),
                    body_fat_pct = COALESCE(excluded.body_fat_pct, daily_metrics.body_fat_pct),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (target_date, weight_kg, body_fat_pct)
            )
            conn.commit()

        if verbose:
            weight_str = f"{weight_kg}kg" if weight_kg is not None else "N/A"
            fat_str = f"{body_fat_pct}%" if body_fat_pct is not None else "N/A"
            print(f"✅ Google Health Data Ingested ({target_date}): Weight={weight_str}, Body Fat={fat_str}")

        # 4. Sync weight to Garmin Connect Cloud if weight_kg is available
        if weight_kg is not None:
            try:
                garmin_client = get_garmin_client()
                iso_timestamp = f"{target_date}T08:00:00.000Z"
                garmin_client.add_body_composition(
                    timestamp=iso_timestamp,
                    weight=weight_kg,
                    percent_fat=body_fat_pct
                )
                if verbose:
                    print(f"✅ Synced Google Health weight ({weight_kg} kg) to Garmin Connect Cloud!")
            except Exception as garmin_err:
                if verbose:
                    print(f"ℹ️ Garmin Cloud weight sync notice: {garmin_err}")

        return extracted_metrics

    except Exception as exc:
        if verbose:
            print(f"⚠️ Error during Google Health ingestion for {target_date}: {exc}")
        return None
