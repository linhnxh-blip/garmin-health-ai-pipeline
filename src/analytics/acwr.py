import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.db.connection import get_db_connection


class ACWRCalculator:
    """
    Sports Medicine Acute:Chronic Workload Ratio (ACWR) Calculator.
    Calculates 7-day Acute Load vs 28-day Chronic Load to assess injury risk and tapering state.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def calculate(
        self,
        target_date: str,
        days: int = 28,
        use_ewma: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate ACWR for target_date.

        Returns:
            {
                'acute_load': float,
                'chronic_load': float,
                'acwr': float,
                'status': str,
                'zone_desc': str,
                'days_evaluated': int
            }
        """
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            target_dt = datetime.now().date()

        start_dt = target_dt - timedelta(days=days - 1)
        start_date_str = start_dt.strftime("%Y-%m-%d")

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT date, training_load_7d, active_calories, activities_summary
                FROM daily_metrics
                WHERE date <= ? AND date >= ?
                ORDER BY date ASC
                """,
                (target_date, start_date_str)
            )
            rows = [dict(r) for r in cursor.fetchall()]

        date_map = {r["date"]: r for r in rows}

        daily_loads: List[float] = []
        for i in range(days):
            d_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            row = date_map.get(d_str)

            if row:
                act_raw = row.get("activities_summary")
                act_load_sum = 0.0
                if act_raw:
                    try:
                        acts = json.loads(act_raw)
                        if isinstance(acts, list):
                            for act in acts:
                                if isinstance(act, dict):
                                    atl = act.get("activity_training_load")
                                    if atl is not None and float(atl) > 0:
                                        act_load_sum += float(atl)
                    except Exception:
                        pass

                if act_load_sum > 0:
                    load_val = act_load_sum
                elif row.get("training_load_7d") is not None and float(row["training_load_7d"]) > 0:
                    load_val = float(row["training_load_7d"]) / 7.0
                elif row.get("active_calories") is not None and float(row["active_calories"]) > 0:
                    load_val = float(row["active_calories"])
                else:
                    load_val = 0.0
            else:
                load_val = 0.0

            daily_loads.append(load_val)

        days_evaluated = len(daily_loads)
        if not daily_loads or sum(daily_loads) == 0.0:
            acute_load = 0.0
            chronic_load = 0.0
            acwr_val = 0.0
        elif use_ewma:
            a_alpha = 2.0 / (7 + 1)
            c_alpha = 2.0 / (28 + 1)

            ewma_a = daily_loads[0]
            ewma_c = daily_loads[0]
            for val in daily_loads[1:]:
                ewma_a = val * a_alpha + ewma_a * (1 - a_alpha)
                ewma_c = val * c_alpha + ewma_c * (1 - c_alpha)
            acute_load = ewma_a
            chronic_load = ewma_c
            acwr_val = acute_load / chronic_load if chronic_load > 0 else 0.0
        else:
            acute_slice = daily_loads[-7:]
            acute_load = sum(acute_slice) / len(acute_slice) if acute_slice else 0.0
            chronic_load = sum(daily_loads) / len(daily_loads) if daily_loads else 0.0
            acwr_val = acute_load / chronic_load if chronic_load > 0 else 0.0

        # Sports Medicine Zone Classification
        if acwr_val < 0.3:
            status = "ACUTE_LOAD_VERY_LOW"
            zone_desc = "Tải cấp tính rất thấp (<0.3). Cần duy trì lực căng thần kinh cơ nhẹ (Chạy Zone 2 + Cadence 178-182 spm) để tránh hiện tượng ì cơ / mỏi giò (stale legs) trước ngày race."
        elif acwr_val < 0.8:
            status = "TAPERING_DEEP_RECOVERY"
            zone_desc = "Rất an toàn, cơ bắp phục hồi cao độ cho Race Day"
        elif 0.8 <= acwr_val <= 1.3:
            status = "SWEET_SPOT_OPTIMAL"
            zone_desc = "Vùng tải tối ưu"
        elif 1.3 < acwr_val <= 1.5:
            status = "ELEVATED_RISK"
            zone_desc = "Cảnh báo nguy cơ quá tải"
        else:
            status = "DANGER_HIGH_INJURY_SPIKE"
            zone_desc = "Báo động đỏ nguy cơ viêm gân/chấn thương cấp"

        return {
            "acute_load": round(acute_load, 2),
            "chronic_load": round(chronic_load, 2),
            "acwr": round(acwr_val, 2),
            "status": status,
            "zone_desc": zone_desc,
            "days_evaluated": days_evaluated
        }


def calculate_acwr(
    target_date: str,
    days: int = 28,
    db_path: Optional[Path] = None,
    use_ewma: bool = False
) -> Dict[str, Any]:
    """Helper function to calculate ACWR."""
    calc = ACWRCalculator(db_path=db_path)
    return calc.calculate(target_date=target_date, days=days, use_ewma=use_ewma)
