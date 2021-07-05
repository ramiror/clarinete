import os
import psycopg2
import psycopg2.extras
import urllib
from flask import Flask, jsonify, request, g
from waitress import serve


def get_db():
    pg_user = os.getenv("POSTGRES_USER")
    pg_host = 'news-database'
    pg_db = os.getenv("POSTGRES_DB")
    with open('/run/secrets/postgres-password', 'r') as fp:
        pg_password = fp.read().strip()
    dsn = f'postgres://{pg_user}:{urllib.parse.quote(pg_password)}@{pg_host}/{pg_db}'

    if 'db' not in g:
        g.db = pg_connection = psycopg2.connect(dsn)
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

app = Flask(__name__)
app.teardown_appcontext(close_db)

@app.route("/api/last_updated")
def last_updated():
    con = get_db()
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''SELECT MAX(time) AS time FROM updated''')
    return jsonify(cur.fetchone())

@app.route("/api/news")
def news_list():
    con = get_db()
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT url, title, volanta, section.name AS section, date, source.name AS source, sentiment, summary
        FROM news
            JOIN section ON news.section_id = section.id
            JOIN source ON news.source_id = source.id
        WHERE position IS NOT NULL
        ORDER BY position ASC''')
    return jsonify(cur.fetchall())

@app.route("/api/news/details")
def news_details():
    con = get_db()
    url = request.args.get('url')
    if not url:
        return 400, ''
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT url, title, volanta, section.name AS section, date, content, source.name AS source, summary, sentiment
        FROM news
            JOIN section ON news.section_id = section.id
            JOIN source ON news.source_id = source.id
        WHERE url = %s''', [url])
    row = cur.fetchone()
    if not url:
        return 404, ''
    return jsonify(row)

if __name__ == '__main__':
    if os.getenv('FLASK_DEBUG', False):
        app.run('0.0.0.0', debug=True)
    else:
        serve(app, host='0.0.0.0', port=5000)
