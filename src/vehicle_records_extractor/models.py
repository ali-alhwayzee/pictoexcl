"""Data model constants used across the application."""

FINAL_FIELDS = [
    "source_code", "driver_name", "birth_date", "birth_place", "province",
    "district_alley_house", "address_landmark", "ration_card_no", "national_id",
    "identity_issuer", "registry_page", "mother_name", "wife_name", "vehicle_no",
    "ownership", "vehicle_type", "vehicle_color", "vehicle_model", "annual_owner_name",
    "chassis_no", "annual_no", "annual_expiry_date", "phone", "residence_address",
    "residence_card_no", "residence_card_issuer", "match_source", "review_status", "notes",
]

FIELD_LABELS_AR = {
    "source_code": "رمز المصدر",
    "driver_name": "اسم السائق",
    "birth_date": "تاريخ الولادة",
    "birth_place": "مكان الولادة",
    "province": "المحافظة",
    "district_alley_house": "المحلة / الزقاق / الدار",
    "address_landmark": "أقرب نقطة دالة",
    "ration_card_no": "رقم البطاقة التموينية",
    "national_id": "الرقم الوطني",
    "identity_issuer": "جهة إصدار الهوية",
    "registry_page": "السجل / الصحيفة",
    "mother_name": "اسم الأم",
    "wife_name": "اسم الزوجة",
    "vehicle_no": "رقم المركبة",
    "ownership": "محافظة الملكية / العودة",
    "vehicle_type": "نوع المركبة",
    "vehicle_color": "لون المركبة",
    "vehicle_model": "موديل المركبة",
    "annual_owner_name": "اسم مالك السنوية",
    "chassis_no": "رقم الشاصي",
    "annual_no": "رقم السنوية",
    "annual_expiry_date": "تاريخ انتهاء السنوية",
    "phone": "الهاتف",
    "residence_address": "عنوان السكن",
    "residence_card_no": "رقم بطاقة السكن",
    "residence_card_issuer": "جهة إصدار بطاقة السكن",
    "match_source": "مصدر المطابقة",
    "review_status": "حالة المراجعة",
    "notes": "ملاحظات",
}

REQUIRED_FIELDS = ["source_code", "driver_name", "mother_name", "vehicle_no", "review_status"]
REVIEW_STATUSES = ["draft", "approved", "needs_review", "bad_image", "duplicate"]
SOURCE_STATUSES = ["imported", "draft", "approved", "needs_review", "bad_image", "duplicate"]
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".pdf"}
