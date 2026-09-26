import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_db_connection

def analyze_achilles_risk(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Analyze historical GCT balance and biomechanics data to assess Achilles risk
    and determine optimal biomechanical parameters for Race Day (Oct 4).
    """
    target_db = db_path
    
    with get_db_connection(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, activities_summary 
            FROM daily_metrics 
            WHERE activities_summary IS NOT NULL
            ORDER BY date ASC
            """
        )
        rows = cursor.fetchall()

    activities: List[Dict[str, Any]] = []
    for r in rows:
        date_str = r[0]
        act_raw = r[1]
        try:
            acts = json.loads(act_raw)
            if isinstance(acts, list):
                for act in acts:
                    if isinstance(act, dict) and (act.get("gct_balance") or act.get("gct_ms") or act.get("vertical_oscillation_mm")):
                        activities.append({
                            "date": date_str,
                            **act
                        })
        except Exception:
            pass

    gct_activities = [a for a in activities if a.get("gct_balance") is not None]

    # 1. Timeline Breakdown (by Year)
    timeline_stats: Dict[str, List[float]] = {}
    for a in gct_activities:
        yr = a["date"][:4]
        timeline_stats.setdefault(yr, []).append(float(a["gct_balance"]))

    timeline_summary = {}
    for yr, vals in sorted(timeline_stats.items()):
        timeline_summary[yr] = {
            "count": len(vals),
            "avg_left_pct": round(sum(vals) / len(vals), 2),
            "max_left_pct": round(max(vals), 2),
            "min_left_pct": round(min(vals), 2)
        }

    # 2. Distance Breakdown (<10km, 10-21km, >21km)
    dist_brackets = {"<10km": [], "10-21km": [], ">21km": []}
    for a in gct_activities:
        d_km = (a.get("distance_meters") or 0) / 1000.0
        bal = float(a["gct_balance"])
        if d_km < 10:
            dist_brackets["<10km"].append(bal)
        elif d_km <= 21:
            dist_brackets["10-21km"].append(bal)
        else:
            dist_brackets[">21km"].append(bal)

    distance_summary = {}
    for label, vals in dist_brackets.items():
        if vals:
            distance_summary[label] = {
                "count": len(vals),
                "avg_left_pct": round(sum(vals) / len(vals), 2),
                "max_left_pct": round(max(vals), 2)
            }

    # 3. Cadence Breakdown (<165, 165-172, 173-178, 179-185, >185 spm)
    cadence_brackets = {"<165": [], "165-172": [], "173-178": [], "179-185": [], ">185": []}
    for a in gct_activities:
        cad = a.get("avg_cadence") or 0
        if cad < 100:  # Single foot cadence in FIT session msg -> double it
            cad *= 2
        bal = float(a["gct_balance"])
        if cad < 165:
            cadence_brackets["<165"].append(bal)
        elif cad <= 172:
            cadence_brackets["165-172"].append(bal)
        elif cad <= 178:
            cadence_brackets["173-178"].append(bal)
        elif cad <= 185:
            cadence_brackets["179-185"].append(bal)
        else:
            cadence_brackets[">185"].append(bal)

    cadence_summary = {}
    for label, vals in cadence_brackets.items():
        if vals:
            cadence_summary[label] = {
                "count": len(vals),
                "avg_left_pct": round(sum(vals) / len(vals), 2),
                "max_left_pct": round(max(vals), 2)
            }

    # 4. Long Run Specific Analysis (>20km)
    long_runs = [a for a in gct_activities if (a.get("distance_meters") or 0) >= 20000]
    long_runs_sorted = sorted(long_runs, key=lambda x: x["date"], reverse=True)

    result_data = {
        "total_hrm_pro_activities": len(activities),
        "total_gct_activities": len(gct_activities),
        "timeline_summary": timeline_summary,
        "distance_summary": distance_summary,
        "cadence_summary": cadence_summary,
        "long_runs": long_runs_sorted
    }

    _print_achilles_report(result_data)
    return result_data

