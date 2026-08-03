# 体組成トラッカー

身長、体重、体脂肪率、内臓脂肪、骨量を日々記録し、推定基礎代謝量と参考の代謝年齢、経時変化を表示するStreamlitアプリです。

## ローカル起動

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

1. このディレクトリをGitHubリポジトリへpushします。
2. Streamlit Community Cloudでリポジトリを選び、Main file pathを `app.py` にします。
3. Deployを実行します。

## Supabaseの設定

記録はSupabaseへ永続保存されます。

1. Supabaseでプロジェクトを作成します。
2. DashboardのSQL Editorで `supabase_schema.sql` を実行します。
3. Project Settings > APIでProject URLと `service_role` keyを確認します。
4. Streamlit Community CloudのApp settings > Secretsに次を登録します。

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_SERVICE_ROLE_KEY"
```

ローカル実行時は `.streamlit/secrets.toml.example` を `.streamlit/secrets.toml` としてコピーし、値を設定してください。`service_role` keyは秘密情報です。GitHubへコミットしないでください。RLSは有効化され、公開ポリシーは作成しない構成です。公開URLを他人も利用できる状態にすると、その人もアプリ経由でデータを操作できるため、個人利用ではStreamlitアプリをPrivateにしてください。

既存のSQLiteデータは、旧アプリでダウンロードしたCSVをサイドバーから取り込むことで移行できます。

## 算定について

- 基礎代謝量: Katch–McArdle式
- 参考代謝年齢: 上記代謝量と同値になる年齢をMifflin–St Jeor式から逆算（18〜90歳）

メーカー独自の「体年齢」と同じものではなく、医療診断にも利用できません。
