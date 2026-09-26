import json
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.db.connection import get_db_connection

def calculate_deep_sleep_bb_correlation(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate Pearson correlation r between deep sleep seconds and body battery charged,
    and estimate average Body Battery points gained per 15 minutes of Deep Sleep.
    """
    pairs: List[Tuple[float, float]] = []
    for r in rows:
        ds = r.get("deep_sleep_seconds")
        bb = r.get("body_battery_charged")
        if ds is not None and bb is not None and ds > 0 and bb > 0:
            pairs.append((float(ds), float(bb)))

    if len(pairs) < 3:
        return {
            "correlation_r": None,
            "bb_per_15m_deep": None,
            "sample_count": len(pairs)
        }

    xs = [p[0] for p in pairs]  # deep sleep seconds
    ys = [p[1] for p in pairs]  # body battery charged

    n = len(pairs)
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)

    std_x = statistics.stdev(xs) if n > 1 else 0.0
    std_y = statistics.stdev(ys) if n > 1 else 0.0

    if std_x == 0 or std_y == 0:
        r_val = 0.0
        slope = 0.0
    else:
        cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / (n - 1)
        r_val = cov / (std_x * std_y)
        var_x = sum((x - mean_x) ** 2 for x in xs) / (n - 1)
        slope = cov / var_x if var_x > 0 else 0.0

    # Calculate Body Battery gained per 15 mins (900 seconds) of Deep Sleep
    bb_per_15m = slope * 900.0 if slope > 0 else (mean_y / (mean_x / 900.0) if mean_x > 0 else 0.0)

    return {
        "correlation_r": round(float(r_val), 2),
        "bb_per_15m_deep": round(float(bb_per_15m), 1),
        "sample_count": n
    }

def calculate_hrv_capacity(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate mean, std, and fatigue warning threshold (Mean - 1*Std) for overnight HRV."""
    vals = [float(r["hrv_last_night"]) for r in rows if r.get("hrv_last_night") is not None]

    if len(vals) < 2:
        return {
            "mean_hrv": round(vals[0], 1) if vals else None,
            "std_hrv": 0.0,
            "fatigue_threshold": None,
            "sample_count": len(vals)
        }

    mean_val = statistics.mean(vals)
    std_val = statistics.stdev(vals)
    fatigue_threshold = mean_val - std_val

    return {
        "mean_hrv": round(float(mean_val), 1),
        "std_hrv": round(float(std_val), 1),
        "fatigue_threshold": round(float(fatigue_threshold), 1),
        "sample_count": len(vals)
    }

def calculate_rhr_sensitivity(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate average Resting Heart Rate (RHR) elevation on the day following high stress days (>=35)."""
    rhr_vals = [float(r["resting_heart_rate"]) for r in rows if r.get("resting_heart_rate") is not None]
    if not rhr_vals:
        return {
            "baseline_rhr_mean": None,
            "avg_rhr_elevation": None,
            "high_stress_count": 0
        }

    baseline_rhr_mean = statistics.mean(rhr_vals)

    # Sort rows chronologically by date
    sorted_rows = sorted(rows, key=lambda x: x["date"])

    elevations: List[float] = []

    for i, r in enumerate(sorted_rows[:-1]):
        stress = r.get("avg_stress_level")
        if stress is not None and stress >= 35:
            # Check next day
            next_row = sorted_rows[i + 1]
            next_rhr = next_row.get("resting_heart_rate")
            if next_rhr is not None:
                elev = float(next_rhr) - baseline_rhr_mean
                elevations.append(elev)

    if not elevations:
        return {
            "baseline_rhr_mean": round(float(baseline_rhr_mean), 1),
            "avg_rhr_elevation": 0.0,
            "high_stress_count": 0
        }

    avg_elev = statistics.mean(elevations)
    return {
        "baseline_rhr_mean": round(float(baseline_rhr_mean), 1),
        "avg_rhr_elevation": round(float(avg_elev), 1),
        "high_stress_count": len(elevations)
    }

def extract_recent_running_dynamics(rows: List[Dict[str, Any]], target_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extract Cadence, GCT Balance, Stride Length, and Vertical Oscillation from the most recent run within last 14 days."""
    sorted_rows = sorted(rows, key=lambda x: x["date"], reverse=True)

    min_date_str = None
    if target_date:
        try:
            t_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
            min_date_str = (t_dt - timedelta(days=14)).strftime("%Y-%m-%d")
        except Exception:
            pass

    for r in sorted_rows:
        row_date = r.get("date")
        if min_date_str and row_date and row_date < min_date_str:
            continue

        act_summary_raw = r.get("activities_summary")
        if not act_summary_raw:
            continue
        try:
            acts = json.loads(act_summary_raw)
            if not isinstance(acts, list):
                continue
            for act in acts:
                act_type = str(act.get("type") or act.get("name") or "").lower()
                if "run" in act_type:
                    cadence = act.get("avg_cadence")
                    gct = act.get("gct_balance")
                    stride = act.get("stride_length_cm") or act.get("avg_stride_length")
                    vert_osc = act.get("vertical_oscillation_cm") or act.get("avg_vertical_oscillation")
                    if cadence or gct or stride or vert_osc:
                        return {
                            "date": r["date"],
                            "name": act.get("name") or "Chạy bộ",
                            "cadence": cadence,
                            "gct_balance": gct,
                            "stride_length_cm": stride,
                            "vertical_oscillation_cm": vert_osc
                        }
        except Exception:
            pass

    return None

def build_memory_context(
    target_date: str,
    days: Optional[int] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Retrieve all historical records prior to target_date and build Adaptive Memory Context.
    
    Returns dict:
      - memory_text: formatted string block for LLM prompt
      - memory_metrics: raw statistical metrics dict
    """
    rows: List[Dict[str, Any]] = []
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM daily_metrics
            WHERE date < ?
            ORDER BY date ASC
            """,
            (target_date,)
        )
        rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        return {
            "memory_text": "--- KHỐI TRÍ NHỚ ĐỘNG TỪ DỮ LIỆU LỊCH SỬ (ADAPTIVE MEMORY TÍCH LŨY) ---\nChưa có đủ dữ liệu lịch sử tích lũy để thiết lập trí nhớ động.",
            "memory_metrics": {}
        }

    deep_bb = calculate_deep_sleep_bb_correlation(rows)
    hrv_cap = calculate_hrv_capacity(rows)
    rhr_sens = calculate_rhr_sensitivity(rows)
    run_dyn = extract_recent_running_dynamics(rows, target_date=target_date)

    parts = []
    parts.append(f"--- KHỐI TRÍ NHỚ ĐỘNG TỪ DỮ LIỆU LỊCH SỬ (ADAPTIVE MEMORY {len(rows)} NGÀY TÍCH LŨY) ---")

    # 1. Deep sleep & BB
    if deep_bb["correlation_r"] is not None and deep_bb["bb_per_15m_deep"] is not None:
        parts.append(
            f"- Tương quan Giấc ngủ sâu & Body Battery: r = {deep_bb['correlation_r']} "
            f"(Mỗi 15 phút Deep Sleep nạp trung bình +{deep_bb['bb_per_15m_deep']} điểm Body Battery)."
        )
    else:
        parts.append("- Tương quan Giấc ngủ sâu & Body Battery: Chưa đủ mẫu đo lường.")

    # 2. HRV capacity
    if hrv_cap["mean_hrv"] is not None and hrv_cap["fatigue_threshold"] is not None:
        parts.append(
            f"- Khả năng chịu tải & Ngưỡng HRV: Mức trung bình {hrv_cap['mean_hrv']} ms (Std: {hrv_cap['std_hrv']} ms). "
            f"Ngưỡng cảnh báo mệt mỏi thần kinh: < {hrv_cap['fatigue_threshold']} ms."
        )
    else:
        parts.append("- Khả năng chịu tải & Ngưỡng HRV: Chưa đủ mẫu đo lường.")

    # 3. RHR sensitivity
    if rhr_sens["avg_rhr_elevation"] is not None and rhr_sens["avg_rhr_elevation"] != 0.0:
        sign = "+" if rhr_sens["avg_rhr_elevation"] > 0 else ""
        parts.append(
            f"- Phản ứng Nhịp tim nghỉ (RHR): Tăng trung bình {sign}{rhr_sens['avg_rhr_elevation']} bpm vào ngày tiếp theo sau những ngày Stress cao (>=35)."
        )
    else:
        parts.append("- Phản ứng Nhịp tim nghỉ (RHR): Duy trì ổn định sau các ngày stress cao.")

    # 4. Running Dynamics
    if run_dyn:
        cad_str = f"{run_dyn['cadence']} spm" if run_dyn.get("cadence") else "N/A"
        gct_val = run_dyn.get("gct_balance")
        if isinstance(gct_val, (int, float)):
            gct_str = f"{gct_val}% L / {round(100.0 - float(gct_val), 1)}% R"
        else:
            gct_str = str(gct_val) if gct_val else "N/A"
        
        extra_items = []
        if run_dyn.get("stride_length_cm"):
            extra_items.append(f"Chiều dài sải chân Stride Length = {run_dyn['stride_length_cm']} cm")
        if run_dyn.get("vertical_oscillation_cm"):
            extra_items.append(f"Dao động dọc Vertical Oscillation = {run_dyn['vertical_oscillation_cm']} cm")
        
        extra_str = (", " + ", ".join(extra_items)) if extra_items else ""

        parts.append(
            f"- Động học Chạy bộ HRM-Pro gần nhất ({run_dyn['date']} - {run_dyn['name']}): Cadence = {cad_str}, Cân bằng tiếp đất GCT (L/R) = {gct_str}{extra_str}."
        )
    else:
        parts.append("- Động học Chạy bộ HRM-Pro: Không có bài chạy trong 14 ngày gần nhất để đánh giá động học HRM-Pro.")


    memory_text = "\n".join(parts)
    memory_metrics = {
        "deep_sleep_bb": deep_bb,
        "hrv_capacity": hrv_cap,
        "rhr_sensitivity": rhr_sens,
        "running_dynamics": run_dyn
    }

    return {
        "memory_text": memory_text,
        "memory_metrics": memory_metrics
    }
