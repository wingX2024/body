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
3. Project Settings > API KeysでProject URLと `sb_publishable_` から始まるPublishable keyを確認します。
4. Streamlit Community CloudのApp settings > Secretsに次を登録します。

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_PUBLISHABLE_KEY"
```

ローカル実行時は `.streamlit/secrets.toml.example` を `.streamlit/secrets.toml` としてコピーし、値を設定してください。アプリではメールアドレスとパスワードによるSupabase Authログインが必須です。各行にユーザーIDを保存し、RLSによって本人の行だけを読み書きできます。Secret keyや旧service_role keyは使用しません。

Supabase DashboardのAuthentication > ProvidersでEmailを有効にしてください。メール確認を有効にしている場合、新規登録後に確認メール内のリンクを開いてからログインします。

既存データは、ログイン後にバックアップCSVをサイドバーから取り込むことで、そのログイン利用者のデータとして移行できます。以前の共有テーブル `body_measurements` は削除せずアクセスだけを閉じ、新しい `body_measurements_private` テーブルを使用します。

## 算定について

- 基礎代謝量: Katch–McArdle式
- 参考代謝年齢: 上記代謝量と同値になる年齢をMifflin–St Jeor式から逆算（18〜90歳）

メーカー独自の「体年齢」と同じものではなく、医療診断にも利用できません。
