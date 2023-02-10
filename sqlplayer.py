import io
import json
import os.path
import re
import fnmatch

from jinja2 import Environment, FileSystemLoader
import cherrypy


SQLPLAYER_VERSION = '1.2 (Feb 2023)'
MAX_ROWS = 1000


def load_profiles() -> dict:
    with io.open('profiles.json') as f:
        return json.load(f)


def check_ip(ip, allowed=None, cfg=None):
    if cfg is not None:
        allowed = cfg.get('allowed', None)
    if allowed is None:
        allowed = ['127.0.0.1']
    elif type(allowed) is str:
        allowed = [allowed]

    for a in allowed:
        if fnmatch.fnmatch(ip, a):
            return True
    return False


def mysql_query(cfg, db, sql):
    try:
        from mysql.connector import connect
        from mysql.connector import Error
        try:
            with connect(
                    host=cfg.get('host', '127.0.0.1'),
                    port=cfg.get('port', 3306),
                    user=cfg.get('user', 'root'),
                    password=cfg.get('pwd', ''),
                    charset=cfg.get('names', 'utf8'),
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
        except Error as e:
            return {'error': str(e)}
    except ImportError:
        return {'error': 'mysql-connector not installed on the server.'}


def postgres_query(cfg, db, sql):
    try:
        from psycopg2 import connect
        from psycopg2 import Error
        try:
            with connect(
                    host=cfg.get('host', '127.0.0.1'),
                    port=cfg.get('port', 5432),
                    user=cfg.get('user', 'root'),
                    password=cfg.get('pwd', ''),
                    database=db
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    cols = [desc[0] for desc in (cursor.description or [])]
                    rows = cursor.fetchall() if cols else []
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
        except Error as e:
            return {'error': str(e)}
    except ImportError:
        return {'error': 'psycopg2 not installed on the server.'}


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
        if not check_ip(ip, cfg=profile_cfg):
            ctx['error'] = f"IP not allowed: {ip}"
        elif profile_cfg is None:
            if profile:
                ctx['error'] = 'Unknown host profile'
        else:
            engine = profile_cfg.get('engine', 'mysql')
            if engine=='mysql':
                ctx |= mysql_query(profile_cfg, db=db, sql=sql)
            elif engine=='postgres':
                ctx |= postgres_query(profile_cfg, db=db, sql=sql)
            else:
                ctx['error'] = f"Unknown database engine: {engine}"

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
