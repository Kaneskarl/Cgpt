import argparse
import getpass
from sqlalchemy import select
from .db import Base, engine, SessionLocal
from .models import User, OfficeSettings
from .security import passwords


def main():
    parser = argparse.ArgumentParser(description='Initialize the attendance database and first administrator')
    parser.add_argument('command', choices=['init', 'create-admin'])
    parser.add_argument('--username', default='admin')
    parser.add_argument('--name', default='Administrator')
    parser.add_argument('--if-missing', action='store_true', help='Keep an existing administrator unchanged')
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(OfficeSettings, 1):
            db.add(OfficeSettings(id=1))
            db.commit()
        if args.command == 'init':
            print('Database initialized.')
            return
        existing=db.scalar(select(User).where(User.username == args.username))
        if existing and args.if_missing and existing.role=='admin':
            print('Existing administrator preserved.')
            return
        if existing:
            raise SystemExit('Account already exists. Use the dashboard to manage it.')
        secret = getpass.getpass('Administrator password (12+ characters): ')
        if len(secret) < 12 or len(secret) > 256 or secret != getpass.getpass('Confirm password: '):
            raise SystemExit('Passwords must match and contain 12 to 256 characters.')
        db.add(User(username=args.username, name=args.name, role='admin', password_hash=passwords.hash(secret)))
        db.commit()
        print('Administrator created. No default accounts or passwords are installed.')


if __name__ == '__main__':
    main()
