# 技能交換平台管理後台功能重構 - 實施摘要

## 修改日期
2026-05-04

## 一、後台卡片共用模板 ✅

### 新增文件
- `templates/admin/_admin_nav_card.html` - 共用的導覽卡片模板
  - 顯示所有管理頁面的按鈕
  - 當前頁面按鈕會顯示 active 樣式
  - 只有 super_admin 才看得到「管理者管理」按鈕
  - 新增「檢舉審查」按鈕供所有 admin/super_admin 使用

### 修改的模板
- `templates/admin/dashboard.html` - 加入 include _admin_nav_card
- `templates/admin/users.html` - 加入 include _admin_nav_card
- `templates/admin/skills.html` - 加入 include _admin_nav_card
- `templates/admin/matches.html` - 加入 include _admin_nav_card
- `templates/admin/managers.html` - 加入 include _admin_nav_card

### 修改的 Routes
- `routes/admin.py` - 所有 routes 現在傳入 `current_page` 變量

## 二、管理者管理功能改革 ✅

### 功能變更
- **舊**: 新增全新的管理者帳號（Email + 密碼）
- **新**: 從現有使用者中搜尋並升級為管理者

### 新增 Routes
- `POST /admin/managers/<int:user_id>/promote` (endpoint: `admin.promote_manager`)
  - 將使用者角色從 user 改為 admin
  - 檢查使用者 status 必須是 active
  - 記錄到 ActivityLog

### 修改的 Routes
- `GET/POST /admin/managers` (endpoint: `admin.managers`)
  - 改為只接受 GET 請求
  - 支援搜尋功能（姓名或 Email）
  - 分頁顯示一般使用者和管理者

### 修改的模板
- `templates/admin/managers.html`
  - 新增搜尋欄位
  - 顯示「設為管理者」按鈕
  - 對 admin 顯示「已是管理者」標籤
  - 保留刪除功能

## 三、導覽列權限管理 ✅

### 現有狀態
- `base.html` 已有條件判斷：
  ```jinja2
  {% if current_user.role in ['admin', 'super_admin'] %}
      <a href="{{ url_for('admin.dashboard') }}">後台</a>
  {% endif %}
  ```
- ✅ 一般使用者看不到「後台」按鈕
- ✅ admin/super_admin 可以看到並進入後台

## 四、檢舉系統 ✅

### 新增 Model
- `models.Report` - 檢舉紀錄表
  - 欄位: id, reporter_id, reported_user_id, match_id, skill_id, reason, description, status, admin_note, reviewed_by, created_at, updated_at
  - 支援的原因: inappropriate_language, harassment, no_show, scam, other
  - 支援的狀態: pending, reviewed, rejected, resolved

### 新增 Routes (routes/admin.py)
- `GET /admin/reports` (endpoint: `admin.reports`)
  - 顯示所有檢舉，預設 pending 優先
  - 支援按 status 篩選
  - 只有 admin/super_admin 可以進入

- `GET /admin/reports/<int:report_id>` (endpoint: `admin.report_detail`)
  - 顯示檢舉詳情
  - 顯示被檢舉人資訊和相關媒合

- `POST /admin/reports/<int:report_id>/update` (endpoint: `admin.update_report`)
  - 更新檢舉狀態和管理者備註
  - 記錄 reviewed_by

### 新增 Routes (routes/matches.py)
- `POST /match/report` (endpoint: `matches.create_report`)
  - 使用者送出檢舉
  - 防止重複檢舉（同一 match 的 pending 檢舉只能一筆）
  - 檢查使用者是否為 match 的參與者
  - 自動判斷被檢舉人

### 新增模板
- `templates/admin/reports.html` - 檢舉列表頁
  - 顯示所有檢舉
  - 支援按 status 篩選
  - 顯示檢舉人、被檢舉人、原因、時間等

- `templates/admin/report_detail.html` - 檢舉詳情頁
  - 顯示完整檢舉資訊
  - 管理者可以更新狀態和備註
  - 提供連結到使用者管理頁面

