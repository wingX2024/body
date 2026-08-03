from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from supabase import Client, create_client
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from calculations import (
    bmi,
    katch_mcardle_bmr,
    lean_body_mass,
    metabolic_age,
    mifflin_st_jeor_bmr,
    validate_measurement,
)


TABLE_NAME = "body_measurements_private"
COLUMNS = [
    "measurement_date", "sex", "height_cm", "weight_kg", "body_fat_pct",
    "visceral_fat_pct", "bone_mass_kg", "bmr_kcal", "metabolic_age",
]


class SupabaseConfigurationError(RuntimeError):
    pass


def supabase_client() -> Client:
    if "supabase_client" in st.session_state:
        return st.session_state["supabase_client"]
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (KeyError, FileNotFoundError) as exc:
        raise SupabaseConfigurationError(
            "SUPABASE_URL または SUPABASE_KEY が設定されていません。"
        ) from exc
    if not str(key).startswith("sb_publishable_"):
        raise SupabaseConfigurationError(
            "個人データ保護のため、SUPABASE_KEYにはsb_publishable_から始まるPublishable keyを設定してください。"
        )
    st.session_state["supabase_client"] = create_client(url, key)
    return st.session_state["supabase_client"]


def load_data(user_id: str) -> pd.DataFrame:
    response = (
        supabase_client()
        .table(TABLE_NAME)
        .select(",".join(COLUMNS))
        .eq("user_id", user_id)
        .order("measurement_date")
        .execute()
    )
    data = pd.DataFrame(response.data, columns=COLUMNS)
    if not data.empty:
        data["sex"] = data["sex"].replace({"female": "女性", "male": "男性"})
        # Older/imported data may use different date notations. Normalize these
        # before displaying so one calendar day is always shown only once.
        data["measurement_date"] = pd.to_datetime(
            data["measurement_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        data = data.dropna(subset=["measurement_date"])
        data = data.drop_duplicates("measurement_date", keep="last")
    return data


def save_row(row: dict, user_id: str) -> bool:
    """Store exactly one record per date and return whether it was replaced."""
    client = supabase_client()
    existing = (
        client.table(TABLE_NAME)
        .select("measurement_date")
        .eq("user_id", user_id)
        .eq("measurement_date", row["measurement_date"])
        .limit(1)
        .execute()
    )
    existed = bool(existing.data)
    clean_row = {column: row[column] for column in COLUMNS}
    clean_row["user_id"] = user_id
    sex_for_storage = {"女性": "female", "男性": "male"}
    clean_row["sex"] = sex_for_storage.get(
        str(clean_row["sex"]).strip(), str(clean_row["sex"]).strip().lower()
    )
    client.table(TABLE_NAME).upsert(
        clean_row, on_conflict="user_id,measurement_date"
    ).execute()
    return existed


def metabolism_chart(row: dict) -> dict:
    point_bmr = katch_mcardle_bmr(row["weight_kg"], row["body_fat_pct"])
    point_age, _ = metabolic_age(
        row["height_cm"], row["weight_kg"], row["body_fat_pct"], row["sex"]
    )
    ages = list(range(18, 91))
    reference_values = [
        {
            "年齢": age,
            "基礎代謝量": mifflin_st_jeor_bmr(
                age, row["height_cm"], row["weight_kg"], row["sex"]
            ),
        }
        for age in ages
    ]
    person_value = [{"年齢": point_age, "基礎代謝量": point_bmr}]
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
        "height": 380,
        "layer": [
            {
                "data": {"values": reference_values},
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
                "data": {"values": person_value},
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


def import_csv(uploaded_file, user_id: str) -> tuple[int, list[str]]:
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
            save_row(values, user_id)
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
    client = supabase_client()
except SupabaseConfigurationError as exc:
    st.error(str(exc))
    st.code(
        'SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\n'
        'SUPABASE_KEY = "YOUR_PUBLISHABLE_KEY"',
        language="toml",
    )
    st.info("ローカルでは .streamlit/secrets.toml、Streamlit CloudではApp settingsのSecretsに設定してください。")
    st.stop()

if "auth_user" not in st.session_state:
    st.subheader("ログイン")
    login_tab, signup_tab = st.tabs(["ログイン", "新規アカウント作成"])
    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("メールアドレス", key="login_email")
            login_password = st.text_input("パスワード", type="password", key="login_password")
            login_clicked = st.form_submit_button("ログイン", type="primary", use_container_width=True)
        if login_clicked:
            try:
                response = client.auth.sign_in_with_password(
                    {"email": login_email.strip(), "password": login_password}
                )
                st.session_state["auth_user"] = response.user
                st.rerun()
            except Exception:
                st.error("ログインできませんでした。メールアドレス、パスワード、メール確認状況を確認してください。")
    with signup_tab:
        with st.form("signup_form"):
            signup_email = st.text_input("メールアドレス", key="signup_email")
            signup_password = st.text_input(
                "パスワード（8文字以上）", type="password", key="signup_password"
            )
            signup_clicked = st.form_submit_button("アカウントを作成", use_container_width=True)
        if signup_clicked:
            if len(signup_password) < 8:
                st.error("パスワードは8文字以上にしてください。")
            else:
                try:
                    response = client.auth.sign_up(
                        {"email": signup_email.strip(), "password": signup_password}
                    )
                    if response.session and response.user:
                        st.session_state["auth_user"] = response.user
                        st.rerun()
                    else:
                        st.success("確認メールを送信しました。メール内のリンクを開いてからログインしてください。")
                except AuthApiError as exc:
                    st.error(
                        "アカウントを作成できませんでした。"
                        f" エラーコード: {exc.code or exc.status} / メッセージ: {exc.message}"
                    )
                except Exception:
                    st.error("アカウントを作成できませんでした。入力内容またはSupabase Authの設定を確認してください。")
    st.info("ログインした利用者ごとにデータを分離して保存します。")
    st.stop()

auth_user = st.session_state["auth_user"]
user_id = str(auth_user.id)

try:
    client.table(TABLE_NAME).select("measurement_date").limit(1).execute()
except Exception:
    st.error("個人用テーブルに接続できません。Supabase SQL Editorで最新のsupabase_schema.sqlを実行してください。")
    st.stop()

with st.sidebar:
    st.caption(f"ログイン中: {auth_user.email}")
    if st.button("ログアウト", use_container_width=True):
        try:
            client.auth.sign_out()
        finally:
            for key in ["auth_user", "supabase_client", "pending_measurement", "pending_saved"]:
                st.session_state.pop(key, None)
            st.rerun()
    st.header("データ管理")
    uploaded = st.file_uploader("バックアップCSVを読み込む", type="csv")
    if uploaded and st.button("CSVを取り込む", use_container_width=True):
        count, import_errors = import_csv(uploaded, user_id)
        if count:
            st.success(f"{count}件を取り込みました。")
        for error in import_errors[:5]:
            st.error(error)
        if len(import_errors) > 5:
            st.error(f"ほか{len(import_errors) - 5}件のエラーがあります。")
    current = load_data(user_id)
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
    # Recalculate derived values from the pending inputs on every rerun. This
    # prevents stale session values from disagreeing with the chart.
    pending_bmr = katch_mcardle_bmr(
        pending["weight_kg"], pending["body_fat_pct"]
    )
    pending_age, pending_clamped = metabolic_age(
        pending["height_cm"], pending["weight_kg"], pending["body_fat_pct"], pending["sex"]
    )
    pending["bmr_kcal"] = round(pending_bmr, 1)
    pending["metabolic_age"] = round(pending_age, 1)
    st.session_state["pending_clamped"] = pending_clamped
    st.subheader("計算結果")
    saved_label = "登録済み" if st.session_state.get("pending_saved") else "まだ登録されていません"
    st.caption(
        f"測定日: {pending['measurement_date']}　性別: {pending['sex']}　※{saved_label}"
    )
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
    chart_key = (
        f"metabolism_{pending['sex']}_{pending['height_cm']}_"
        f"{pending['weight_kg']}_{pending['body_fat_pct']}"
    )
    st.vega_lite_chart(
        spec=metabolism_chart(pending),
        use_container_width=True,
        key=chart_key,
    )
    reference_at_18 = mifflin_st_jeor_bmr(
        18, pending["height_cm"], pending["weight_kg"], pending["sex"]
    )
    reference_at_90 = mifflin_st_jeor_bmr(
        90, pending["height_cm"], pending["weight_kg"], pending["sex"]
    )
    st.caption(
        "青線は今回入力した性別・身長・体重に対するMifflin–St Jeor式の年齢別基準値、"
        "赤点は体脂肪率から求めた本人の基礎代謝量と参考代謝年齢です。"
        f" 基準線の端点: 18歳 {reference_at_18:,.0f} kcal / 90歳 {reference_at_90:,.0f} kcal。"
    )

    if not st.session_state.get("pending_saved") and st.button(
        "この計算結果を登録する", type="primary", use_container_width=True
    ):
        try:
            replaced = save_row(pending, user_id)
        except APIError as exc:
            if getattr(exc, "code", None) == "42501":
                st.error(
                    "本人データへの書き込みがRLSに拒否されました。最新のsupabase_schema.sqlを実行し、"
                    "再ログインしてください。"
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

data = load_data(user_id)
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
