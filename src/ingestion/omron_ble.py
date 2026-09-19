import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from bleak import BleakScanner, BleakClient
from config.settings import settings
from src.db.connection import get_db_connection, init_db
from src.ingestion.garmin_client import get_garmin_client

# OMRON Manufacturer ID (0x020E = 526)
OMRON_MFG_ID = 526
WEIGHT_SCALE_SERVICE_UUID = "0000181d-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_SERVICE_UUID = "0000181b-0000-1000-8000-00805f9b34fb"

WEIGHT_MEASUREMENT_CHAR_UUID = "00002a9d-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_CHAR_UUID = "00002a9c-0000-1000-8000-00805f9b34fb"

def parse_omron_mfg_data(data: bytes) -> Dict[str, Any]:
    """Parse OMRON BLE Manufacturer Data payload (ID 526 / 0x020E)."""
    res: Dict[str, Any] = {
        "weight_kg": None,
        "body_fat_pct": None,
        "muscle_mass_pct": None,
        "visceral_fat": None
    }
    if not data or len(data) < 4:
        return res

    # Bytes 2-3: Weight raw uint16
    w_raw = int.from_bytes(data[2:4], "little")
    if 1000 <= w_raw <= 4000:
        res["weight_kg"] = round(w_raw * 0.05, 2)
    elif 5000 <= w_raw <= 25000:
        res["weight_kg"] = round(w_raw * 0.01, 2)
    elif 200 <= w_raw <= 1000:
        res["weight_kg"] = round(w_raw / 10.0, 2)

    # Byte 5: Body Fat %
    if len(data) >= 6:
        fat_raw = data[5]
        if 50 <= fat_raw <= 500:
            res["body_fat_pct"] = round(fat_raw * 0.1, 1)

    # Byte 8: Muscle Mass %
    if len(data) >= 9:
        mus_raw = data[8]
        if 100 <= mus_raw <= 600:
            res["muscle_mass_pct"] = round(mus_raw * 0.1, 1)

    # Byte 11/13: Visceral Fat
    if len(data) >= 12:
        visc_raw = data[11]
        if 1 <= visc_raw <= 30:
            res["visceral_fat"] = int(visc_raw)

    return res

def parse_weight_measurement_gatt(data: bytearray) -> Optional[float]:
    """Parse Weight Measurement characteristic 0x2A9D according to Bluetooth SIG GATT spec."""
    if not data or len(data) < 3:
        return None
    flags = data[0]
    unit_imperial = (flags & 0x01) != 0
    
    raw_val = int.from_bytes(data[1:3], byteorder="little")
    if raw_val <= 0:
        return None

    if raw_val > 10000:
        weight_kg = raw_val * 0.005
    elif raw_val > 1000:
        weight_kg = raw_val * 0.01
    elif raw_val > 200:
        weight_kg = raw_val / 10.0
    else:
        weight_kg = float(raw_val)

    if unit_imperial:
        weight_kg = weight_kg * 0.45359237

    return round(weight_kg, 2)