### 修改的模板
- `templates/match.html`
  - 新增檢舉按鈕
  - 檢舉表單顯示原因下拉選單和補充說明 textarea
  - 使用 JavaScript 切換表單顯示/隱藏

## 五、CSS 更新 ✅

### 新增樣式 (static/style.css)
- `.tag-blue` - 用於 reviewed 狀態
- `.btn.active` - 卡片按鈕的 active 狀態
- `.btn-muted.active` - muted 按鈕的 active 狀態

## 六、資料庫遷移 ✅

### 新增遷移腳本
- `migrate_reports.py` - 安全建立 reports 表
  - 不會 drop 任何現有資料
  - 檢查表是否已存在
  - 如果不存在就建立

### 執行方式
```bash
python migrate_reports.py
```

或者在應用啟動時由 `db.create_all()` 自動建立。

## 七、權限矩陣

| 功能 | user | admin | super_admin |
|------|------|-------|------------|
| 檢視管理後台導覽列 | ✗ | ✓ | ✓ |
| 進入 /admin | ✗ | ✓ | ✓ |
| 會員管理 | ✗ | ✓ (限定範圍) | ✓ |
| 技能管理 | ✗ | ✓ | ✓ |
| 媒合管理 | ✗ | ✓ | ✓ |
| 檢舉審查 | ✗ | ✓ | ✓ |
| 管理者管理 | ✗ | ✗ | ✓ |
| 送出檢舉 | ✓ | ✓ | ✓ |

## 八、測試檢查清單

- [ ] 一般使用者看不到導覽列的「後台」
- [ ] admin 使用者可以看到導覽列的「後台」
- [ ] super_admin 使用者可以看到導覽列的「後台」
- [ ] 一般使用者進入 /admin-entry 會被重定向
- [ ] admin 使用者可以進入 /admin
- [ ] admin 使用者可以進入 /admin/reports
- [ ] admin 使用者無法進入 /admin/managers（會得到 403）
- [ ] super_admin 使用者可以進入 /admin/managers
- [ ] super_admin 可以搜尋使用者
- [ ] super_admin 可以升級使用者為 admin
- [ ] 停權/封鎖的使用者無法被升級為 admin
- [ ] 一般使用者可以在媒合頁面看到檢舉按鈕
- [ ] 一般使用者可以填寫並送出檢舉表單
- [ ] 防止重複檢舉同一媒合
- [ ] admin 可以檢視檢舉列表
- [ ] admin 可以按 status 篩選檢舉
- [ ] admin 可以檢視檢舉詳情
- [ ] admin 可以更新檢舉狀態和備註
- [ ] 檢舉的 reviewed_by 記錄正確

## 九、檔案修改總覽

### 新增檔案
- `templates/admin/_admin_nav_card.html`
- `templates/admin/reports.html`
- `templates/admin/report_detail.html`
- `migrate_reports.py`

### 修改檔案
- `models.py` - 新增 Report model
- `routes/admin.py` - 修改 managers、新增 promote_manager、新增 reports routes、加入 current_page 變量
- `routes/matches.py` - 新增 create_report route
- `templates/admin/dashboard.html` - 加入 include
- `templates/admin/users.html` - 加入 include
- `templates/admin/skills.html` - 加入 include
- `templates/admin/matches.html` - 加入 include
- `templates/admin/managers.html` - 完全改寫
- `templates/match.html` - 新增檢舉表單和 JavaScript
- `static/style.css` - 新增 tag-blue 和 .btn.active 樣式

## 十、注意事項

1. ✅ 沒有刪除任何現有資料
2. ✅ 沒有修改 DATABASE_URL
3. ✅ 沒有修改 Render 設定
4. ✅ 沒有 drop_all() 操作
5. ✅ 保留了現有的管理者刪除功能
6. ✅ 所有新舊功能共存

## 十一、部署步驟

1. 部署新的代碼
2. 執行 `python migrate_reports.py` 建立 reports 表
3. 重啟應用
4. 驗證功能是否正常

## 十二、回滾計畫

如需回滾：
1. 恢復之前的代碼
2. reports 表保留（不會影響現有功能）
3. 重啟應用

---
實施完成於: 2026-05-04