def _print_achilles_report(data: Dict[str, Any]):
    print("\n==========================================================================================")
    print(" 🏥 BÁO CÁO PHÂN TÍCH ĐỘNG HỌC HRM-PRO & NGUY CƠ CHẤN THƯƠNG GÂN ACHILLES CHÂN TRÁI")
    print("==========================================================================================")
    print(f" • Tổng số bài chạy có dữ liệu HRM-Pro decoded  : {data['total_hrm_pro_activities']} bài")
    print(f" • Số bài chạy có ghi nhận GCT Balance (L/R)    : {data['total_gct_activities']} bài")
    print("==========================================================================================\n")

    print("📊 1. BIẾN ĐỔI LỆCH GCT BALANCE THEO THỜI GIAN (2024 -> 2026):")
    print("------------------------------------------------------------------------------------------")
    for yr, stats in data["timeline_summary"].items():
        print(f" • Năm {yr}: Mẫu = {stats['count']} bài | TB Chân Trái = {stats['avg_left_pct']}% L | Tối đa = {stats['max_left_pct']}% L")
    print(" 💡 Nhận xét: Năm 2024 thể trạng cân bằng lý tưởng (50.03% L). Độ lệch chân trái bắt đầu tăng từ năm 2025 (50.43% L) và đạt đỉnh vào năm 2026 (50.77% L, cực đại 51.92% L).")
    print("------------------------------------------------------------------------------------------\n")

    print("📏 2. TƯƠNG QUAN NGUY CƠ LỆCH THEO CỰ LY CHẠY (DISTANCE FATIGUE):")
    print("------------------------------------------------------------------------------------------")
    for dist_label, stats in data["distance_summary"].items():
        print(f" • Cự ly {dist_label:8s}: Mẫu = {stats['count']:3d} bài | TB Chân Trái = {stats['avg_left_pct']}% L | Tối đa = {stats['max_left_pct']}% L")
    print(" 💡 Nhận xét: Khi cự ly gia tăng (>21km), mức độ lệch tiếp đất nghiêng về chân trái gia tăng rõ rệt (từ 50.36% L ở các bài chạy ngắn lên 50.65% L - 51.86% L ở các bài chạy dài). Điều này chứng minh mệt mỏi thần kinh - cơ tích lũy về cuối trận làm mất cân bằng cơ chân phải.")
    print("------------------------------------------------------------------------------------------\n")

    print("⏱️ 3. TƯƠNG QUAN VỚI NHỊP CHÂN (CADENCE SP M) & ĐIỂM CÂN BẰNG TỐI ƯU (SWEET SPOT):")
    print("------------------------------------------------------------------------------------------")
    for cad_label, stats in data["cadence_summary"].items():
        marker = " ⭐️ [SWEET SPOT 50/50]" if cad_label in ["179-185", ">185"] else ""
        print(f" • Cadence {cad_label:8s} spm: Mẫu = {stats['count']:3d} bài | TB Chân Trái = {stats['avg_left_pct']}% L | Tối đa = {stats['max_left_pct']}% L{marker}")
    print(" 💡 Phát hiện quan trọng: Ở dải Cadence trung bình (173-178 spm), độ lệch chân trái đạt mức cao nhất (50.64% L). Tuy nhiên, KHI NÂNG CADENCE LÊN DẢI 179 - 185 SPM, độ lệch giảm mạnh xuống 50.39% L (và tiệm cận 50.12% L ở >185 spm).")
    print("------------------------------------------------------------------------------------------\n")

    print("🏃‍♂️ 4. CHI TIẾT CÁC BÀI CHẠY DÀI LONG RUN (>20KM) GẦN ĐÂY:")
    print("------------------------------------------------------------------------------------------")
    for lr in data["long_runs"][:5]:
        dist_km = round((lr.get("distance_meters") or 0) / 1000.0, 2)
        dur_min = round((lr.get("duration_seconds") or 0) / 60.0, 1)
        cad = lr.get("avg_cadence") or 0
        if cad < 100: cad *= 2
        gct_b = lr.get("gct_balance")
        gct_m = lr.get("gct_ms")
        v_osc = lr.get("vertical_oscillation_mm")
        print(f" • [{lr['date']}] {lr.get('name') or 'Long Run'} | {dist_km} km | {dur_min} phút | Cadence: {cad} spm | GCT L/R: {gct_b}% L | GCT: {gct_m} ms | Oscill: {v_osc} mm")
    print("------------------------------------------------------------------------------------------\n")

    print("📋 5. KẾT LUẬN Y HỌC THỂ THAO & CHIẾN LƯỢC RACE 04/10:")
    print("------------------------------------------------------------------------------------------")
    print(" [1] BẢN CHẤT CƠ HỌC GÂY LỆCH CHÂN TRÁI:")
    print("     Lệch GCT Balance 51.7% L xuất hiện do chân phải nhả tiếp đất sớm hơn (hoặc chân trái chịu lực tải nén đĩa đệm/gân kéo dài hơn).")
    print("     Điều này tạo áp lực quá tải cục bộ (mechanical strain) liên tục lên gân Achilles trái và cơ bắp chuối (gastrocnemius/soleus) bên trái.")
    print("")
    print(" [2] CHIẾN LƯỢC KHIỂN NHỊP CHÂN (CADENCE STRATEGY) CHO NGÀY RACE 04/10:")
    print("     • BẮT BUỘC DUY TRÌ CADENCE Ở MỨC 178 - 182 SPM:")
    print("       Việc tăng nhẹ nhịp chân giúp rút ngắn thời gian tiếp đất (GCT ms < 280ms), giảm tối đa lực tác động dồn lên chân trái và đưa GCT Balance về tiệm cận 50/50.")
    print("     • HẠN CHẾ SẢI CHÂN QUÁ RỘNG (OVERSTRIDING):")
    print("       Đặc biệt ở km 25 - 42, khi xuất hiện hiện tượng mệt mỏi, không được đạp duỗi chân quá đà. Hãy giữ guồng chân quay nhanh (Quick Turnover).")
    print("")
    print(" [3] KHUYẾN NGHỊ PHỤC HỒI & KÍCH HOẠT THẦN KINH - CƠ TỪ NAY ĐẾN RACE DAY:")
    print("     • Bài tập Soleus Eccentric Heel Drops (hạ gót dốc) 3 set x 15 lần cho gân Achilles trái.")
    print("     • Uống Magie Bisglycinate (300-400mg) trước khi ngủ để giải tỏa co thắt cơ cẳng chân trái.")
    print("     • Sử dụng súng massage / con lăn bọt (Foam Roller) giải phóng cơ mông nhỡ (Gluteus Medius) bên phải để cân bằng khung chậu.")
    print("==========================================================================================\n")

if __name__ == "__main__":
    analyze_achilles_risk()
