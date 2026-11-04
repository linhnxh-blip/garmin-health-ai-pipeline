"""
Garmin Health AI Pipeline - Training Prescriber & Clinical Exercise Guardrails
Manages dynamic running volume scaling, sleep quality cross-checks (Deep/REM),
biomechanical risk detection (GCT Balance), and subjective fatigue guardrails.
"""

from typing import Dict, Any, Optional, Tuple, Union


def has_subjective_fatigue(feedback: Optional[Union[str, bool, Dict[str, Any]]]) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether subjective athlete feedback indicates fatigue, sluggishness, or musculoskeletal soreness.
    Returns (has_fatigue: bool, reason: Optional[str]).
    """
    if feedback is None:
        return False, None
    if isinstance(feedback, bool):
        if feedback:
            return True, "Vận động viên phản hồi có cảm giác mệt mỏi/nặng chân chủ quan."
        return False, None

    text = ""
    if isinstance(feedback, dict):
        text = str(feedback.get("feedback") or feedback.get("message") or feedback.get("note") or "")
    else:
        text = str(feedback)

    text_lower = text.lower().strip()
    if not text_lower:
        return False, None

    fatigue_keywords = [
        "mỏi", "nặng chân", "uể oải", "thốn", "căng cơ", "căng cứng", "đau", 
        "sluggish", "fatigue", "fatigued", "sore", "soreness", "tired", "exhausted",
        "nặng bắp chuối", "gợn gân", "nhức"
    ]
    for kw in fatigue_keywords:
        if kw in text_lower:
            return True, f"Ghi nhận phản hồi mệt mỏi/nặng chân chủ quan: '{text.strip()}'."

    return False, None


def has_gct_balance_issue(gct_balance: Optional[Union[str, float]]) -> Tuple[bool, Optional[str]]:
    """
    Evaluates ground contact time (GCT) balance asymmetry for Achilles risk.
    Normal athletic baseline: 50.0% ± 1.0% (<= 51.0% L).
    Returns (has_issue: bool, reason: Optional[str]).
    """
    if gct_balance is None:
        return False, None
    try:
        if isinstance(gct_balance, (int, float)):
            left_val = float(gct_balance)
        else:
            left_val = float(str(gct_balance).split("%")[0].strip())

        if left_val > 51.0:
            return True, f"Lệch pha tiếp đất GCT Balance ({left_val:.1f}% Chân Trái) vượt ngưỡng an toàn (50.0% ± 1.0%), nguy cơ quá tải gân Achilles trái."
    except Exception:
        pass
    return False, None


def evaluate_run_readiness(
    readiness_score: Optional[Union[int, float]],
    recovery_time_hours: Optional[Union[int, float]],
    deep_sleep_pct: Optional[Union[int, float]] = None,
    rem_sleep_pct: Optional[Union[int, float]] = None,
    sleep_duration_seconds: Optional[Union[int, float]] = None,
    hrv_status: Optional[str] = None,
    gct_balance_issue: bool = False,
    subjective_fatigue: Optional[Union[str, bool]] = None,
    days_since_race: Optional[int] = None,
    phase: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Evaluates running readiness before issuing a 'GO_RUN' directive.
    Cross-checks hardware metrics, structural sleep quality (Deep & REM sleep),
    biomechanical symmetry, and subjective fatigue.

    Statuses:
    - 'REST_OR_WALK': Critical safety barrier tripped (acute phase, low readiness, high recovery time, severe sleep debt < 5h).
    - 'OPTIONAL_ACTIVE_RECOVERY': Sleep deficit fatigue (Deep < 10%, REM < 15%), subjective fatigue, or biomechanical issue.
    - 'GO_RUN': Fully primed across hardware, sleep quality, and biomechanics.
    """
    # 1. Post-Race Acute Phase (D+1 to D+7): Absolute Running Prohibition
    if phase == "POST_RACE_ACUTE" or (days_since_race is not None and 1 <= days_since_race <= 7):
        d_str = f"D+{days_since_race}" if days_since_race is not None else "D+1..7"
        return "REST_OR_WALK", f"Giai đoạn Hồi phục Cấp Post-Race Acute ({d_str}): CẤM CHẠY HOÀN TOÀN để vi tổn thương cơ bắp và gân gót tự tái tạo."

    # 2. Acute Sleep Deprivation (< 5 hours = 18000s): Hard Neuromuscular Lockout
    if sleep_duration_seconds is not None:
        try:
            s_sec = float(sleep_duration_seconds)
            if 0 < s_sec < 18000:
                hours = round(s_sec / 3600.0, 1)
                return "REST_OR_WALK", f"Thiếu ngủ cấp tính ({hours}h < 5.0h): Phản xạ thần kinh cơ và cảm thụ bản thể suy giảm nghiêm trọng. CẤM CHẠY TUYỆT ĐỐI."
        except (ValueError, TypeError):
            pass

    # 3. Base Hardware Criteria (Readiness & Recovery Time)
    if readiness_score is not None:
        try:
            if float(readiness_score) < 65:
                return "REST_OR_WALK", f"Điểm Sẵn sàng Tập luyện (Readiness {readiness_score}/100) chưa đạt ngưỡng an toàn (>= 65)."
        except (ValueError, TypeError):
            pass

    if recovery_time_hours is not None:
        try:
            if float(recovery_time_hours) > 6:
                return "REST_OR_WALK", f"Thời gian hồi phục mô liên kết (Recovery Time {recovery_time_hours}h) chưa cạn về mốc an toàn (<= 6h)."
        except (ValueError, TypeError):
            pass

    if hrv_status is not None:
        st_clean = str(hrv_status).strip().upper()
        if st_clean not in ("BALANCED", "BALANCED_HIGH"):
            return "REST_OR_WALK", f"Trạng thái HRV ({hrv_status}) chưa đạt mức Cân bằng (BALANCED)."

    # 4. Neuromuscular Recovery Check (Deep Sleep < 10% means incomplete physical/protein synthesis)
    if deep_sleep_pct is not None:
        try:
            d_pct = float(deep_sleep_pct)
            if d_pct < 10.0:
                return "OPTIONAL_ACTIVE_RECOVERY", f"Deep Sleep đêm qua thấp ({d_pct:.1f}% < 10%), cơ bắp và thần kinh chưa phục hồi sâu. ƯU TIÊN: Đi bộ thả lỏng hoặc bơi nhẹ 500m thay vì chạy."
        except (ValueError, TypeError):
            pass

    # 5. Cognitive / Central Nervous System Check (REM Sleep < 15% means incomplete CNS recovery)
    if rem_sleep_pct is not None:
        try:
            r_pct = float(rem_sleep_pct)
            if r_pct < 15.0:
                return "OPTIONAL_ACTIVE_RECOVERY", f"REM Sleep đêm qua thấp ({r_pct:.1f}% < 15%), phục hồi thần kinh nhận thức chưa hoàn tất. ƯU TIÊN: Đi bộ thả lỏng hoặc bơi nhẹ 500m thay vì chạy."
        except (ValueError, TypeError):
            pass

    # 6. Subjective Fatigue Guardrail
    has_fatigue, fatigue_msg = has_subjective_fatigue(subjective_fatigue)
    if has_fatigue:
        return "OPTIONAL_ACTIVE_RECOVERY", f"{fatigue_msg} ƯU TIÊN: Đi bộ thả lỏng hoặc bơi nhẹ 500m thay vì chạy."

    # 7. Biomechanical / GCT Asymmetry Check
    if gct_balance_issue:
        return "OPTIONAL_ACTIVE_RECOVERY", "Lệch pha tiếp đất GCT Balance (>51% L) cảnh báo áp lực quá tải lên gân Achilles trái. ƯU TIÊN: Bơi lội triệt tiêu trọng lực hoặc đi bộ nhẹ."

    # 8. All Systems Green -> GO_RUN
    return "GO_RUN", None


