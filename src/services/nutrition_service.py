"""
Nutrition Service Module.
Provides comparison and formatting logic for daily nutrition progress and meal logging.
"""

from typing import Dict, Any, Optional
from pathlib import Path

def format_daily_progress(logged: dict, target: dict) -> str:
    """
    Format side-by-side comparison of daily logged nutrition vs target.
    Displays surplus (Thừa), deficit (Còn thiếu), or on-target (Chuẩn đạt mục tiêu).
    """
    cal_logged = float(logged["cal"] if "cal" in logged else logged.get("total_cal", 0.0))
    p_logged = float(logged["p"] if "p" in logged else logged.get("total_protein", logged.get("protein_g", 0.0)))
    c_logged = float(logged["c"] if "c" in logged else logged.get("total_carbs", logged.get("carb_g", 0.0)))
    f_logged = float(logged["f"] if "f" in logged else logged.get("total_fat", logged.get("fat_g", 0.0)))

    cal_target = float(target["cal"] if "cal" in target else target.get("target_calories", target.get("total_cal", 0.0)))
    p_target = float(target["p"] if "p" in target else target.get("protein_g", target.get("total_protein", 0.0)))
    c_target = float(target["c"] if "c" in target else target.get("carb_g", target.get("total_carbs", 0.0)))
    f_target = float(target["f"] if "f" in target else target.get("fat_g", target.get("total_fat", 0.0)))

    # Compute deltas
    cal_diff = round(cal_logged - cal_target, 1)
    p_diff = round(p_logged - p_target, 1)
    c_diff = round(c_logged - c_target, 1)
    f_diff = round(f_logged - f_target, 1)

    def format_stat(val_logged, val_target, diff, unit="g"):
        pct = round((val_logged / val_target) * 100, 0) if val_target > 0 else 0
        if diff > 5:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Thừa +{diff:.1f}{unit} | {pct:.0f}%) ⚠️"
        elif diff < -5:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Còn thiếu {abs(diff):.1f}{unit} | {pct:.0f}%)"
        else:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Chuẩn đạt mục tiêu | 100%) ✅"

    return (
        f"📊 TIẾN ĐỘ HÔM NAY (ĐÃ NẠP / MỤC TIÊU):\n"
        f"• Năng lượng: {format_stat(cal_logged, cal_target, cal_diff, ' kcal')}\n"
        f"• Protein:    {format_stat(p_logged, p_target, p_diff)}\n"
        f"• Carb:       {format_stat(c_logged, c_target, c_diff)}\n"
        f"• Fat:        {format_stat(f_logged, f_target, f_diff)}"
    )


def calculate_live_progress(date_str: Optional[str] = None, db_path: Optional[Path] = None) -> str:
    """Calculate total calories and macros logged today and dynamic comparison vs daily target."""
    from datetime import datetime
    from src.db.nutrition_repository import get_remaining_nutrition_quota

    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    quota = get_remaining_nutrition_quota(user_date=target_date, db_path=db_path)

    logged = {
        "cal": quota["logged"]["total_cal"],
        "p": quota["logged"]["total_protein"],
        "c": quota["logged"]["total_carbs"],
        "f": quota["logged"]["total_fat"],
    }
    target = {
        "cal": quota["target"]["target_calories"],
        "p": quota["target"]["protein_g"],
        "c": quota["target"]["carb_g"],
        "f": quota["target"]["fat_g"],
    }

    return format_daily_progress(logged, target)
