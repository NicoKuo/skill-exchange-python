"""utils/helpers.py: Flask 應用程式的核心輔助函數庫。"""

from datetime import datetime, timezone, timedelta
import re

from flask import url_for
from markupsafe import Markup, escape
from sqlalchemy import or_, func

from models import db, Match, Review, Notification, Skill, User


# 台灣時區（UTC+8）
TAIWAN_TIMEZONE = timezone(timedelta(hours=8))

# 用來解析技能描述中嵌入的附件標記格式：<!--attachment:檔名|顯示名-->
ATTACHMENT_MARKER_RE = re.compile(
    r'(?s)^(.*?)(?:\n)?<!--attachment:([^|]+)\|([^>]+)-->$'
)

# 標籤分割正規表達式：支援全形逗號、半形逗號、頓號等分隔符
TAG_SPLIT_RE = re.compile(r'[，,、]+')


# -----------------------------------------------
# 模型相容性輔助函數（處理不同版本的欄位名稱差異）
# -----------------------------------------------

def model_has_attr(model, attr_name):
    """檢查模型類別是否具有指定屬性，避免 AttributeError。"""
    return hasattr(model, attr_name)


def get_skill_type(skill):
    """
    相容讀取技能的類型欄位（offer / learn）。
    支援兩種欄位命名：Skill.type 或 Skill.skill_type。
    回傳類型字串，若技能為 None 則回傳 None。
    """
    if not skill:
        return None

    if hasattr(skill, 'type'):
        return getattr(skill, 'type', None)

    if hasattr(skill, 'skill_type'):
        return getattr(skill, 'skill_type', None)

    return None


def skill_type_column():
    """
    回傳 Skill 類別的類型欄位物件（用於 SQLAlchemy 查詢）。
    相容 Skill.type 和 Skill.skill_type 兩種命名，避免版本不一致時出錯。
    """
    if hasattr(Skill, 'type'):
        return Skill.type

    if hasattr(Skill, 'skill_type'):
        return Skill.skill_type

    return None


def apply_common_skill_filters(query, user_id=None, skill_type=None):
    """
    對技能查詢套用常用的篩選條件（安全版本）。
    只有模型真的有該欄位時才加入 filter，避免 AttributeError。
    可篩選：指定使用者、技能類型、狀態為 open、is_active 為 True，
    並依建立時間倒序排列。
    """
    # 篩選指定使用者的技能
    if user_id is not None and hasattr(Skill, 'user_id'):
        query = query.filter(Skill.user_id == user_id)

    # 篩選技能類型（offer / learn）
    type_col = skill_type_column()
    if skill_type is not None and type_col is not None:
        query = query.filter(type_col == skill_type)

    # 只顯示狀態為 open 的技能
    if hasattr(Skill, 'status'):
        query = query.filter(Skill.status == 'open')

    # 只顯示上架中（is_active=True）的技能
    if hasattr(Skill, 'is_active'):
        query = query.filter(Skill.is_active.is_(True))

    # 依建立時間新到舊排序
    if hasattr(Skill, 'created_at'):
        query = query.order_by(Skill.created_at.desc())

    return query


# -----------------------------------------------
# 附件輔助函數
# -----------------------------------------------

def detect_attachment_type(filename_or_url):
    """
    根據檔名或 MIME 類型字串判斷附件類型。
    回傳：'image'（圖片）/ 'pdf'（PDF 文件）/ 'file'（其他檔案）/ None（無附件）。
    """
    if not filename_or_url:
        return None

    value = str(filename_or_url).strip().lower()
    if not value:
        return None

    # 處理 MIME 類型字串（可能含分號，如 image/jpeg; charset=utf-8）
    mime_value = value.split(';', 1)[0].strip()

    # 直接比對常見圖片 MIME 類型
    if mime_value in {'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'}:
        return 'image'

    if mime_value == 'application/pdf':
        return 'pdf'

    if mime_value.startswith('image/'):
        return 'image'

    # 從 URL 或檔名取得副檔名（去除查詢字串和錨點）
    base_value = value.split('?', 1)[0].split('#', 1)[0]
    extension = base_value.rsplit('.', 1)[-1] if '.' in base_value else ''

    if extension in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        return 'image'

    if extension == 'pdf':
        return 'pdf'

    return 'file'


