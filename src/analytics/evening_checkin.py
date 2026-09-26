import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from src.db.connection import get_db_connection, init_db
from src.analytics.prompt_engine import get_vietnamese_date_str

def generate_evening_checkin(
    target_date: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Generate daily step & mechanical load check-in report for 21:00 bedtime preparation."""
    init_db(db_path)
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    date_vn = get_vietnamese_date_str(date_str)

    total_steps = 0
    step_goal = 10000
    activities_summary_raw = None
    training_status = None

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT total_steps, step_goal, activities_summary, training_status
            FROM daily_metrics
            WHERE date = ?
            """,
            (date_str,)
        )
        row = cursor.fetchone()
        if row:
            total_steps = row[0] or 0
            step_goal = row[1] or 10000
            activities_summary_raw = row[2]
            training_status = row[3]

    # Calculate run steps & NEAT walking steps
    run_steps_total = 0
    run_distance_km = 0.0
    has_running_activity = False

    if activities_summary_raw:
        try:
            activities = json.loads(activities_summary_raw)
            if isinstance(activities, list):
                for act in activities:
                    if not isinstance(act, dict):
                        continue
                    act_type = str(act.get("type") or act.get("name") or "").lower()
                    if any(r_kw in act_type for r_kw in ["run", "running", "chạy"]):
                        has_running_activity = True
                        dur_sec = float(act.get("duration_seconds") or 0.0)
                        dist_m = float(act.get("distance_meters") or 0.0)
                        cadence = float(act.get("avg_cadence") or 0.0)

                        if cadence > 0 and dur_sec > 0:
                            act_steps = int(round((cadence * dur_sec) / 60.0))
                        elif dist_m > 0:
                            act_steps = int(round(dist_m / 0.95))
                        else:
                            act_steps = 0

                        run_steps_total += act_steps
                        run_distance_km += dist_m / 1000.0
        except Exception:
            pass

    neat_steps = max(0, total_steps - run_steps_total)
    is_rest_day = not has_running_activity or (training_status and "RECOVERY" in str(training_status).upper())

    # Step Goal completion percentage
    step_pct = round((total_steps / step_goal) * 100) if step_goal > 0 else 100

    # Mechanical Load Assessment
    if is_rest_day and neat_steps > 10000:
        load_assessment = (
            f"⚠️ **Cảnh báo Tải trọng Cơ học:** Hôm nay là ngày Rest Day nhưng vận động thụ động (NEAT) còn cao "
            f"({neat_steps:,} bước). Thân dưới chưa được nghỉ ngơi tuyệt đối, có thể làm chậm quá trình siêu bù đắp "
            f"(supercompensation) của gân Achilles & khớp cổ chân."
        )
    elif total_steps >= step_goal:
        load_assessment = (
            f"✅ **Đánh giá Tải trọng:** Đã hoàn thành mục tiêu bước chân ngày ({total_steps:,} / {step_goal:,} bước, {step_pct}%). "
            f"Tải trọng cơ học vừa phải, tối ưu cho quá trình phục hồi mô cơ."
        )
    else:
        load_assessment = (
            f"ℹ️ **Đánh giá Tải trọng:** Ghi nhận {total_steps:,} / {step_goal:,} bước ({step_pct}%). "
            f"Tải trọng cơ học ở mức thấp, sẵn sàng cho quá trình sạc Body Battery đêm nay."
        )

    # Check Nutrition logs for today
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date
        nut_logs = get_nutrition_logs_by_date(date_str, db_path=db_path)
    except Exception:
        nut_logs = []

    tot_cal_logged = sum(int(log.get("total_calories") or 0) for log in nut_logs)
    has_nutrition = len(nut_logs) > 0 and tot_cal_logged >= 100

    # Build concise single-card Markdown text
    lines = [
        f"🌙 **CHECK-IN PHỤC HỒI & TỔNG KẾT BƯỚC CHÂN CUỐI NGÀY**",
        f"📅 *{date_vn}*",
        "",
        f"👟 **Phân bóc Tải trọng Bước chân:**",
        f"• Tổng bước chân: **{total_steps:,}** / {step_goal:,} bước ({step_pct}%)",
        f"• Bước chạy bài tập: **{run_steps_total:,}** bước ({run_distance_km:.2f} km)",
        f"• Bước đi bộ sinh hoạt (NEAT): **{neat_steps:,}** bước",
        "",
        load_assessment
    ]

    if not has_nutrition:
        lines.extend([
            "",
            f"🍱 **Nhắc nhở Dinh dưỡng Cuối ngày (Chưa log):**",
            f"⚠️ Hôm nay bạn chưa ghi nhận bữa ăn nào trên hệ thống! Để tránh khuyết dữ liệu phục hồi, vui lòng:",
            f"• Gửi ảnh bữa ăn hoặc gõ `/log_standard` để nạp nhanh ước lượng chuẩn Rest Day (~2,150 kcal / 122g P).",
            f"• Hoặc gõ `/quick_log [mô tả]` (VD: `/quick_log 1 phở bò bắp bữa sáng và 1 cơm tấm bữa trưa`)."
        ])

    lines.extend([
        "",
        f"💤 **Khuyến nghị Phục hồi Trước giờ ngủ (21:30):**",
        f"• 💊 **Magie Bisglycinate (300 - 400mg):** Uống lúc 20:30 để thư giãn hệ thần kinh giao cảm, hỗ trợ thả lỏng cơ bắp.",
        f"• 💧 **Bù nước thông minh:** Ngừng uống nhiều nước sau 20:30 (chỉ nhấp ngụm nhỏ) để tránh gián đoạn giấc ngủ Deep Sleep."
    ])

    card_markdown = "\n".join(lines)

    return {
        "date": date_str,
        "total_steps": total_steps,
        "step_goal": step_goal,
        "run_steps": run_steps_total,
        "neat_steps": neat_steps,
        "run_distance_km": run_distance_km,
        "is_rest_day": is_rest_day,
        "card_markdown": card_markdown
    }
