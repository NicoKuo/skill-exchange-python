# 技能交換平台 Python Flask 版

這份專案將原本 PHP + MySQL 網站改成 **HTML + Python Flask**，保留原本卡片、Hero、統計、技能列表、媒合、聊天室、評價、通知與後台的展示版型。

## 本機測試
```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
python seed.py
python app.py
```

打開 http://127.0.0.1:5000

## 公開網站部署建議
可部署到 Render / Railway / Fly.io / VPS。正式公開網站建議把 `DATABASE_URL` 換成 PostgreSQL。

## 示範帳號
- admin@fju.edu.tw / 123456
- student1@fju.edu.tw / 123456
- student2@fju.edu.tw / 123456
