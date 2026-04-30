"""Utility helper functions used in templates and route logic."""

from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, func
from models import db, Match, Review, Notification


TAIWAN_TIMEZONE = timezone(timedelta(hours=8))

def user_average_rating(user_id):
    avg = db.session.query(func.avg(Review.rating)).filter(Review.reviewee_id == user_id).scalar()
    return round(float(avg), 1) if avg else 0

def user_completed_matches(user_id):
    return Match.query.filter(
        Match.status == 'completed',
        or_(Match.requester_id == user_id, Match.receiver_id == user_id)
    ).count()

def user_points(user_id):
    return user_completed_matches(user_id) * 20 + Review.query.filter_by(reviewee_id=user_id).count() * 5

def user_badges(user_id):
    badges=[]
    completed=user_completed_matches(user_id)
    rating=user_average_rating(user_id)
    if completed >= 1: badges.append('交換新手')
    if completed >= 3: badges.append('交換達人')
    if rating >= 4.5: badges.append('高評價成員')
    return badges

def unread_notifications_count(user_id):
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()

def add_notification(user_id, type_, content, related_id=None):
    db.session.add(Notification(user_id=user_id, type=type_, content=content, related_id=related_id))
    db.session.commit()

def skill_match_score(skill, user):
    score = 60
    if skill.method == 'both': score += 10
    if skill.location and user.bio and skill.location in user.bio: score += 10
    if skill.type == 'offer': score += 10
    return min(score, 95)


def format_taiwan_time(value, format_string='%Y-%m-%d %H:%M'):
    if not value:
        return ''

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(TAIWAN_TIMEZONE).strftime(format_string)

    return value