def get_post_race_run_volume(days_since_race: Optional[int]) -> Dict[str, Any]:
    """
    Dynamic Running Volume Logic (Progressive 4-week ladder post-marathon):
    - Week 1 (D+1 to D+7): 0 km (Acute recovery, walking/swimming only)
    - Week 2 (D+8 to D+14): 2.0 - 3.0 km (Shakeout run thích ứng, Zone 1/Low Zone 2 <= 135 bpm)
    - Week 3 (D+15 to D+21): 3.5 - 5.0 km (Zone 2 thích ứng tăng tiến, HR <= 135-138 bpm)
    - Week 4+ (D+22+): 5.0 - 7.0 km (MAF Zone 2 hiếu khí nền tảng, HR <= 136 bpm)
    """
    if days_since_race is None:
        return {
            "week": 4,
            "min_km": 5.0,
            "max_km": 7.0,
            "distance_str": "5.0 - 7.0 km",
            "duration_str": "35 - 50 phút",
            "hr_cap_bpm": 136,
            "zone_str": "MAF Zone 2",
            "is_shakeout": False,
            "title": "Chạy hiếu khí nền tảng MAF Zone 2",
            "description": "Chạy hiếu khí nền tảng MAF Zone 2 (HR <= 136 bpm), duy trì guồng chân tối ưu Cadence 178-182 spm, tiếp đất êm."
        }

    if 1 <= days_since_race <= 7:
        return {
            "week": 1,
            "min_km": 0.0,
            "max_km": 0.0,
            "distance_str": "0 km",
            "duration_str": "15 - 20 phút (Đi bộ / Bơi)",
            "hr_cap_bpm": 125,
            "zone_str": "Active Recovery",
            "is_shakeout": False,
            "title": "Phục hồi cấp Post-Race Acute (CẤM CHẠY)",
            "description": "Đi bộ nhẹ nhàng 15-20 phút hoặc bơi sải thả lỏng Zone 1 triệt tiêu 90% trọng lực. CẤM CHẠY HOÀN TOÀN."
        }
    elif 8 <= days_since_race <= 14:
        return {
            "week": 2,
            "min_km": 2.0,
            "max_km": 3.0,
            "distance_str": "2.0 - 3.0 km",
            "duration_str": "15 - 20 phút",
            "hr_cap_bpm": 135,
            "zone_str": "Zone 1 / Low Zone 2",
            "is_shakeout": True,
            "title": "Shakeout Run nhẹ nhàng thích ứng",
            "description": "Cho phép chạy thử thích ứng 2.0 km - 3.0 km (tối đa 15 - 20 phút). RÀNG BUỘC CỨNG: Khống chế nhịp tim chặt chẽ ở Zone 1 / Low Zone 2 (<= 135 bpm). Chạy guồng chân ngắn, tiếp đất êm, không sải dài. NGUYÊN TẮC: Nếu chân trái hoặc bắp chuối có bất kỳ cảm giác gợn/thốn nào -> DỪNG NGAY LẬP TỨC và chuyển sang đi bộ. PROHIBIT (NGHIÊM CẤM): CẤM tuyệt đối Strides, Tempo, Interval, bứt tốc, biến tốc."
        }
    elif 15 <= days_since_race <= 21:
        return {
            "week": 3,
            "min_km": 3.5,
            "max_km": 5.0,
            "distance_str": "3.5 - 5.0 km",
            "duration_str": "25 - 35 phút",
            "hr_cap_bpm": 138,
            "zone_str": "Zone 2",
            "is_shakeout": False,
            "title": "Chạy phục hồi thích ứng tăng tiến (Progressive Recovery Run)",
            "description": "Chạy phục hồi thích ứng tăng tiến 3.5 - 5.0 km (25-35 phút), Zone 2 (HR <= 135-138 bpm), sải ngắn tự nhiên, tiếp đất êm sát mặt đất."
        }
    else:  # >= 22
        return {
            "week": 4,
            "min_km": 5.0,
            "max_km": 7.0,
            "distance_str": "5.0 - 7.0 km",
            "duration_str": "35 - 50 phút",
            "hr_cap_bpm": 136,
            "zone_str": "MAF Zone 2",
            "is_shakeout": False,
            "title": "Chạy hiếu khí nền tảng MAF Zone 2",
            "description": "Chạy hiếu khí nền tảng MAF Zone 2 (HR <= 136 bpm), 5.0 - 7.0 km, duy trì guồng chân tối ưu Cadence 178-182 spm, tiếp đất êm."
        }


