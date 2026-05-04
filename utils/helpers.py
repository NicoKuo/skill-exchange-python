"""Utility helper functions used in templates and route logic."""

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

    if skill.location and user.bio and skill.location in user.bio:
        score += 10

    if skill.type == 'offer':
        score += 10

    return min(score, 95)


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
        attachment_url = url_for(
            'skills.skill_attachment',
            filename=attachment['stored_name']
        )

        html += Markup(
            '<div class="skill-attachment">'
            '<span class="tag tag-yellow">附件</span> '
            f'<a href="{escape(attachment_url)}" '
            f'target="_blank" rel="noopener">'
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
