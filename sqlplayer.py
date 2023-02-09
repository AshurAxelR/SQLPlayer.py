import io
import json
import os.path
import re

from mysql.connector import connect
from mysql.connector import Error as SqlError

from jinja2 import Environment, FileSystemLoader
import cherrypy

SQLPLAYER_VERSION = '1.2 (Feb 2023)'
MAX_ROWS = 1000

def load_profiles() -> dict:
    with io.open('profiles.json') as f:
        return json.load(f)

def process_query(cfg, db, sql):
    with connect(
            host=cfg['host'],
            user=cfg['user'],
            password=cfg['pwd'],
            charset=cfg['names'],
            database=db
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            cols = [desc[0] for desc in (cursor.description or [])]
            rows = cursor.fetchall()
            connection.commit()
            total = cursor.rowcount
            if total>MAX_ROWS:
                rows = rows[:MAX_ROWS]
            return {
                'cols': cols,
                'rows': rows,
                'total': total,
                'len_rows': len(rows),
            }

class SqlPlayer(object):
    def __init__(self):
        self.tenv = Environment(
            loader=FileSystemLoader('template'),
            autoescape=True
        )

    @cherrypy.expose
    def index(self, db=None, profile=None, sql=None):
        profiles = load_profiles()
        profile_cfg = profiles.get(profile, None)
        if db and not re.match(r"^[A-Za-z0-9\-_]{1,64}$", db):
            db = None
        if not sql:
            sql = 'SELECT * FROM table'

        ctx = {
            'db': db,
            'profile': profile,
            'profile_list': profiles.keys(),
            'sql': sql,
            'version': SQLPLAYER_VERSION
        }

        ip = cherrypy.request.headers["Remote-Addr"]
        if not ip=='127.0.0.1':
            ctx['error'] = 'Not localhost'
        elif profile_cfg is None:
            if profile:
                ctx['error'] = 'Unknown host profile'
        else:
            try:
                ctx |= process_query(profile_cfg, db=db, sql=sql)
            except SqlError as e:
                ctx['error'] = str(e)

        template = self.tenv.get_template('index.html')
        return template.render(ctx)

if __name__ == '__main__':
    conf = {
        '/': {
            'tools.staticdir.root': os.path.abspath(os.getcwd())
        },
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': './static'
        }
    }
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 8080})
    cherrypy.quickstart(SqlPlayer(), '/', conf)
