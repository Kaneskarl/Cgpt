"""PostgreSQL backup and restore to a separate empty database. Secrets stay in child environments."""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
import psycopg

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')


def run(args, env):
    result=subprocess.run(args,env=env,capture_output=True,text=True)
    if result.returncode:
        # Tool errors can echo connection details; don't expose arbitrary stderr.
        raise SystemExit(f'{Path(args[0]).name} failed (exit {result.returncode}). Check database access and tool versions.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    backup=sub.add_parser('backup');backup.add_argument('--directory',default=str(ROOT/'backups'))
    restore=sub.add_parser('restore');restore.add_argument('--archive',required=True);restore.add_argument('--target-database',required=True)
    args=parser.parse_args()
    url=make_url(os.environ.get('DATABASE_URL',''))
    if not url.drivername.startswith('postgresql'):
        raise SystemExit('Backups require PostgreSQL, not the SQLite test database.')
    env=os.environ.copy();env['PGPASSWORD']=url.password or '';env['PGCONNECT_TIMEOUT']='10'
    flags=['--host',url.host or 'localhost','--port',str(url.port or 5432),'--username',url.username or 'attendance']
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        raise SystemExit('Add PostgreSQL 17 bin directory to PATH (pg_dump and pg_restore required).')
    if args.command=='backup':
        target=Path(args.directory);target.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path=target/f'attendance-{stamp}.dump';partial=path.with_suffix('.partial')
        try:
            run(['pg_dump',*flags,'--dbname',url.database,'--format=custom','--file',str(partial)],env)
            run(['pg_restore','--list',str(partial)],env)
            partial.rename(path)
        finally:
            partial.unlink(missing_ok=True)
        print('Verified backup archive:',path)
    else:
        if args.target_database==url.database:
            raise SystemExit('Restore to a separate empty database; never overwrite the live database.')
        archive=Path(args.archive)
        if not archive.is_file():raise SystemExit('Backup archive not found.')
        with psycopg.connect(host=url.host or 'localhost',port=url.port or 5432,user=url.username,password=url.password,
                             dbname=args.target_database,connect_timeout=10) as connection:
            count=connection.execute("SELECT count(*) FROM pg_tables WHERE schemaname NOT LIKE 'pg_%' AND schemaname != 'information_schema'").fetchone()[0]
            if count:raise SystemExit('Restore target is not empty. Choose a new database.')
        run(['pg_restore',*flags,'--dbname',args.target_database,'--no-owner','--no-privileges','--exit-on-error','--single-transaction',str(archive)],env)
        print('Archive restored to separate database:',args.target_database)


if __name__=='__main__':main()
