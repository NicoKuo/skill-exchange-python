"""
Safe database migration script - Create reports table without dropping existing data.
Run this script if db.create_all() is not sufficient.
"""

from app import app
from models import db, Report

def migrate_create_reports_table():
    """Create the reports table if it doesn't exist."""
    with app.app_context():
        try:
            # Try to query the reports table - if it exists, this will work
            Report.query.first()
            print("✓ 'reports' table already exists.")
            return True
        except Exception as e:
            # Table doesn't exist, create it
            print(f"Creating 'reports' table...")
            try:
                db.create_all()
                print("✓ 'reports' table created successfully.")
                return True
            except Exception as create_error:
                print(f"✗ Failed to create table: {create_error}")
                return False

if __name__ == '__main__':
    success = migrate_create_reports_table()
    if success:
        print("\n✓ Database migration completed successfully!")
    else:
        print("\n✗ Database migration failed!")
        exit(1)