def skill_attachment_url(attachment):
    """
    將各種格式的附件資訊轉換為可用的存取 URL。
    支援：dict 格式、URL 字串、相對路徑、檔名等輸入。
    回傳可用的 URL 字串，若無法解析則回傳 None。
    """
    if not attachment:
        return None

    # 處理 dict 格式（包含 url、stored_name 等鍵值）
    if isinstance(attachment, dict):
        direct_url = attachment.get('url')
        if direct_url:
            return direct_url

        stored_name = attachment.get('stored_name') or attachment.get('filename')
        if stored_name:
            try:
                return url_for('skills.skill_attachment', filename=stored_name)
            except Exception:
                return url_for('static', filename=f'uploads/{stored_name}')

        # 嘗試其他可能的鍵名
        attachment = (
            attachment.get('file_name')
            or attachment.get('path')
            or attachment.get('value')
        )

        if not attachment:
            return None

    attachment = str(attachment).strip()

    if not attachment:
        return None

    # 外部完整 URL 直接回傳
    if attachment.startswith(('http://', 'https://')):
        return attachment

    # 已是 /static/ 路徑直接回傳
    if attachment.startswith('/static/'):
        return attachment

    # uploads/ 開頭的相對路徑轉換為 static URL
    if attachment.startswith('uploads/'):
        return url_for('static', filename=attachment)

    # skill_attachments/ 前綴的檔案名稱
    if attachment.startswith('skill_attachments/'):
        filename = attachment.split('/', 1)[1]
        try:
            return url_for('skills.skill_attachment', filename=filename)
        except Exception:
            return url_for('static', filename=f'uploads/{filename}')

    # 其餘情況當作技能附件檔名處理
    try:
        return url_for('skills.skill_attachment', filename=attachment)
    except Exception:
        return url_for('static', filename=f'uploads/{attachment}')


def normalize_skill_attachment_url(skill):
    """
    從 Skill 物件取得規範化的附件 URL。
    優先使用資料庫中的 BLOB 資料（透過 skill_attachment 路由存取），
    其次使用 attachment_url 欄位。
    回傳 URL 字串或 None。
    """
    if not skill:
        return None

    # 若有 BLOB 資料，透過 ID 路由存取
    if getattr(skill, 'attachment_data', None):
        try:
            return url_for('skills.skill_attachment', skill_id=skill.id)
        except Exception:
            return None

    attachment_url = getattr(skill, 'attachment_url', None)

    if not attachment_url:
        return None

    attachment_url = str(attachment_url).strip()

    if not attachment_url:
        return None

    # 外部完整 URL 直接回傳
    if attachment_url.startswith(('http://', 'https://')):
        return attachment_url

    # 已是內部路由路徑直接回傳
    if attachment_url.startswith('/skills/') or attachment_url.startswith('/skill-attachments/'):
        return attachment_url

    if attachment_url.startswith('/static/'):
        return attachment_url

    # skill_attachments/ 前綴的相對路徑
    if attachment_url.startswith('skill_attachments/'):
        filename = attachment_url.split('/', 1)[1]
        try:
            return url_for('skills.skill_attachment', filename=filename)
        except Exception:
            return url_for('static', filename=f'uploads/{filename}')

    if attachment_url.startswith('uploads/'):
        return url_for('static', filename=attachment_url)

    # 其他情況取出最後一個路徑元件當作檔名
    filename = attachment_url.split('/')[-1]

    try:
        return url_for('skills.skill_attachment', filename=filename)
    except Exception:
        return url_for('static', filename=f'uploads/{filename}')


def split_skill_description(description):
    """
    將技能描述拆分為純文字部分與附件資訊。
    若描述末尾含有 <!--attachment:檔名|顯示名--> 標記，將其解析出來。
    回傳 (文字內容, 附件 dict 或 None)。
    """
    if not description:
        return '', None

    match = ATTACHMENT_MARKER_RE.match(description)

    if not match:
        return description, None

    return match.group(1).strip(), {
        'stored_name': match.group(2),   # 儲存的檔名
        'display_name': match.group(3),  # 顯示給使用者的檔名
    }