def prescribe_running_workout(
    readiness_score: Optional[Union[int, float]],
    recovery_time_hours: Optional[Union[int, float]],
    deep_sleep_pct: Optional[Union[int, float]] = None,
    rem_sleep_pct: Optional[Union[int, float]] = None,
    sleep_duration_seconds: Optional[Union[int, float]] = None,
    hrv_status: Optional[str] = None,
    gct_balance: Optional[Union[str, float]] = None,
    subjective_fatigue: Optional[Union[str, bool]] = None,
    days_since_race: Optional[int] = None,
    days_to_race: Optional[int] = None,
    phase: Optional[str] = None
) -> Dict[str, Any]:
    """
    Comprehensive training prescription generator.
    Produces deterministic recommendations for morning briefing, executive briefs,
    and Telegram message cards.
    """
    gct_issue, gct_reason = has_gct_balance_issue(gct_balance)
    status, reason = evaluate_run_readiness(
        readiness_score=readiness_score,
        recovery_time_hours=recovery_time_hours,
        deep_sleep_pct=deep_sleep_pct,
        rem_sleep_pct=rem_sleep_pct,
        sleep_duration_seconds=sleep_duration_seconds,
        hrv_status=hrv_status,
        gct_balance_issue=gct_issue,
        subjective_fatigue=subjective_fatigue,
        days_since_race=days_since_race,
        phase=phase
    )

    volume = get_post_race_run_volume(days_since_race)
    achilles_directive = "Bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (đứng 2 chân nhón nhẹ 2-3cm giữ 30s x 3 set) để kích thích dòn sợi collagen gân Achilles trái."

    if status == "REST_OR_WALK":
        choice_1_title = "Nghỉ ngơi hoàn toàn hoặc Đi bộ nhẹ nhàng (CẤM CHẠY BỘ)"
        choice_1_desc = f"Nghỉ ngơi hoàn toàn (Full Rest Day) hoặc chỉ đi bộ thả lỏng 15-20 phút. {reason or ''} PROHIBIT: CẤM CHẠY BỘ dưới mọi hình thức, cấm Strides, Tempo, Interval."
        choice_2_title = "Phục hồi không trọng lực"
        choice_2_desc = "Bơi sải nhẹ nhàng 500m Zone 1 (triệt tiêu 90% trọng lực lên gân gót) hoặc gác chân cao 10-15 phút."
        brief_line = f"• Trạng thái Phục hồi Post-Race (Reverse Taper D+{days_since_race or 8}): Nghỉ hoàn toàn hoặc chỉ đi bộ 15 phút ({reason or 'Chưa đủ điều kiện chạy'}). Kèm Isometric Holds gân gót."
        card_plan = f"Nghỉ ngơi hoàn toàn hoặc chỉ đi bộ nhẹ 15 phút (Chưa đủ điều kiện chạy). Kèm bài tập tĩnh Isometric Holds nhón gót 30s x 3 set bảo vệ gân Achilles."

    elif status == "OPTIONAL_ACTIVE_RECOVERY":
        choice_1_title = "ƯU TIÊN VẬN ĐỘNG PHỤC HỒI (Active Recovery: Đi bộ nhẹ / Bơi lội)"
        choice_1_desc = (
            f"{reason} "
            f"ƯU TIÊN HÀNG ĐẦU: Đi bộ thả lỏng nhẹ nhàng 15-20 phút HOẶC Bơi sải nhẹ 500m Zone 1 (triệt tiêu 90% trọng lực lên gân cơ). "
            f"Nếu cơ thể vẫn muốn vận động chạy thử thích ứng: Chỉ cho phép chạy nhẹ thích ứng ngắn ({volume['distance_str']}, {volume['duration_str']}, {volume['zone_str']}, HR <= {volume['hr_cap_bpm']} bpm), "
            f"tiếp đất êm, sải ngắn. NGUYÊN TẮC: Dừng lại ngay lập tức nếu bắp chuối hoặc gân gót có cảm giác thốn/gợn hoặc nặng chân."
        )
        choice_2_title = "Nghỉ ngơi hoàn toàn (Complete Rest Day)"
        choice_2_desc = "Nghỉ ngơi trọn vẹn để cơ thể và gân gót hoàn tất bù đắp thiếu hụt giấc ngủ và tái tạo collagen."
        brief_line = f"• Trạng thái Phục hồi Post-Race (D+{days_since_race or 8} - Ưu tiên Active Recovery): {reason} Ưu tiên đi bộ 15-20p hoặc bơi 500m thay vì chạy. Kèm Isometric Holds gân gót."
        card_plan = f"Active Recovery (Ưu tiên đi bộ 15-20p hoặc bơi 500m): {reason} Tạm hoãn chạy để tái tạo collagen. Kèm Isometric Holds nhón gót 30s x 3 set."

    else:  # GO_RUN
        choice_1_title = f"{volume['title']} ({volume['distance_str']})"
        choice_1_desc = (
            f"Khối lượng chỉ định: {volume['distance_str']} ({volume['duration_str']}). "
            f"Khống chế nhịp tim chặt chẽ ở {volume['zone_str']} (HR <= {volume['hr_cap_bpm']} bpm). "
            f"{volume['description']} "
            f"NGUYÊN TẮC NGẮT TẢI: Nếu bắp chuối trái hoặc gân gót có bất kỳ cảm giác gợn/thốn nào -> DỪNG NGAY LẬP TỨC và chuyển sang đi bộ. "
            f"PROHIBIT: CẤM tuyệt đối Strides bứt tốc, Tempo, Interval, bứt tốc hay biến tốc."
        )
        choice_2_title = "Phục hồi không trọng lực hoặc Nghỉ ngơi"
        choice_2_desc = "Bơi sải nhẹ nhàng 500m - 700m Zone 1 HOẶC Nghỉ hoàn toàn nếu cảm thấy cơ thể còn mỏi. Kết hợp foam roller nhẹ nhàng bắp chân."
        
        if volume.get("is_shakeout"):
            brief_line = f"• Trạng thái Phục hồi Post-Race (Reverse Taper D+{days_since_race or 8}): Đủ điều kiện Shakeout Run 2.0-3.0km ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm, sải ngắn) HOẶC Bơi sải 500-700m Zone 1 / Nghỉ ngơi. Kèm Isometric Holds gân gót."
            card_plan = f"Shakeout Run thích ứng 2.0-3.0 km ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm, tiếp đất êm) HOẶC Bơi sải 500-700m Zone 1 / Nghỉ hoàn toàn. Kèm Isometric Holds nhón gót 30s x 3 set."
        elif volume.get("week") == 3:
            brief_line = f"• Trạng thái Phục hồi Post-Race (Tuần 3 D+{days_since_race or 15}): Đủ điều kiện Chạy phục hồi thích ứng 3.5-5.0km ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm, sải ngắn) HOẶC Bơi sải 500-700m. Kèm Isometric Holds gân gót."
            card_plan = f"Chạy phục hồi thích ứng tăng tiến 3.5-5.0 km ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm, tiếp đất êm) HOẶC Bơi sải 500-700m Zone 1. Kèm Isometric Holds 30s x 3 set."
        else:
            brief_line = f"• Trạng thái Phục hồi Post-Race (Tuần 4+ D+{days_since_race or 22}): Đủ điều kiện {volume['title']} {volume['distance_str']} ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm) HOẶC Bơi sải 800-1000m. Kèm Isometric Holds gân gót."
            card_plan = f"{volume['title']} {volume['distance_str']} ({volume['duration_str']}, {volume['zone_str']} <= {volume['hr_cap_bpm']} bpm, Cadence 178-182 spm) HOẶC Bơi sải 800-1000m. Kèm Isometric Holds 30s x 3 set."

    return {
        "status": status,
        "reason": reason,
        "volume": volume,
        "option_1": {
            "title": choice_1_title,
            "description": choice_1_desc
        },
        "option_2": {
            "title": choice_2_title,
            "description": choice_2_desc
        },
        "achilles_directive": achilles_directive,
        "brief_line": brief_line,
        "card_plan": card_plan,
        "gct_issue": gct_issue,
        "gct_reason": gct_reason
    }


