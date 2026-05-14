"""屁眼"""

from datetime import datetime, timezone, timedelta
import re

from flask import url_for
from markupsafe import Markup, escape
from sqlalchemy import or_, func
from models import db, Match, Review, Notification, Skill, User


TAIWAN_TIMEZONE = timezone(timedelta(hours=8))

ATTACHMENT_MARKER_RE = re.compile(
    r'(?s)^(.*?)(?:\n)?<!--attachment:([^|]+)\|([^>]+)-->$'
)

TAG_SPLIT_RE = re.compile(r'[，,、]+')


def detect_attachment_type(filename_or_url):
    if not filename_or_url:
        return None

    value = str(filename_or_url).strip().lower()
    if not value:
        return None

    mime_value = value.split(';', 1)[0].strip()
    if mime_value in {'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'}:
        return 'image'
    if mime_value == 'application/pdf':
        return 'pdf'
    if mime_value.startswith('image/'):
        return 'image'

    base_value = value.split('?', 1)[0].split('#', 1)[0]
    extension = base_value.rsplit('.', 1)[-1] if '.' in base_value else ''
    if extension in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        return 'image'
    if extension == 'pdf':
        return 'pdf'

    return 'file'


def user_average_rating(user_id):
    avg = db.session.query(func.avg(Review.rating)).filter(
        Review.reviewee_id == user_id
    ).scalar()

    return round(float(avg), 1) if avg else 0


def user_completed_matches(user_id):
    return Match.query.filter(
        Match.status == 'completed',
        or_(Match.requester_id == user_id, Match.receiver_id == user_id)
    ).count()


def user_points(user_id):
    return (
        user_completed_matches(user_id) * 20
        + Review.query.filter_by(reviewee_id=user_id).count() * 5
    )


def user_pending_review_count(user_id):
    completed_ids = {
        match.id
        for match in Match.query.filter(
            Match.status == 'completed',
            or_(Match.requester_id == user_id, Match.receiver_id == user_id)
        ).all()
    }

    reviewed_ids = {
        row[0]
        for row in Review.query.filter_by(reviewer_id=user_id)
        .with_entities(Review.match_id)
        .all()
    }

    return len(completed_ids - reviewed_ids)


def split_tags(tags):
    if not tags:
        return []

    if isinstance(tags, (list, tuple, set)):
        raw_tags = list(tags)
    else:
        raw_tags = TAG_SPLIT_RE.split(str(tags))

    cleaned_tags = []
    for tag in raw_tags:
        value = str(tag).strip()
        if value and value not in cleaned_tags:
            cleaned_tags.append(value)

    return cleaned_tags


def skill_attachment_url(attachment):
    if not attachment:
        return None

    if isinstance(attachment, dict):
        direct_url = attachment.get('url')
        if direct_url:
            return direct_url

        stored_name = attachment.get('stored_name') or attachment.get('filename')
        if stored_name:
            return url_for('skills.skill_attachment', filename=stored_name)

        attachment = attachment.get('file_name') or attachment.get('path') or attachment.get('value')
        if not attachment:
            return None

    attachment = str(attachment).strip()
    if not attachment:
        return None

    if attachment.startswith(('http://', 'https://')):
        return attachment

    if attachment.startswith('/static/'):
        return attachment

    if attachment.startswith('uploads/'):
        return url_for('static', filename=attachment)

    if attachment.startswith('skill_attachments/'):
        return url_for('skills.skill_attachment', filename=attachment.split('/', 1)[1])

    return url_for('static', filename=f'uploads/{attachment}')


def normalize_skill_attachment_url(skill):
    if not skill:
        return None

    if getattr(skill, 'attachment_data', None):
        return url_for('skills.skill_attachment', skill_id=skill.id)

    attachment_url = getattr(skill, 'attachment_url', None)
    if attachment_url:
        attachment_url = str(attachment_url).strip()
        if attachment_url.startswith(('http://', 'https://')):
            return attachment_url
        if attachment_url.startswith('/skills/') or attachment_url.startswith('/skill-attachments/'):
            return attachment_url
        if attachment_url.startswith('/static/'):
            return attachment_url
        if attachment_url.startswith('skill_attachments/'):
            return url_for('skills.skill_attachment', filename=attachment_url.split('/', 1)[1])
        if attachment_url.startswith('uploads/'):
            return url_for('static', filename=attachment_url)
        return url_for('skills.skill_attachment', filename=attachment_url.split('/')[-1])

    return None