async def listen_and_sync_omron_ble(
    mac_address: Optional[str] = None,
    timeout: int = 30,
    target_date: Optional[str] = None
) -> Dict[str, Any]:
    """Listen for live OMRON VIVA BLE measurements (via BLE broadcast packets & GATT), store in SQLite & sync to Garmin."""
    target_mac = (mac_address or os.getenv("OMRON_MAC_ADDRESS") or getattr(settings, "omron_mac_address", None) or "").strip().upper()
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")

    print(f"📡 Starting BLE Scale Listener for date: {date_str} (Timeout: {timeout}s)...")
    if target_mac:
        print(f"🎯 Target Scale MAC: [{target_mac}]")
    else:
        print("🔍 Searching for any nearby OMRON/BLE scale...")

    print("👉 Please STEP ON your OMRON VIVA scale NOW to transmit measurements!\n")

    captured_metrics: Dict[str, Any] = {
        "weight_kg": None,
        "body_fat_pct": None,
        "muscle_mass_pct": None,
        "visceral_fat": None
    }
    event = asyncio.Event()

    # 1. BLE Advertisement Packet Callback (Passive/Active Broadcast Receiver)
    def adv_callback(device, adv_data):
        name = (device.name or adv_data.local_name or "").upper()
        addr = device.address.upper()

        is_match = False
        if target_mac and addr == target_mac:
            is_match = True
        elif any(kw in name for kw in ["BLESMART_", "OMRON", "HBF-222T", "VIVA"]):
            is_match = True

        if not is_match:
            return

        # Check Manufacturer Data ID 526 (0x020E = OMRON) or other scale IDs
        mfg_data = adv_data.manufacturer_data.get(OMRON_MFG_ID)
        if not mfg_data and adv_data.manufacturer_data:
            # Fallback to any manufacturer payload if present
            for m_id, m_bytes in adv_data.manufacturer_data.items():
                if len(m_bytes) >= 4:
                    mfg_data = m_bytes
                    break

        if mfg_data:
            parsed = parse_omron_mfg_data(mfg_data)
            w = parsed.get("weight_kg")
            if w and 30.0 <= w <= 250.0:
                captured_metrics["weight_kg"] = w
                if parsed.get("body_fat_pct"):
                    captured_metrics["body_fat_pct"] = parsed["body_fat_pct"]
                if parsed.get("muscle_mass_pct"):
                    captured_metrics["muscle_mass_pct"] = parsed["muscle_mass_pct"]
                if parsed.get("visceral_fat"):
                    captured_metrics["visceral_fat"] = parsed["visceral_fat"]

                print(f"⚖️ [BLE Broadcast] Captured Weight: {captured_metrics['weight_kg']} kg | Fat: {captured_metrics.get('body_fat_pct') or 'N/A'}% | Visceral: {captured_metrics.get('visceral_fat') or 'N/A'}")
                event.set()

    scanner = BleakScanner(detection_callback=adv_callback)
    await scanner.start()

    try:
        await asyncio.wait_for(event.wait(), timeout=float(timeout))
        print("✅ Received live measurement broadcast packet!")
    except asyncio.TimeoutError:
        print("ℹ️ Broadcast scan timed out, checking direct GATT connection...")
    finally:
        await scanner.stop()

    # 2. Parallel GATT Connection Fallback if broadcast didn't capture weight
    if not captured_metrics.get("weight_kg") and target_mac:
        print(f"📡 Attempting direct GATT connection to [{target_mac}]...")
        try:
            async with BleakClient(target_mac, timeout=10.0) as client:
                for service in client.services:
                    for char in service.characteristics:
                        if char.uuid.lower() == WEIGHT_MEASUREMENT_CHAR_UUID:
                            val = await client.read_gatt_char(char.uuid)
                            w = parse_weight_measurement_gatt(val)
                            if w:
                                captured_metrics["weight_kg"] = w
                                print(f"⚖️ [GATT Read] Captured Weight: {w} kg")
        except Exception as gatt_err:
            print(f"ℹ️ GATT Connection Note: {gatt_err}")

    weight_val = captured_metrics.get("weight_kg")
    if not weight_val:
        raise RuntimeError(
            "❌ Could not capture weight measurement! Please make sure:\n"
            "   1. Bluetooth is turned ON on your PC.\n"
            "   2. You step on the OMRON scale barefoot so the screen shows your weight & body fat.\n"
            "   3. Run `python main.py ble-scan` to confirm scale MAC Address."
        )

    # Save to SQLite Database
    init_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_metrics (date, weight_kg, body_fat_pct, muscle_mass_pct, visceral_fat, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(date) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                body_fat_pct = COALESCE(excluded.body_fat_pct, daily_metrics.body_fat_pct),
                muscle_mass_pct = COALESCE(excluded.muscle_mass_pct, daily_metrics.muscle_mass_pct),
                visceral_fat = COALESCE(excluded.visceral_fat, daily_metrics.visceral_fat),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                date_str,
                captured_metrics["weight_kg"],
                captured_metrics["body_fat_pct"],
                captured_metrics["muscle_mass_pct"],
                captured_metrics["visceral_fat"]
            )
        )
        conn.commit()

    print(f"✅ BLE Ingestion Complete! Saved to SQLite `daily_metrics`: {captured_metrics}")

    # Sync to Garmin Connect Cloud
    try:
        g_client = get_garmin_client()
        iso_ts = f"{date_str}T08:00:00.000Z"
        g_client.add_body_composition(
            timestamp=iso_ts,
            weight=captured_metrics["weight_kg"],
            percent_fat=captured_metrics["body_fat_pct"],
            muscle_mass=captured_metrics["muscle_mass_pct"],
            visceral_fat_rating=captured_metrics["visceral_fat"]
        )
        print(f"✅ Successfully synced BLE weight ({captured_metrics['weight_kg']} kg) to Garmin Connect cloud!")
    except Exception as g_err:
        print(f"ℹ️ Weight recorded in SQLite database. (Garmin Connect sync note: {g_err})")

    return captured_metrics

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(listen_and_sync_omron_ble(timeout=15))
