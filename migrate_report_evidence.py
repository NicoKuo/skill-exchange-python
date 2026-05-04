#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
安全遷移腳本：添加檢舉附件欄位到 reports 表
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
            # 檢查 reports 表中是否已存在附件欄位
            inspector = db.inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('reports')]
            
            fields_to_add = [
                ('evidence_file_url', 'VARCHAR(500)'),
                ('evidence_file_name', 'VARCHAR(255)'),
                ('evidence_file_type', 'VARCHAR(20)')
            ]
            
            for field_name, field_type in fields_to_add:
                if field_name not in columns:
                    print(f"添加 {field_name} 欄位到 reports 表...")
                    conn.execute(db.text(f'''
                        ALTER TABLE reports 
                        ADD COLUMN {field_name} {field_type}
                    '''))
                    print(f"✓ {field_name} 欄位已成功添加")
                else:
                    print(f"✓ {field_name} 欄位已存在，跳過")
            
            conn.commit()
            print("\n✓ 遷移完成！")
            print("所有檢舉附件欄位已準備就緒。")
            
        except Exception as e:
            conn.rollback()
            print(f"✗ 遷移失敗: {e}")
            sys.exit(1)
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
