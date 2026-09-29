"""
Centralized Sports Medicine & Biochemical Constants for Garmin Health AI Pipeline.
Defines core markers, supplementary markers, and clinical action guidelines (ADA, AHA, EULAR, ACSM).
"""

from typing import List, Dict

# Core 14 Blood Markers critical for endurance athlete physiology & sports medicine tracking
CORE_SPORT_MARKERS: List[str] = [
    "HGB", "HCT", "RBC",
    "GLUCOSE", "HBA1C", "TRIGLYCERIDE",
    "CHOLESTEROL", "LDL_C", "HDL_C",
    "URIC_ACID", "CREATININE", "ALT", "AST",
    "WBC"
]

# Supplementary markers tracked when present in lab reports
SUPPLEMENTARY_MARKERS: List[str] = ["IRON", "FERRITIN"]

# Action guidelines mapped to clinical standards (ADA, AHA, EULAR, ACSM, EASL)
SPORTS_MEDICINE_RECOMMENDATIONS: Dict[str, str] = {
    "GLUCOSE": "Cắt bỏ hoàn toàn đường lỏng HFCS/nước ngọt và bánh kẹo công nghiệp. Nạp carb phức hợp (gạo lứt, yến mạch, khoai lang), tăng cường bài tập Zone 2 để kích hoạt cơ chế FatMax đốt mỡ.",
    "HBA1C": "Duy trì kiểm soát carb nghiêm ngặt, cắt bỏ HFCS & đường đơn; tăng cường bài tập MAF Zone 2 đều đặn để cải thiện độ nhạy Insulin dài hạn.",
    "TRIGLYCERIDE": "Cắt bỏ hoàn toàn đường lỏng HFCS/nước ngọt và bánh kẹo công nghiệp. Nạp carb phức hợp (gạo lứt, yến mạch, khoai lang), tăng cường bài tập Zone 2 để kích hoạt cơ chế FatMax đốt mỡ.",
    "URIC_ACID": "Uric acid sát trần bão hòa dịch khớp (> 420 µmol/L). Ép uống tối thiểu 2.8 - 3.2L nước khoáng kiềm/ngày, hạn chế ăn dồn dập hải sản/phủ tạng để tránh áp lực thận và co rút cơ bắp.",
    "WBC": "Bạch cầu nền thấp (< 3.5 G/L). Cần ưu tiên giấc ngủ sâu (> 7.5 tiếng) và dinh dưỡng phục hồi, tránh tập dồn volume cao liên tiếp nhiều ngày.",
    "HGB": "Huyết sắc tố HGB giảm sút. Bổ sung thực phẩm giàu Sắt heme (thịt bò thăn, gan, hải sản) kết hợp Vitamin C; rà soát tải chạy bộ để tránh vỡ hồng cầu do va đập bàn chân (Footstrike Hemolysis).",
    "HCT": "HCT sụt giảm dưới 40%. Bổ sung vi chất tạo máu (Sắt, Folate, B12) và duy trì hidrat hóa hợp lý.",
    "ALT": "Men gan ALT vượt 40 U/L do vi tổn thương cơ bắp sau bài tập nặng hoặc mệt mỏi gan. Giảm tải sức mạnh, ưu tiên bơi lội thả lỏng không trọng lực và bổ sung Silymarin/Milk Thistle.",
    "AST": "Men gan AST vượt 40 U/L do vi tổn thương cơ bắp sau bài tập nặng hoặc mệt mỏi gan. Giảm tải sức mạnh, ưu tiên bơi lội thả lỏng không trọng lực và bổ sung Silymarin/Milk Thistle.",
    "CHOLESTEROL": "Cholesterol toàn phần tăng. Tăng chất xơ hòa tan (yến mạch, rau xanh) và tập Zone 2 để cải thiện chỉ số mỡ máu.",
    "LDL_C": "LDL-Cholesterol vượt ngưỡng tối ưu (< 2.6 mmol/L). Cắt giảm chất béo bão hòa/trans-fat, bổ sung 2000mg/ngày Omega-3 và duy trì tập endurance Zone 2.",
    "HDL_C": "HDL-Cholesterol thấp (< 1.0 mmol/L). Tăng cường tập luyện hiếu khí MAF Zone 2 và nạp chất béo tốt (dầu olive, quả bơ, hạt óc chó).",
    "CREATININE": "Creatinine tăng cao phản ánh quá tải cơ bắp hoặc áp lực lọc thận. Ép bù đủ 3.0L nước/ngày và giảm khối lượng tập tạ nặng.",
    "RBC": "Số lượng hồng cầu giảm sút. Bổ sung vi chất tạo máu (Sắt, B12, Folate)."
}
