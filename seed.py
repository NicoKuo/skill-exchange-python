# seed.py: populate local database with sample data for development/testing
from app import app
from models import db, User, SkillCategory, Skill, Match, Message, Review, Notification

with app.app_context():
    db.drop_all(); db.create_all()
    cats=[('語言','英文、日文、韓文等語言學習'),('設計','平面設計、UI設計、影片剪輯'),('程式設計','網頁、Python、Java、資料庫'),('音樂','吉他、鋼琴、唱歌'),('運動','排球、健身、跑步'),('生活技能','料理、攝影、簡報製作')]
    cat_objs=[]
    for name,desc in cats:
        c=SkillCategory(name=name, description=desc); db.session.add(c); cat_objs.append(c)
    admin=User(name='管理員', email='admin@fju.edu.tw', role='admin', bio='系統管理者')
    s1=User(name='學生甲', email='student1@fju.edu.tw', role='student', bio='我會剪片，也想學英文口說')
    s2=User(name='學生乙', email='student2@fju.edu.tw', role='student', bio='我會英文會話，也想學設計')
    for u in [admin,s1,s2]: u.set_password('123456'); db.session.add(u)
    db.session.commit()
    skills=[
        Skill(user_id=s1.id, category_id=cat_objs[1].id, title='影片剪輯教學', description='可教基礎剪映、轉場、字幕與短影音剪輯技巧', type='offer', method='online', available_time='平日晚上'),
        Skill(user_id=s1.id, category_id=cat_objs[0].id, title='想學英文口說', description='想找人一起練習生活英文與面試英文', type='learn', method='offline', location='輔大附近', available_time='週末下午'),
        Skill(user_id=s2.id, category_id=cat_objs[0].id, title='英文會話陪練', description='可以練習日常英文、自我介紹與基本面試口說', type='offer', method='online', available_time='平日晚上'),
        Skill(user_id=s2.id, category_id=cat_objs[1].id, title='想學平面設計', description='想學海報、社群貼文與簡單排版技巧', type='learn', method='offline', location='新北', available_time='週末'),
    ]
    db.session.add_all(skills); db.session.commit()
    m1=Match(skill_id=skills[0].id, requester_id=s2.id, receiver_id=s1.id, message='你好，我對影片剪輯教學有興趣，想進一步了解。', status='pending')
    m2=Match(skill_id=skills[2].id, requester_id=s1.id, receiver_id=s2.id, message='我想用影片剪輯交換英文口說，這週可以約嗎？', status='completed')
    db.session.add_all([m1,m2]); db.session.commit()
    db.session.add_all([
        Message(match_id=m1.id, sender_id=s2.id, receiver_id=s1.id, content='你好，我想請問你影片剪輯主要是教哪種軟體呢？'),
        Message(match_id=m2.id, sender_id=s1.id, receiver_id=s2.id, content='我可以用影片剪輯和你交換英文口說。', is_read=True),
        Message(match_id=m2.id, sender_id=s2.id, receiver_id=s1.id, content='沒問題，我們這週三晚上線上進行。', is_read=True),
        Review(match_id=m2.id, reviewer_id=s1.id, reviewee_id=s2.id, rating=5, comment='英文口說交流很順利，適合展示系統評價功能。'),
        Review(match_id=m2.id, reviewer_id=s2.id, reviewee_id=s1.id, rating=5, comment='回覆快速，教學內容清楚，交換過程很順暢。'),
        Notification(user_id=s1.id, type='match_request', content='你收到一筆新的技能交換申請', related_id=m1.id),
        Notification(user_id=s1.id, type='message', content='你收到一則新訊息', related_id=m1.id),
        Notification(user_id=s2.id, type='system', content='歡迎登入 SkillSwap 展示版。'),
    ])
    db.session.commit()
    print('資料庫已建立，示範帳號：admin@fju.edu.tw / 123456')
