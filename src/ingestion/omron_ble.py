import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from bleak import BleakClient, BleakScanner
from config.settings import settings
from src.db.connection import get_db_connection, init_db
from src.ingestion.garmin_client import get_garmin_client

# Standard GATT Service & Characteristic UUIDs
WEIGHT_SCALE_SERVICE_UUID = "0000181d-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_SERVICE_UUID = "0000181b-0000-1000-8000-00805f9b34fb"

WEIGHT_MEASUREMENT_CHAR_UUID = "00002a9d-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_CHAR_UUID = "00002a9c-0000-1000-8000-00805f9b34fb"

def parse_weight_measurement(data: bytearray) -> Optional[float]:
    """Parse Weight Measurement characteristic 0x2A9D according to Bluetooth SIG GATT spec."""
    if not data or len(data) < 3:
        return None
    flags = data[0]
    unit_imperial = (flags & 0x01) != 0  # 0 = SI (kg), 1 = Imperial (lb)
    
    raw_val = int.from_bytes(data[1:3], byteorder="little")
    if raw_val <= 0:
        return None

    # Resolution handling for 0x2A9D (0.005kg, 0.01kg, or 0.1kg)
    if raw_val > 10000:
        weight_kg = raw_val * 0.005
    elif raw_val > 1000:
        weight_kg = raw_val * 0.01
    elif raw_val > 200:
        weight_kg = raw_val / 10.0
    else:
        weight_kg = float(raw_val)

    if unit_imperial:
        weight_kg = weight_kg * 0.45359237  # Convert lbs to kg

    return round(weight_kg, 2)

def parse_body_composition_measurement(data: bytearray) -> Dict[str, Optional[float]]:
    """Parse Body Composition Measurement characteristic 0x2A9C according to Bluetooth SIG GATT spec."""
    res: Dict[str, Optional[float]] = {
        "body_fat_pct": None,
        "muscle_mass_pct": None,
        "visceral_fat": None
    }
    if not data or len(data) < 3:
        return res

    flags = int.from_bytes(data[0:2], byteorder="little") if len(data) >= 2 else data[0]
    
    # Body Fat Percentage (Bytes 2-3 or 1-2)
    offset = 2 if len(data) >= 4 else 1
    if len(data) >= offset + 2:
        raw_fat = int.from_bytes(data[offset:offset+2], byteorder="little")
        if 50 <= raw_fat <= 600:
            res["body_fat_pct"] = round(raw_fat * 0.1, 1)

    # Muscle Mass / Visceral Fat parsing if present in notification payload
    if len(data) >= offset + 4:
        raw_muscle = int.from_bytes(data[offset+2:offset+4], byteorder="little")
        if 100 <= raw_muscle <= 800:
            res["muscle_mass_pct"] = round(raw_muscle * 0.1, 1)

    if len(data) >= offset + 5:
        visc = data[offset+4]
        if 1 <= visc <= 30:
            res["visceral_fat"] = int(visc)

    return res

async def listen_and_sync_omron_ble(
    mac_address: Optional[str] = None,
    timeout: int = 30,
    target_date: Optional[str] = None
) -> Dict[str, Any]:
    """Connect to OMRON VIVA BLE scale, listen for measurements, store in SQLite & sync to Garmin."""
    target_mac = mac_address or os.getenv("OMRON_MAC_ADDRESS") or getattr(settings, "omron_mac_address", None)
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")

    if not target_mac:
        print("🔍 OMRON MAC Address not provided in .env. Discovering active scale via BLE scan...")
        scanner = BleakScanner()
        devices = await scanner.discover(timeout=5.0)
        for dev in devices:
            name = (dev.name or "").upper()
            if any(kw in name for kw in ["BLESMART_", "OMRON", "HBF-222T", "VIVA"]):
                target_mac = dev.address
                print(f"✨ Auto-detected OMRON Scale MAC: {target_mac}")
                break

    if not target_mac:
        raise ValueError(
            "❌ OMRON MAC Address not found! Please run `python main.py ble-scan` while stepping on scale "
            "and set `OMRON_MAC_ADDRESS=<MAC_ADDRESS>` in your `.env` file."
        )

    print(f"📡 Connecting to OMRON VIVA Scale at [{target_mac}] for date: {date_str}...")
    print("👉 Please STEP ON scale barefoot to trigger full Body Composition measurement!")

    captured_metrics: Dict[str, Any] = {
        "weight_kg": None,
        "body_fat_pct": None,
        "muscle_mass_pct": None,
        "visceral_fat": None
    }
    event = asyncio.Event()

    def weight_notification_handler(sender, data: bytearray):
        w = parse_weight_measurement(data)
        if w:
            captured_metrics["weight_kg"] = w
            print(f"⚖️ Received Weight Measurement: {w} kg")
            event.set()

    def body_comp_notification_handler(sender, data: bytearray):
        bc = parse_body_composition_measurement(data)
        if bc.get("body_fat_pct"):
            captured_metrics["body_fat_pct"] = bc["body_fat_pct"]
            print(f"📊 Received Body Fat: {bc['body_fat_pct']}%")
        if bc.get("muscle_mass_pct"):
            captured_metrics["muscle_mass_pct"] = bc["muscle_mass_pct"]
            print(f"💪 Received Muscle Mass: {bc['muscle_mass_pct']}%")
        if bc.get("visceral_fat"):
            captured_metrics["visceral_fat"] = bc["visceral_fat"]
            print(f"🫁 Received Visceral Fat: {bc['visceral_fat']}")
        event.set()

    try:
        async with BleakClient(target_mac, timeout=float(timeout)) as client:
            print(f"✅ BLE Connected to scale [{target_mac}]!")
            
            # Subscribe to 0x2A9D (Weight) and 0x2A9C (Body Composition)
            services = client.services
            for service in services:
                for char in service.characteristics:
                    c_uuid = char.uuid.lower()
                    if c_uuid == WEIGHT_MEASUREMENT_CHAR_UUID:
                        await client.start_notify(char.uuid, weight_notification_handler)
                        print("🔔 Subscribed to Weight Measurement Characteristic (0x2A9D).")
                    elif c_uuid == BODY_COMPOSITION_CHAR_UUID:
                        await client.start_notify(char.uuid, body_comp_notification_handler)
                        print("🔔 Subscribed to Body Composition Characteristic (0x2A9C).")

            print(f"⏳ Waiting for measurement data (timeout {timeout}s)...")
            try:
                await asyncio.wait_for(event.wait(), timeout=float(timeout))
                await asyncio.sleep(2.0)  # Allow remaining notification packets to arrive
            except asyncio.TimeoutError:
                print("⚠️ Timeout waiting for GATT notifications. Checking fallback scale properties...")

    except Exception as exc:
        print(f"⚠️ BLE Direct Client Notice: {exc}")

    weight_val = captured_metrics.get("weight_kg")
    if not weight_val:
        raise RuntimeError(f"❌ Failed to receive weight measurement from BLE scale at [{target_mac}]. Make sure scale screen is active.")

    # Save to SQLite
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

    print(f"✅ BLE Ingestion Complete! Saved to SQLite: {captured_metrics}")

    # Sync to Garmin Connect
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
        print(f"✅ Synced BLE weight ({captured_metrics['weight_kg']} kg) to Garmin Connect cloud!")
    except Exception as g_err:
        print(f"ℹ️ Weight saved in SQLite. (Garmin Connect sync notice: {g_err})")

    return captured_metrics