def calculate_sleep_stage_percentages(
    deep_sleep_seconds: Optional[Union[int, float]],
    rem_sleep_seconds: Optional[Union[int, float]],
    light_sleep_seconds: Optional[Union[int, float]],
    awake_duration_seconds: Optional[Union[int, float]] = None
) -> Dict[str, float]:
    """
    Derives exact percentages of Deep, REM, Light sleep relative to Total Sleep Time (Deep + REM + Light).
    Total percentage sum is mathematically guaranteed to equal 100.0%.
    """
    deep_s = float(deep_sleep_seconds or 0.0)
    rem_s = float(rem_sleep_seconds or 0.0)
    light_s = float(light_sleep_seconds or 0.0)
    awake_s = float(awake_duration_seconds or 0.0)

    deep_m = round(deep_s / 60.0, 1)
    rem_m = round(rem_s / 60.0, 1)
    light_m = round(light_s / 60.0, 1)
    awake_m = round(awake_s / 60.0, 1)

    total_asleep = deep_m + rem_m + light_m
    total_bed = total_asleep + awake_m

    if total_asleep > 0:
        deep_pct = round((deep_m / total_asleep) * 100.0, 1)
        rem_pct = round((rem_m / total_asleep) * 100.0, 1)
        light_pct = round(100.0 - deep_pct - rem_pct, 1)
    else:
        deep_pct = rem_pct = light_pct = 0.0

    awake_pct = round((awake_m / total_bed) * 100.0, 1) if total_bed > 0 else 0.0

    return {
        "deep_pct": deep_pct,
        "rem_pct": rem_pct,
        "light_pct": light_pct,
        "awake_pct": awake_pct,
        "deep_min": deep_m,
        "rem_min": rem_m,
        "light_min": light_m,
        "awake_min": awake_m,
        "total_asleep_min": total_asleep,
        "total_bed_min": total_bed
    }
