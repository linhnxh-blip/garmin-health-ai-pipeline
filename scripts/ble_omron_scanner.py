import asyncio
import sys
from typing import Dict, Any
from bleak import BleakScanner

# Standard GATT Service UUIDs for Scale & Body Composition
WEIGHT_SCALE_SERVICE_UUID = "0000181d-0000-1000-8000-00805f9b34fb"
BODY_COMPOSITION_SERVICE_UUID = "0000181b-0000-1000-8000-00805f9b34fb"

OMRON_KEYWORDS = ["BLESMART_", "OMRON", "HBF-222T", "HBF-", "VIVA", "SCALE", "WEIGHT"]

async def scan_omron_ble(duration: int = 10):
    print(f"📡 Scanning for Bluetooth Low Energy (BLE) scales for {duration} seconds...")
    print("👉 Please STEP ON your OMRON VIVA scale to activate Bluetooth broadcasting!\n")

    devices_dict: Dict[str, Dict[str, Any]] = {}

    def detection_callback(device, advertisement_data):
        name = device.name or advertisement_data.local_name or "Unknown"
        uuids = [str(u).lower() for u in advertisement_data.service_uuids or []]
        name_upper = name.upper()

        is_target = any(kw in name_upper for kw in OMRON_KEYWORDS) or any(
            u in uuids for u in [WEIGHT_SCALE_SERVICE_UUID, BODY_COMPOSITION_SERVICE_UUID]
        )

        devices_dict[device.address] = {
            "address": device.address,
            "name": name,
            "rssi": advertisement_data.rssi,
            "uuids": uuids,
            "is_target": is_target,
        }

    scanner = BleakScanner(detection_callback)
    await scanner.start()
    await asyncio.sleep(duration)
    await scanner.stop()

    print("================ BLE DISCOVERY RESULTS ================")
    matched = []
    other = []

    for addr, dev in devices_dict.items():
        if dev["is_target"]:
            matched.append(dev)
        else:
            other.append(dev)

    if matched:
        print(f"✨ Found {len(matched)} matching Scale/OMRON device(s):")
        for idx, dev in enumerate(matched, 1):
            print(f"  [{idx}] NAME: {dev['name']}")
            print(f"      MAC/ADDRESS: {dev['address']}")
            print(f"      RSSI: {dev['rssi']} dBm")
            print(f"      SERVICES: {dev['uuids'] or 'None'}")
            print(f"      💡 Add to .env: OMRON_MAC_ADDRESS={dev['address']}\n")
    else:
        print("⚠️ No specific OMRON/Scale keyword matched.")
        print(f"📋 Discovered {len(other)} other nearby BLE device(s):")
        for dev in other[:15]:
            print(f"  - [{dev['name']}] MAC: {dev['address']} | RSSI: {dev['rssi']} dBm | Services: {dev['uuids']}")

    return matched

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(scan_omron_ble(duration=10))
