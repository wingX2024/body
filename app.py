from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from supabase import Client, create_client
from postgrest.exceptions import APIError

from calculations import (
    bmi,
    katch_mcardle_bmr,
    lean_body_mass,
    metabolic_age,
    mifflin_st_jeor_bmr,
    validate_measurement,
)


TABLE_NAME = "body_measurements"
COLUMNS = [
    "measurement_date", "sex", "height_cm", "weight_kg", "body_fat_pct",
    "visceral_fat_pct", "bone_mass_kg", "bmr_kcal", "metabolic_age",
]


class SupabaseConfigurationError(RuntimeError):
    pass


@st.cache_resource
def supabase_client() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (KeyError, FileNotFoundError) as exc:
        raise SupabaseConfigurationError(
            "SUPABASE_URL または SUPABASE_KEY が設定されていません。"
        ) from exc
    if str(key).startswith("sb_publishable_"):
        raise SupabaseConfigurationError(
            "SUPABASE_KEYにPublishable keyが設定されています。書き込み可能なsb_secret_から始まるSecret keyへ変更してください。"
        )
    return create_client(url, key)


def load_data() -> pd.DataFrame:
    response = (
        supabase_client()
        .table(TABLE_NAME)
        .select(",".join(COLUMNS))
        .order("measurement_date")
        .execute()
    )
    data = pd.DataFrame(response.data, columns=COLUMNS)
    if not data.empty:
        # Older/imported data may use different date notations. Normalize these
        # before displaying so one calendar day is always shown only once.
        data["measurement_date"] = pd.to_datetime(
            data["measurement_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        data = data.dropna(subset=["measurement_date"])
        data = data.drop_duplicates("measurement_date", keep="last")
    return data


def save_row(row: dict) -> bool:
    """Store exactly one record per date and return whether it was replaced."""
    client = supabase_client()
    existing = (
        client.table(TABLE_NAME)
        .select("measurement_date")
        .eq("measurement_date", row["measurement_date"])
        .limit(1)
        .execute()
    )
    existed = bool(existing.data)
    clean_row = {column: row[column] for column in COLUMNS}
    client.table(TABLE_NAME).upsert(
        clean_row, on_conflict="measurement_date"
    ).execute()
    return existed


def metabolism_chart(row: dict) -> dict:
    ages = list(range(18, 91))
    values = [
        {
            "年齢": age,
            "基礎代謝量": mifflin_st_jeor_bmr(
                age, row["height_cm"], row["weight_kg"], row["sex"]
            ),
            "系列": "基準",
        }
        for age in ages
    ]
    values.append(
        {
            "年齢": row["metabolic_age"],
            "基礎代謝量": row["bmr_kcal"],
            "系列": "本人",
        }
    )
    position = {
        "x": {
            "field": "年齢", "type": "quantitative", "title": "年齢（歳）",
            "scale": {"domain": [18, 90]},
        },
        "y": {
            "field": "基礎代謝量", "type": "quantitative",
            "title": "基礎代謝量（kcal/日）", "scale": {"zero": False},
        },
    }
    return {
        "data": {"values": values},
        "height": 380,
        "layer": [
            {
                "transform": [{"filter": "datum.系列 === '基準'"}],
                "mark": {"type": "line", "color": "#4C78A8", "strokeWidth": 3},
                "encoding": {
                    **position,
                    "tooltip": [
                        {"field": "年齢", "type": "quantitative"},
                        {"field": "基礎代謝量", "type": "quantitative", "format": ".0f"},
                    ],
                },
            },
            {
                "transform": [{"filter": "datum.系列 === '本人'"}],
                "mark": {"type": "point", "color": "#E45756", "filled": True, "size": 180},
                "encoding": {
                    **position,
                    "tooltip": [
                        {"field": "年齢", "type": "quantitative", "title": "推定年齢", "format": ".1f"},
                        {"field": "基礎代謝量", "type": "quantitative", "title": "本人の基礎代謝量", "format": ".0f"},
                    ],
                },
            },
        ],
    }


def import_csv(uploaded_file) -> tuple[int, list[str]]:
    incoming = pd.read_csv(uploaded_file)
    missing = [c for c in COLUMNS if c not in incoming.columns]
    if missing:
        return 0, ["CSVに必要な列がありません: " + ", ".join(missing)]
    saved = 0
    errors: list[str] = []
    for index, row in incoming.iterrows():
        try:
            day = pd.to_datetime(row["measurement_date"]).date().isoformat()
            values = {c: row[c] for c in COLUMNS}
            values["measurement_date"] = day
            validation = validate_measurement(
                float(values["height_cm"]), float(values["weight_kg"]),
                float(values["body_fat_pct"]), float(values["visceral_fat_pct"]),
                float(values["bone_mass_kg"]),
            )
            if validation:
                raise ValueError(" ".join(validation))
            save_row(values)
            saved += 1
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f"{index + 2}行目: {exc}")
    return saved, errors


st.set_page_config(page_title="体組成トラッカー", page_icon="⚖️", layout="wide")
st.title("体組成トラッカー")
st.caption("日々の体組成を記録し、基礎代謝量と参考の代謝年齢を確認できます。")
if flash_message := st.session_state.pop("flash_message", None):
    st.success(flash_message)

try:
    supabase_client().table(TABLE_NAME).select("measurement_date").limit(1).execute()
except SupabaseConfigurationError as exc:
    st.error(str(exc))
    st.code(
        'SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\n'
        'SUPABASE_KEY = "YOUR_SERVICE_ROLE_KEY"',
        language="toml",
    )
    st.info("ローカルでは .streamlit/secrets.toml、Streamlit CloudではApp settingsのSecretsに設定してください。")
    st.stop()
except Exception:
    st.error("Supabaseに接続できないか、body_measurementsテーブルがありません。supabase_schema.sqlを実行してください。")
    st.stop()

with st.sidebar:
    st.header("データ管理")
    uploaded = st.file_uploader("バックアップCSVを読み込む", type="csv")
    if uploaded and st.button("CSVを取り込む", use_container_width=True):
        count, import_errors = import_csv(uploaded)
        if count:
            st.success(f"{count}件を取り込みました。")
        for error in import_errors[:5]:
            st.error(error)
        if len(import_errors) > 5:
            st.error(f"ほか{len(import_errors) - 5}件のエラーがあります。")
    current = load_data()
    if not current.empty:
        st.download_button(
            "CSVをダウンロード", current.to_csv(index=False).encode("utf-8-sig"),
            "body_composition.csv", "text/csv", use_container_width=True,
        )
    st.success("データはSupabaseに永続保存されます。CSVは任意のバックアップとして利用できます。")

with st.form("measurement_form"):
    st.subheader("今日の測定値")
    a, b, c = st.columns(3)
    measured_on = a.date_input("測定日", value=date.today())
    sex = b.selectbox("性別（計算式の区分）", ["女性", "男性"])
    height = c.number_input("身長 (cm)", 100.0, 230.0, 165.0, 0.1)
    d, e, f, g = st.columns(4)
    weight = d.number_input("体重 (kg)", 25.0, 300.0, 60.0, 0.1)
    body_fat = e.number_input("体脂肪率 (%)", 2.0, 70.0, 25.0, 0.1)
    visceral_fat = f.number_input("内臓脂肪（% または機器の値）", 0.0, 60.0, 8.0, 0.1)
    bone_mass = g.number_input("骨量 (kg)", 0.5, 10.0, 2.5, 0.1)
    calculated = st.form_submit_button("計算する", type="primary", use_container_width=True)

if calculated:
    errors = validate_measurement(height, weight, body_fat, visceral_fat, bone_mass)
    if errors:
        for error in errors:
            st.error(error)
    else:
        bmr_value = katch_mcardle_bmr(weight, body_fat)
        age_value, clamped = metabolic_age(height, weight, body_fat, sex)
        st.session_state["pending_measurement"] = {
            "measurement_date": measured_on.isoformat(), "sex": sex,
            "height_cm": height, "weight_kg": weight,
            "body_fat_pct": body_fat, "visceral_fat_pct": visceral_fat,
            "bone_mass_kg": bone_mass, "bmr_kcal": round(bmr_value, 1),
            "metabolic_age": round(age_value, 1),
        }
        st.session_state["pending_clamped"] = clamped
        st.session_state["pending_saved"] = False

pending = st.session_state.get("pending_measurement")
if pending:
    st.subheader("計算結果")
    saved_label = "登録済み" if st.session_state.get("pending_saved") else "まだ登録されていません"
    st.caption(f"測定日: {pending['measurement_date']}　※{saved_label}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("推定基礎代謝", f"{pending['bmr_kcal']:,.0f} kcal/日")
    m2.metric("参考・代謝年齢", f"{pending['metabolic_age']:.1f} 歳")
    m3.metric("BMI", f"{bmi(pending['height_cm'], pending['weight_kg']):.1f}")
    m4.metric(
        "除脂肪量",
        f"{lean_body_mass(pending['weight_kg'], pending['body_fat_pct']):.1f} kg",
    )
    if st.session_state.get("pending_clamped"):
        st.warning("算定値が成人の比較範囲外だったため、18〜90歳の端の値を表示しています。")

    st.subheader("代謝量と年齢の関係")
    st.vega_lite_chart(spec=metabolism_chart(pending), use_container_width=True)
    st.caption(
        "青線は今回入力した性別・身長・体重に対するMifflin–St Jeor式の年齢別基準値、"
        "赤点は体脂肪率から求めた本人の基礎代謝量と参考代謝年齢です。"
    )

    if not st.session_state.get("pending_saved") and st.button(
        "この計算結果を登録する", type="primary", use_container_width=True
    ):
        try:
            replaced = save_row(pending)
        except APIError as exc:
            if getattr(exc, "code", None) == "42501":
                st.error(
                    "Supabaseの書き込み権限がありません。Streamlit SecretsのSUPABASE_KEYを、"
                    "SupabaseのSecret key（sb_secret_で始まる値）へ変更してください。"
                )
            else:
                error_code = getattr(exc, "code", "不明")
                error_message = getattr(exc, "message", "詳細なし")
                st.error(
                    "Supabaseへの登録に失敗しました。"
                    f" エラーコード: {error_code} / メッセージ: {error_message}"
                )
        except Exception:
            st.error("Supabaseとの通信中にエラーが発生しました。時間をおいて再度登録してください。")
        else:
            if replaced:
                st.session_state["flash_message"] = "同じ日付の記録を今回の計算結果で更新しました。"
            else:
                st.session_state["flash_message"] = "計算結果を登録しました。"
            st.session_state["pending_saved"] = True
            st.rerun()

data = load_data()
if not data.empty:
    data["measurement_date"] = pd.to_datetime(data["measurement_date"])
    st.subheader("経時変化")
    left, right = st.columns(2)
    left.line_chart(data.set_index("measurement_date")[["weight_kg", "body_fat_pct"]])
    right.line_chart(data.set_index("measurement_date")[["bmr_kcal", "metabolic_age"]])
    st.caption("左: 体重 (kg)・体脂肪率 (%) ／ 右: 基礎代謝 (kcal/日)・参考代謝年齢 (歳)")
    with st.expander("記録一覧"):
        shown = data.sort_values("measurement_date", ascending=False).copy()
        shown["measurement_date"] = shown["measurement_date"].dt.date
        st.dataframe(shown, use_container_width=True, hide_index=True)
else:
    st.info("まだ記録がありません。最初の測定値を登録してください。")

with st.expander("計算方法と注意事項"):
    st.markdown(
        """
- 基礎代謝量は、体脂肪率から求めた除脂肪量を **Katch–McArdle式** `370 + 21.6 × 除脂肪量(kg)` に当てはめた推定値です。
- 代謝年齢は、その基礎代謝量と同じ値になる年齢を **Mifflin–St Jeor式**から逆算した参考値です。市販体重計の独自指標とは一致しません。
- 代謝量と年齢のグラフも、入力した性別・身長・体重を固定してMifflin–St Jeor式から描いています。人口全体の統計分布や個人の将来予測ではありません。
- 内臓脂肪の表示単位は機器によって「%」「レベル」など異なります。経時比較のため、毎回同じ機器・条件で測ってください。
- 骨量と内臓脂肪は推移の記録に使います。一般に利用できる妥当な補正式がないため、代謝年齢へは加算していません。
- 本アプリの値は健康管理の目安であり、診断や治療には使えません。
"""
    )
