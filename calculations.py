"""Body-composition calculations used by the Streamlit app.

The functions here intentionally use published, transparent equations instead
of trying to reproduce a scale manufacturer's proprietary "body age" score.
"""

from __future__ import annotations


def validate_measurement(
    height_cm: float,
    weight_kg: float,
    body_fat_pct: float,
    visceral_fat_pct: float,
    bone_mass_kg: float,
) -> list[str]:
    errors: list[str] = []
    if not 100 <= height_cm <= 230:
        errors.append("身長は100〜230 cmで入力してください。")
    if not 25 <= weight_kg <= 300:
        errors.append("体重は25〜300 kgで入力してください。")
    if not 2 <= body_fat_pct <= 70:
        errors.append("体脂肪率は2〜70%で入力してください。")
    if not 0 <= visceral_fat_pct <= 60:
        errors.append("内臓脂肪は0〜60の範囲で入力してください。")
    if not 0.5 <= bone_mass_kg <= 10:
        errors.append("骨量は0.5〜10 kgで入力してください。")
    if bone_mass_kg >= weight_kg * (1 - body_fat_pct / 100):
        errors.append("骨量は除脂肪量より小さい値にしてください。")
    return errors


def lean_body_mass(weight_kg: float, body_fat_pct: float) -> float:
    return weight_kg * (1 - body_fat_pct / 100)


def katch_mcardle_bmr(weight_kg: float, body_fat_pct: float) -> float:
    """Estimate resting energy expenditure in kcal/day."""
    return 370 + 21.6 * lean_body_mass(weight_kg, body_fat_pct)


def mifflin_st_jeor_bmr(
    age: float, height_cm: float, weight_kg: float, sex: str
) -> float:
    """Return the age-specific Mifflin-St Jeor reference BMR."""
    sex_constant = 5 if sex == "男性" else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + sex_constant


def metabolic_age(
    height_cm: float, weight_kg: float, body_fat_pct: float, sex: str
) -> tuple[float, bool]:
    """Invert Mifflin-St Jeor so its BMR equals Katch-McArdle BMR.

    Returns the value clamped to the adult comparison range (18–90), plus a
    flag indicating whether clamping occurred.
    """
    bmr = katch_mcardle_bmr(weight_kg, body_fat_pct)
    sex_constant = 5 if sex == "男性" else -161
    raw_age = (10 * weight_kg + 6.25 * height_cm + sex_constant - bmr) / 5
    age = min(90.0, max(18.0, raw_age))
    return age, age != raw_age


def bmi(height_cm: float, weight_kg: float) -> float:
    return weight_kg / (height_cm / 100) ** 2