def render_skill_description(description, truncate=None):
    """
    將技能描述渲染為安全的 HTML Markup。
    - 自動將換行符轉換為 <br> 標籤
    - 若有附件標記，在描述後方附加附件連結
    - truncate 參數可限制文字最大長度（超過則截斷並加 ...）
    回傳 Markup 物件（可在模板中直接使用 | safe 輸出）。
    """
    text, attachment = split_skill_description(description)

    # 截斷文字（用於列表頁的預覽）
    if truncate and len(text) > truncate:
        text = text[:truncate].rstrip() + '...'

    # 將文字 escape 後轉換換行為 <br>
    html = escape(text).replace('\n', Markup('<br>'))

    # 若有附件，在描述後附加附件連結
    if attachment:
        attachment_url = skill_attachment_url(attachment)

        if attachment_url:
            html += Markup(
                '<div class="skill-attachment">'
                '<span class="tag tag-yellow">附件</span> '
                f'<a href="{escape(attachment_url)}" target="_blank" rel="noopener">'
                f'{escape(attachment["display_name"])}</a>'
                '</div>'
            )

    return Markup(html)


# -----------------------------------------------
# 使用者統計輔助函數
# -----------------------------------------------

def user_average_rating(user_id):
    """
    計算指定使用者的平均評分。
    從所有針對該使用者的評論中取平均值，四捨五入到小數點後一位。
    若無任何評論則回傳 0。
    """
    avg = db.session.query(func.avg(Review.rating)).filter(
        Review.reviewee_id == user_id
    ).scalar()

    return round(float(avg), 1) if avg else 0


def user_completed_matches(user_id):
    """
    計算指定使用者的已完成媒合次數。
    包含作為申請方或被申請方的所有 completed 狀態媒合。
    """
    return Match.query.filter(
        Match.status == 'completed',
        or_(Match.requester_id == user_id, Match.receiver_id == user_id)
    ).count()


def user_points(user_id):
    """
    計算指定使用者的累積積分。
    計算方式：每完成一次交換 +20 分，每收到一則評價 +5 分。
    """
    return (
        user_completed_matches(user_id) * 20
        + Review.query.filter_by(reviewee_id=user_id).count() * 5
    )


def user_pending_review_count(user_id):
    """
    計算指定使用者尚未評分的已完成媒合數量。
    用於提示使用者完成互評後才能進行下一次交換。
    """
    # 取得所有已完成的媒合 ID
    completed_ids = {
        match.id
        for match in Match.query.filter(
            Match.status == 'completed',
            or_(Match.requester_id == user_id, Match.receiver_id == user_id)
        ).all()
    }

    # 取得該使用者已評分的媒合 ID
    reviewed_ids = {
        row[0]
        for row in Review.query.filter_by(reviewer_id=user_id)
        .with_entities(Review.match_id)
        .all()
    }

    # 差集 = 已完成但尚未評分的媒合
    return len(completed_ids - reviewed_ids)


