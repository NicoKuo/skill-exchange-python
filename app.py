import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import or_

from models import db, User, SkillCategory, Skill, Match, Message, Review, Notification
from helpers import (
    user_average_rating,
    user_completed_matches,
    user_points,
    user_badges,
    unread_notifications_count,
    add_notification,
    skill_match_score
)

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///skill_exchange.db"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_helpers():
    return dict(
        user_average_rating=user_average_rating,
        user_completed_matches=user_completed_matches,
        user_points=user_points,
        user_badges=user_badges,
        unread_notifications_count=unread_notifications_count,
        skill_match_score=skill_match_score
    )


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    stats = {
        "users": User.query.filter_by(role="student").count(),
        "skills": Skill.query.filter_by(status="open").count(),
        "matches": Match.query.filter(Match.status.in_(["accepted", "completed", "pending"])).count(),
        "reviews": Review.query.count(),
    }

    popular_skills = Skill.query.filter_by(status="open").order_by(Skill.created_at.desc()).limit(6).all()
    top_users = User.query.filter_by(role="student").limit(5).all()

    return render_template(
        "index.html",
        stats=stats,
        popular_skills=popular_skills,
        top_users=top_users
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("姓名、Email 必填，密碼至少 6 碼。", "error")
        elif User.query.filter_by(email=email).first():
            flash("這個 Email 已被註冊。", "error")
        else:
            user = User(name=name, email=email, role="student", bio="")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash("註冊成功，請登入。", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.status == "active":
            login_user(user)
            flash("登入成功。", "success")
            return redirect(url_for("dashboard"))

        flash("Email 或密碼錯誤。", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已登出。", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    my_skills = Skill.query.filter_by(user_id=current_user.id).order_by(Skill.created_at.desc()).all()
    return render_template("dashboard.html", my_skills=my_skills)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", "").strip()
        current_user.bio = request.form.get("bio", "").strip()
        current_user.avatar = request.form.get("avatar", "").strip() or None

        new_password = request.form.get("new_password", "").strip()

        if not current_user.name:
            flash("姓名不能空白。", "error")
        elif new_password and len(new_password) < 6:
            flash("新密碼至少 6 碼。", "error")
        else:
            if new_password:
                current_user.set_password(new_password)

            db.session.commit()
            flash("個人資料已更新。", "success")
            return redirect(url_for("profile"))

    reviews = Review.query.filter_by(reviewee_id=current_user.id).order_by(Review.created_at.desc()).all()
    return render_template("profile.html", reviews=reviews)


@app.route("/skills")
def skills():
    keyword = request.args.get("keyword", "").strip()
    category_id = request.args.get("category_id", "").strip()
    method = request.args.get("method", "").strip()

    query = Skill.query.filter_by(status="open")

    if keyword:
        query = query.filter(
            or_(
                Skill.title.contains(keyword),
                Skill.description.contains(keyword)
            )
        )

    if category_id:
        query = query.filter_by(category_id=int(category_id))

    if method:
        query = query.filter_by(method=method)

    skills = query.order_by(Skill.created_at.desc()).all()
    categories = SkillCategory.query.all()

    return render_template(
        "skills.html",
        skills=skills,
        categories=categories,
        keyword=keyword,
        category_id=category_id,
        method=method
    )


@app.route("/add-skill", methods=["GET", "POST"])
@login_required
def add_skill():
    categories = SkillCategory.query.all()

    if request.method == "POST":
        skill = Skill(
            user_id=current_user.id,
            category_id=int(request.form.get("category_id") or 0) or None,
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            type=request.form.get("type", "offer"),
            method=request.form.get("method", "online"),
            location=request.form.get("location", "").strip(),
            available_time=request.form.get("available_time", "").strip(),
            status="open"
        )

        if not skill.title or not skill.description:
            flash("技能標題與描述必填。", "error")
        else:
            db.session.add(skill)
            db.session.commit()
            flash("技能已上架。", "success")
            return redirect(url_for("skills"))

    return render_template("add_skill.html", categories=categories)


@app.route("/match", methods=["GET", "POST"])
@login_required
def match_center():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            skill = Skill.query.get_or_404(int(request.form.get("skill_id")))

            if skill.user_id == current_user.id:
                flash("不能媒合自己的技能。", "error")
            else:
                exists = Match.query.filter(
                    Match.skill_id == skill.id,
                    Match.requester_id == current_user.id,
                    Match.status.in_(["pending", "accepted"])
                ).first()

                if exists:
                    flash("你已送出過這筆媒合邀請。", "error")
                else:
                    m = Match(
                        skill_id=skill.id,
                        requester_id=current_user.id,
                        receiver_id=skill.user_id,
                        message=request.form.get("message") or "想和你進一步交換技能。"
                    )
                    db.session.add(m)
                    db.session.commit()
                    add_notification(skill.user_id, "match_request", "你收到新的技能媒合邀請。", m.id)
                    flash("媒合邀請已送出。", "success")

            return redirect(url_for("match_center"))

        if action in ["accepted", "rejected", "completed", "cancelled"]:
            m = Match.query.get_or_404(int(request.form.get("match_id")))

            if current_user.id not in [m.requester_id, m.receiver_id]:
                abort(403)

            m.status = action
            db.session.commit()

            other = m.requester_id if m.receiver_id == current_user.id else m.receiver_id
            add_notification(other, "system", f"你的媒合狀態更新為：{action}", m.id)

            flash("媒合狀態已更新。", "success")
            return redirect(url_for("match_center"))

    selected_skill = Skill.query.get(request.args.get("skill_id")) if request.args.get("skill_id") else None

    matches = Match.query.filter(
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).order_by(Match.updated_at.desc()).all()

    return render_template("match.html", selected_skill=selected_skill, matches=matches)


@app.route("/chat/<int:match_id>", methods=["GET", "POST"])
@login_required
def chat(match_id):
    m = Match.query.get_or_404(match_id)

    if current_user.id not in [m.requester_id, m.receiver_id]:
        abort(403)

    other_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id

    if request.method == "POST":
        content = request.form.get("content", "").strip()

        if content:
            db.session.add(
                Message(
                    match_id=m.id,
                    sender_id=current_user.id,
                    receiver_id=other_id,
                    content=content
                )
            )
            db.session.commit()
            add_notification(other_id, "message", "你收到一則新訊息。", m.id)
            return redirect(url_for("chat", match_id=m.id))

    messages = Message.query.filter_by(match_id=m.id).order_by(Message.created_at.asc()).all()

    return render_template("chat.html", match=m, messages=messages, other_id=other_id)


@app.route("/review", methods=["GET", "POST"])
@login_required
def review():
    completed = Match.query.filter(
        Match.status == "completed",
        or_(
            Match.requester_id == current_user.id,
            Match.receiver_id == current_user.id
        )
    ).all()

    if request.method == "POST":
        m = Match.query.get_or_404(int(request.form.get("match_id")))

        if current_user.id not in [m.requester_id, m.receiver_id]:
            abort(403)

        reviewee_id = m.receiver_id if current_user.id == m.requester_id else m.requester_id
        rating = max(1, min(5, int(request.form.get("rating", 5))))

        db.session.add(
            Review(
                match_id=m.id,
                reviewer_id=current_user.id,
                reviewee_id=reviewee_id,
                rating=rating,
                comment=request.form.get("comment", "").strip()
            )
        )

        db.session.commit()
        add_notification(reviewee_id, "review", "你收到新的評價。", m.id)

        flash("評價已送出。", "success")
        return redirect(url_for("review"))

    return render_template("review.html", completed=completed)


@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()

    for item in items:
        item.is_read = True

    db.session.commit()

    return render_template("notifications.html", items=items)


@app.route("/admin")
@login_required
@admin_required
def admin():
    users = User.query.order_by(User.created_at.desc()).all()
    skills = Skill.query.order_by(Skill.created_at.desc()).all()

    return render_template("admin.html", users=users, skills=skills)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="127.0.0.1", port=5000, debug=True)