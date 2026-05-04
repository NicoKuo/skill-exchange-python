#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
安全遷移腳本：添加 message_id 到 reports 表
使用 ALTER TABLE 確保資料安全，不刪除任何現有資料
"""
import os
import sys
from app import create_app, db

def migrate():
    """執行遷移"""
    app = create_app()
    
    with app.app_context():
        # 連接到資料庫
        conn = db.engine.connect()
        
        try:
            # 檢查 reports 表中是否已存在 message_id 欄位
            inspector = db.inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('reports')]
            
            if 'message_id' not in columns:
                print("添加 message_id 欄位到 reports 表...")
                conn.execute(db.text('''
                    ALTER TABLE reports 
                    ADD COLUMN message_id INTEGER
                '''))
                
                # 添加外鍵約束
                conn.execute(db.text('''
                    ALTER TABLE reports 
                    ADD CONSTRAINT fk_reports_message_id 
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
                '''))
                
                print("✓ message_id 欄位已成功添加")
            else:
                print("✓ message_id 欄位已存在，跳過")
            
            # 確保 Message 模型的 is_read 欄位存在
            if 'is_read' not in columns:
                # 檢查 messages 表
                msg_columns = [c['name'] for c in inspector.get_columns('messages')]
                
                if 'is_read' not in msg_columns:
                    print("添加 is_read 欄位到 messages 表...")
                    conn.execute(db.text('''
                        ALTER TABLE messages 
                        ADD COLUMN is_read BOOLEAN DEFAULT 0
                    '''))
                    print("✓ is_read 欄位已成功添加")
                else:
                    print("✓ is_read 欄位已存在於 messages 表，跳過")
            
            conn.commit()
            print("\n✓ 遷移完成！")
            print("所有報告和訊息欄位已準備就緒。")
            
        except Exception as e:
            conn.rollback()
            print(f"✗ 遷移失敗: {e}")
            sys.exit(1)
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