def user_badges(user_id):
    """
    根據使用者的活動數據計算並回傳成就徽章清單。
    每個徽章包含：name（名稱）、tier（等級：iron/bronze/silver/gold）、icon（表情符號）。
    徽章共分四大類：加入時間、技能數量、評價數量、交換次數。
    """
    badges = []

    # 取得統計數據
    completed = user_completed_matches(user_id)
    rating = user_average_rating(user_id)
    reviews = Review.query.filter_by(reviewee_id=user_id).count()

    # 查詢該使用者上架中的技能數
    skills_query = Skill.query
    if hasattr(Skill, 'user_id'):
        skills_query = skills_query.filter(Skill.user_id == user_id)
    if hasattr(Skill, 'status'):
        skills_query = skills_query.filter(Skill.status == 'open')
    skills = skills_query.count()

    # 計算使用者加入天數
    user = User.query.get(user_id)
    days = 0
    if user and getattr(user, 'created_at', None):
        days = (datetime.utcnow() - user.created_at).days

    # 基礎徽章：所有使用者都有
    badges.append({'name': '新會員', 'tier': 'iron', 'icon': '🔩'})

    # 加入時間徽章
    if days >= 7:
        badges.append({'name': '老朋友', 'tier': 'bronze', 'icon': '📅'})
    if days >= 30:
        badges.append({'name': '月老會員', 'tier': 'silver', 'icon': '🗓️'})
    if days >= 180:
        badges.append({'name': '半年元老', 'tier': 'gold', 'icon': '👑'})

    # 技能數量徽章
    if skills >= 1:
        badges.append({'name': '技能先鋒', 'tier': 'bronze', 'icon': '🎯'})
    if skills >= 3:
        badges.append({'name': '多才多藝', 'tier': 'silver', 'icon': '🎨'})
    if skills >= 6:
        badges.append({'name': '技能大師', 'tier': 'gold', 'icon': '🏆'})

    # 評價數量徽章
    if reviews >= 1:
        badges.append({'name': '初獲好評', 'tier': 'bronze', 'icon': '💬'})
    if reviews >= 5:
        badges.append({'name': '口碑累積', 'tier': 'silver', 'icon': '📣'})
    if reviews >= 15:
        badges.append({'name': '眾望所歸', 'tier': 'gold', 'icon': '🌟'})

    # 交換次數徽章
    if completed >= 1:
        badges.append({'name': '交換新手', 'tier': 'bronze', 'icon': '🤝'})
    if completed >= 3:
        badges.append({'name': '交換達人', 'tier': 'silver', 'icon': '🔗'})
    if completed >= 10:
        badges.append({'name': '交換大師', 'tier': 'gold', 'icon': '🌐'})

    # 高評價特殊徽章
    if rating >= 4.5 and reviews >= 3:
        badges.append({'name': '高評價成員', 'tier': 'silver', 'icon': '⭐'})
    if rating >= 4.9 and reviews >= 5:
        badges.append({'name': '完美評價', 'tier': 'gold', 'icon': '💎'})

    return badges


# -----------------------------------------------
# 標籤輔助函數
# -----------------------------------------------

def split_tags(tags):
    """
    將標籤字串拆分為清單。
    支援多種分隔符：全形逗號（，）、半形逗號（,）、頓號（、）。
    也接受已是 list/tuple/set 的輸入，去除空白並去重。
    """
    if not tags:
        return []

    if isinstance(tags, (list, tuple, set)):
        raw_tags = list(tags)
    else:
        raw_tags = TAG_SPLIT_RE.split(str(tags))

    cleaned_tags = []

    for tag in raw_tags:
        value = str(tag).strip()
        # 去除空字串，並防止重複
        if value and value not in cleaned_tags:
            cleaned_tags.append(value)

    return cleaned_tags


# -----------------------------------------------
# 通知輔助函數
# -----------------------------------------------

def unread_notifications_count(user_id):
    """
    取得指定使用者的未讀通知數量。
    用於導覽列顯示通知提示徽章。
    """
    return Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).count()


def add_notification(user_id, type_, content, related_id=None):
    """
    建立並儲存一則通知。
    參數：
      user_id   - 接收通知的使用者 ID
      type_     - 通知類型（如 'match_request' / 'message' / 'review' / 'system'）
      content   - 通知文字內容
      related_id - 關聯物件 ID（如 match_id），可選
    """
    db.session.add(
        Notification(
            user_id=user_id,
            type=type_,
            content=content,
            related_id=related_id
        )
    )

    db.session.commit()


# -----------------------------------------------
# 技能媒合輔助函數
# -----------------------------------------------

def skill_match_score(skill, user):
    """
    計算指定技能對使用者的媒合分數（0-95 分）。
    計算規則：
      基礎分 60 分
      +10 分：教學方式為 both（線上線下皆可）
      +10 分：技能類型為 offer（提供技能比想學技能更好媒合）
    回傳整數分數，最高 95 分。
    """
    score = 60

    if getattr(skill, 'method', None) == 'both':
        score += 10

    skill_type = get_skill_type(skill)

    if skill_type == 'offer':
        score += 10

    return min(score, 95)