def user_badges(user_id):
    badges = []

    completed = user_completed_matches(user_id)
    rating = user_average_rating(user_id)
    reviews = Review.query.filter_by(reviewee_id=user_id).count()
    skills = Skill.query.filter_by(user_id=user_id, status='open').count()
    user = User.query.get(user_id)

    days = (datetime.utcnow() - user.created_at).days if user else 0

    badges.append({
        'name': '新會員',
        'tier': 'iron',
        'icon': '🔩'
    })

    if days >= 7:
        badges.append({
            'name': '老朋友',
            'tier': 'bronze',
            'icon': '📅'
        })

    if days >= 30:
        badges.append({
            'name': '月老會員',
            'tier': 'silver',
            'icon': '🗓️'
        })

    if days >= 180:
        badges.append({
            'name': '半年元老',
            'tier': 'gold',
            'icon': '👑'
        })

    if skills >= 1:
        badges.append({
            'name': '技能先鋒',
            'tier': 'bronze',
            'icon': '🎯'
        })

    if skills >= 3:
        badges.append({
            'name': '多才多藝',
            'tier': 'silver',
            'icon': '🎨'
        })

    if skills >= 6:
        badges.append({
            'name': '技能大師',
            'tier': 'gold',
            'icon': '🏆'
        })

    if reviews >= 1:
        badges.append({
            'name': '初獲好評',
            'tier': 'bronze',
            'icon': '💬'
        })

    if reviews >= 5:
        badges.append({
            'name': '口碑累積',
            'tier': 'silver',
            'icon': '📣'
        })

    if reviews >= 15:
        badges.append({
            'name': '眾望所歸',
            'tier': 'gold',
            'icon': '🌟'
        })

    if completed >= 1:
        badges.append({
            'name': '交換新手',
            'tier': 'bronze',
            'icon': '🤝'
        })

    if completed >= 3:
        badges.append({
            'name': '交換達人',
            'tier': 'silver',
            'icon': '🔗'
        })

    if completed >= 10:
        badges.append({
            'name': '交換大師',
            'tier': 'gold',
            'icon': '🌐'
        })

    if rating >= 4.5 and reviews >= 3:
        badges.append({
            'name': '高評價成員',
            'tier': 'silver',
            'icon': '⭐'
        })

    if rating >= 4.9 and reviews >= 5:
        badges.append({
            'name': '完美評價',
            'tier': 'gold',
            'icon': '💎'
        })

    return badges


def unread_notifications_count(user_id):
    return Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).count()


def add_notification(user_id, type_, content, related_id=None):
    db.session.add(
        Notification(
            user_id=user_id,
            type=type_,
            content=content,
            related_id=related_id
        )
    )

    db.session.commit()


def skill_match_score(skill, user):
    score = 60

    if skill.method == 'both':
        score += 10

    if skill.location_area and user.bio and skill.location_area in user.bio:
        score += 10

    if skill.type == 'offer':
        score += 10

    return min(score, 95)


def exchange_candidate_skills(selected_skill, current_user):
    if not selected_skill or selected_skill.user_id == current_user.id:
        return [], []

    if selected_skill.type == 'offer':
        my_type = 'offer'
        other_type = 'learn'
    else:
        my_type = 'learn'
        other_type = 'offer'

    my_skills = Skill.query.filter_by(
        user_id=current_user.id,
        type=my_type,
        status='open',
        is_active=True,
    ).order_by(Skill.created_at.desc()).all()

    other_skills = Skill.query.filter_by(
        user_id=selected_skill.user_id,
        type=other_type,
        status='open',
        is_active=True,
    ).order_by(Skill.created_at.desc()).all()

    return my_skills, other_skills


def split_skill_description(description):
    if not description:
        return '', None

    match = ATTACHMENT_MARKER_RE.match(description)

    if not match:
        return description, None

    return match.group(1).strip(), {
        'stored_name': match.group(2),
        'display_name': match.group(3),
    }


def render_skill_description(description, truncate=None):
    text, attachment = split_skill_description(description)

    if truncate and len(text) > truncate:
        text = text[:truncate].rstrip() + '...'

    html = escape(text).replace('\n', Markup('<br>'))

    if attachment:
        attachment_url = skill_attachment_url(attachment)

        html += Markup(
            '<div class="skill-attachment">'
            '<span class="tag tag-yellow">附件</span> '
            f'<a href="{escape(attachment_url)}" target="_blank" rel="noopener">'
            f'{escape(attachment["display_name"])}</a>'
            '</div>'
        )

    return Markup(html)


def format_taiwan_time(value, format_string='%Y-%m-%d %H:%M'):
    if not value:
        return ''

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(TAIWAN_TIMEZONE).strftime(
            format_string
        )

    return value