def exchange_candidate_skills(selected_skill, current_user):
    """
    根據選定的技能，找出雙方可用來交換的技能清單。

    規則：
    - 若 selected_skill 是對方提供的（offer），
      目前使用者需拿自己的 offer 去交換，
      對方可能想學（learn）。
    - 若 selected_skill 是對方想學的（learn），
      目前使用者可用自己的 offer 對應。

    回傳 (我的候選技能清單, 對方候選技能清單)，若無法媒合則回傳 ([], [])。
    """
    if not selected_skill or not current_user:
        return [], []

    # 不能和自己媒合
    if getattr(selected_skill, 'user_id', None) == getattr(current_user, 'id', None):
        return [], []

    selected_type = get_skill_type(selected_skill)

    # 決定雙方各自需要哪種類型的技能
    if selected_type == 'offer':
        my_type = 'offer'
        other_type = 'learn'
    else:
        my_type = 'learn'
        other_type = 'offer'

    # 查詢我的可用技能
    my_query = apply_common_skill_filters(
        Skill.query,
        user_id=current_user.id,
        skill_type=my_type
    )

    # 查詢對方的可用技能
    other_query = apply_common_skill_filters(
        Skill.query,
        user_id=selected_skill.user_id,
        skill_type=other_type
    )

    return my_query.all(), other_query.all()


# -----------------------------------------------
# 時間輔助函數
# -----------------------------------------------

def format_taiwan_time(value, format_string='%Y-%m-%d %H:%M'):
    """
    將 UTC 時間轉換為台灣時區（UTC+8）並格式化為字串。
    參數：
      value         - datetime 物件（若無 tzinfo 則假設為 UTC）
      format_string - strftime 格式字串，預設 '%Y-%m-%d %H:%M'
    若 value 為 None 或空值則回傳空字串。
    """
    if not value:
        return ''

    if isinstance(value, datetime):
        # 若沒有時區資訊，假設為 UTC
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(TAIWAN_TIMEZONE).strftime(format_string)

    return value


# -----------------------------------------------
# 技能推薦輔助函數
# -----------------------------------------------

def get_skill_recommendations(user_id, limit=6, debug=False):
    """
    根據使用者的個人檔案，推薦可進行媒合的技能。

    推薦邏輯：
    1. 獲取當前使用者的已發佈技能並分類為：
       - offered_skills: 使用者能提供的技能（type='offer'）
       - wanted_skills: 使用者想要學的技能（type='learn'）
    
    2. 根據分類和標籤進行匹配，推薦其他使用者的技能：
       - 推薦「我想學」對應類型：其他使用者提供的相同分類技能（type='offer'）
       - 推薦「我能教」對應的需求：其他使用者想學的相同分類技能（type='learn'）

    參數：
      user_id - 當前使用者 ID
      limit   - 返回推薦的最多技能數量，預設 6 個

    回傳：
      dict 物件，包含：
        - 'wanted_matches': 當前使用者想學，而其他使用者提供的技能清單
        - 'offered_matches': 當前使用者提供，而其他使用者想學的技能清單
        - 'total_wanted': 第一類推薦的總數
        - 'total_offered': 第二類推薦的總數
    """
    # 獲取當前使用者的技能
    user_offered = apply_common_skill_filters(
        Skill.query,
        user_id=user_id,
        skill_type='offer'
    ).all()

    user_wanted = apply_common_skill_filters(
        Skill.query,
        user_id=user_id,
        skill_type='learn'
    ).all()

    # 從使用者個人檔案文字（offered_skills_intro / wanted_skills_intro）抽取關鍵字，作為補充匹配來源
    def extract_profile_keywords(text):
        if not text:
            return set()

        kws = set()

        # 先以標籤分割（支援中文/英文逗號等）
        parts = TAG_SPLIT_RE.split(text)

        # CJK 連續字元（長度 >=2）與 ASCII 文字（長度 >=2）都視為關鍵字
        cjk_re = re.compile(r'[\u4e00-\u9fff]{2,}')
        ascii_re = re.compile(r'[A-Za-z0-9]{2,}')

        for p in parts:
            p = p.strip()
            if not p:
                continue

            # 先找 CJK 片段
            for m in cjk_re.findall(p):
                kws.add(m)

            # 再找英文/數字 token
            for m in ascii_re.findall(p):
                kws.add(m.lower())

            # 若沒有透過上面抓到任何 token，退回以非字元分割並取長度 >=2 的片段
            if not cjk_re.search(p) and not ascii_re.search(p):
                for token in re.split(r"\W+", p):
                    t = token.strip()
                    if len(t) >= 2:
                        kws.add(t)

        return kws

    profile_offered_keywords = set()
    profile_wanted_keywords = set()
    user = None
    try:
        user = User.query.get(user_id)
        if user:
            profile_offered_keywords = extract_profile_keywords(getattr(user, 'offered_skills_intro', '') or '')
            profile_wanted_keywords = extract_profile_keywords(getattr(user, 'wanted_skills_intro', '') or '')
    except Exception:
        profile_offered_keywords = set()
        profile_wanted_keywords = set()

    # 如果使用者沒有技能，但有在個人檔案填寫關鍵字，我們仍然嘗試用關鍵字做回退推薦
    has_user_skills = bool(user_offered or user_wanted)

    # 蒐集已申請過媒合的技能 ID（避免推薦已申請的）
    applied_skill_ids = {
        row[0]
        for row in db.session.query(Match.skill_id)
        .filter(
            or_(
                Match.requester_id == user_id,
                Match.receiver_id == user_id,
            )
        )
        .distinct()
        .all()
    }

    # 基礎查詢：只顯示上架中的技能，不包括自己的技能，也不包括已申請過的
    base_query = Skill.query.filter(
        Skill.status == 'open',
        Skill.is_active.is_(True),
        Skill.user_id != user_id,
    )
    if applied_skill_ids:
        base_query = base_query.filter(~Skill.id.in_(applied_skill_ids))

    # 取得類型欄位的相容 column（避免不同 schema 命名造成的錯誤）
    type_col = skill_type_column()

    debug_info = {'profile_offered_keywords': list(profile_offered_keywords), 'profile_wanted_keywords': list(profile_wanted_keywords)} if debug else None

    # 推薦類型 1：當前使用者「想學」的，而其他使用者「提供」的
    # （按分類和標籤匹配）
    wanted_matches = []
    if user_wanted:
        wanted_categories = set()
        wanted_tags = set()

        for skill in user_wanted:
            if skill.category_id:
                wanted_categories.add(skill.category_id)
            if skill.tags:
                wanted_tags.update(split_tags(skill.tags))

        # 基於分類匹配
        if wanted_categories:
            if type_col is not None:
                category_query = base_query.filter(type_col == 'offer', Skill.category_id.in_(wanted_categories))
            else:
                category_query = base_query.filter(Skill.type == 'offer', Skill.category_id.in_(wanted_categories))

            wanted_matches = category_query.order_by(Skill.created_at.desc()).limit(limit).all()

    # 如果使用者沒有想學/提供技能，但在個人檔案有關鍵字，allow fallback later

    # 若分類匹配結果不足，使用個人檔案文字關鍵字做補充搜尋（例如使用者在 wanted_skills_intro 提到的關鍵詞）
    if (not wanted_matches or len(wanted_matches) < limit) and profile_wanted_keywords:
        kw_conds = []
        for kw in profile_wanted_keywords:
            kw = kw.strip()
            if not kw:
                continue
            kw_conds.append(or_(
                Skill.title.ilike(f"%{kw}%"),
                Skill.description.ilike(f"%{kw}%"),
                Skill.tags.ilike(f"%{kw}%")
            ))

        if kw_conds:
            if type_col is not None:
                query_with_kw = base_query.filter(type_col == 'offer', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()
            else:
                query_with_kw = base_query.filter(Skill.type == 'offer', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()

            # 合併並去重（保留先前的 category-based matches 優先）
            seen = {s.id for s in wanted_matches}
            for s in query_with_kw:
                if s.id not in seen and len(wanted_matches) < limit:
                    wanted_matches.append(s)
                    seen.add(s.id)

    # 推薦類型 2：當前使用者「能提供」的，而其他使用者「想學」的
    # （按分類和標籤匹配）
    offered_matches = []
    if user_offered:
        offered_categories = set()
        offered_tags = set()

        for skill in user_offered:
            if skill.category_id:
                offered_categories.add(skill.category_id)
            if skill.tags:
                offered_tags.update(split_tags(skill.tags))

        # 基於分類匹配
        if offered_categories:
            if type_col is not None:
                category_query = base_query.filter(type_col == 'learn', Skill.category_id.in_(offered_categories))
            else:
                category_query = base_query.filter(Skill.type == 'learn', Skill.category_id.in_(offered_categories))

            offered_matches = category_query.order_by(Skill.created_at.desc()).limit(limit).all()

        # 若分類匹配結果不足，使用個人檔案文字關鍵字做補充搜尋（例如使用者在 offered_skills_intro 提到的關鍵詞）
        if (not offered_matches or len(offered_matches) < limit) and profile_offered_keywords:
            kw_conds = []
            for kw in profile_offered_keywords:
                kw = kw.strip()
                if not kw:
                    continue
                kw_conds.append(or_(
                    Skill.title.ilike(f"%{kw}%"),
                    Skill.description.ilike(f"%{kw}%"),
                    Skill.tags.contains(kw)
                ))

            if kw_conds:
                if type_col is not None:
                    query_with_kw = base_query.filter(type_col == 'learn', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()
                else:
                    query_with_kw = base_query.filter(Skill.type == 'learn', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()

                seen = {s.id for s in offered_matches}
                for s in query_with_kw:
                    if s.id not in seen and len(offered_matches) < limit:
                        offered_matches.append(s)
                        seen.add(s.id)

    # 如果使用者本身沒有技能，但有 profile 關鍵字，使用關鍵字做回退搜尋填充推薦
    if not has_user_skills and (profile_wanted_keywords or profile_offered_keywords):
        # 搜尋其他人提供的技能（用 wanted 關鍵字）
        if profile_wanted_keywords and not wanted_matches:
            kw_conds = [or_(Skill.title.ilike(f"%{kw}%"), Skill.description.ilike(f"%{kw}%"), Skill.tags.ilike(f"%{kw}%")) for kw in profile_wanted_keywords]
            if kw_conds:
                if type_col is not None:
                    wanted_matches = base_query.filter(type_col == 'offer', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()
                else:
                    wanted_matches = base_query.filter(Skill.type == 'offer', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()

        # 搜尋其他人想學的技能（用 offered 關鍵字）
        if profile_offered_keywords and not offered_matches:
            kw_conds = [or_(Skill.title.ilike(f"%{kw}%"), Skill.description.ilike(f"%{kw}%"), Skill.tags.ilike(f"%{kw}%")) for kw in profile_offered_keywords]
            if kw_conds:
                if type_col is not None:
                    offered_matches = base_query.filter(type_col == 'learn', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()
                else:
                    offered_matches = base_query.filter(Skill.type == 'learn', or_(*kw_conds)).order_by(Skill.created_at.desc()).limit(limit).all()

    # 獲取推薦的總數（不計 limit）
    total_wanted = 0
    total_offered = 0

    if user_wanted and wanted_categories:
        if type_col is not None:
            total_wanted = base_query.filter(type_col == 'offer', Skill.category_id.in_(wanted_categories)).count()
        else:
            total_wanted = base_query.filter(Skill.type == 'offer', Skill.category_id.in_(wanted_categories)).count()

    if user_offered and offered_categories:
        if type_col is not None:
            total_offered = base_query.filter(type_col == 'learn', Skill.category_id.in_(offered_categories)).count()
        else:
            total_offered = base_query.filter(Skill.type == 'learn', Skill.category_id.in_(offered_categories)).count()

    if debug and debug_info is not None:
        debug_info.update({'wanted_count': len(wanted_matches), 'offered_count': len(offered_matches)})

    result = {
        'wanted_matches': wanted_matches,
        'offered_matches': offered_matches,
        'total_wanted': total_wanted,
        'total_offered': total_offered,
    }

    if debug and debug_info is not None:
        result['debug'] = debug_info

    return result
