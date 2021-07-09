import os
import pika
import json
import psycopg2
import urllib
import logging
import sys
import requests
from yoyo import read_migrations
from yoyo import get_backend

def get_module_logger(mod_name):
    logger = logging.getLogger(mod_name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s [%(name)-12s] %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel({
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'DEBUG': logging.DEBUG,
    }[os.getenv('LOG_LEVEL', 'WARNING')])
    return logger
logger = get_module_logger(__name__)

def enqueue_url(cur, url, force=False):
    if force:
        cur.execute('SELECT title, content FROM news WHERE url = %s', [url])
    else:
        cur.execute('SELECT title, content FROM news WHERE url = %s AND summary IS NULL', [url])
    res = cur.fetchone()
    if res is not None:
        title, content = res
        if not title or not content:
            return

        pika_connection = pika.BlockingConnection(pika.ConnectionParameters(host='news-queue'))
        channel = pika_connection.channel()
        channel.queue_declare(queue='summary_item', durable=True)
        channel.basic_publish(
            exchange='',
            routing_key='summary_item',
            body=json.dumps({
                'url': url,
                'title': title,
                'content': content,
            }),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=1,
            )
        )
        cur.execute('UPDATE news SET summary = %s WHERE url = %s', ['', url])

def enqueue_answerer(cur, url):
    cur.execute('SELECT title, content FROM news WHERE url = %s', [url])
    res = cur.fetchone()
    if not res:
        return
    title, content = res
    if not title or not content or '?' not in title:
        return
    pika_connection = pika.BlockingConnection(pika.ConnectionParameters(host='news-queue'))
    channel = pika_connection.channel()
    channel.queue_declare(queue='answer_item', durable=True)
    channel.basic_publish(
        exchange='',
        routing_key='answer_item',
        body=json.dumps({
            'url': url,
            'title': title,
            'content': content,
        }),
        properties=pika.BasicProperties(
            content_type='application/json',
            delivery_mode=1,
        )
    )

def enqueue_deduplicator(cur, url):
    cur.execute('SELECT title, source_id, date, canonical_url FROM news WHERE url = %s', [url])
    res = cur.fetchone()
    if not res:
        return
    title, source, date, canonical_url = res
    if canonical_url or not date or not source:
        return
    cur.execute('''
        SELECT COALESCE(canonical_url, url) AS url, title
        FROM news
        WHERE
            title IS NOT NULL AND
            source_id != %s AND
            date > %s - INTERVAL '1 DAY' AND
            date < %s
    ''', [source, date, date])
    alternatives = cur.fetchall()
    channel = pika_connection.channel()
    channel.queue_declare(queue='deduplicator_item', durable=True)
    channel.basic_publish(
        exchange='',
        routing_key='deduplicator_item',
        body=json.dumps({
            'url': url,
            'title': title,
            'alternatives': alternatives,
            'canonical_url': canonical_url,
        }),
        properties=pika.BasicProperties(
            content_type='application/json',
            delivery_mode=1,
        )
    )

def update_article(cur, obj):
    logger.info('updating article ' + obj['url'])
    cur.execute('''INSERT INTO news (url) VALUES (%s) ON CONFLICT DO NOTHING''', [obj['url']])
    changed = set()
    for k in 'section', 'source':
        if k in obj and obj[k]:
            cur.execute(f'''INSERT INTO {k} (name) VALUES (%s) ON CONFLICT DO NOTHING''', [obj[k]])
            cur.execute(f'''UPDATE news SET {k}_id = (SELECT id FROM {k} WHERE name = %s) WHERE url = %s AND ({k}_id IS NULL OR {k}_id != (SELECT id FROM {k} WHERE name = %s))''', [
                obj[k],
                obj['url'],
                obj[k],
            ])
            if cur.rowcount > 0:
                changed.add(k)

    changed_text = False
    for f in 'title', 'volanta', 'image', 'content', 'date', 'summary', 'canonical_url':
        if obj.get(f, None) is None:
            continue
        cur.execute(f'''UPDATE news SET {f} = %s WHERE url = %s AND ({f} IS NULL OR {f} != %s)''',
            [
                obj[f],
                obj['url'],
                obj[f],
            ]
        )
        if cur.rowcount > 0:
            changed.add(f)
    for f in ('answer',):
        if obj.get(f, None) is None:
            continue
        cur.execute('INSERT INTO answer (url, answer) VALUES (%s, %s) ON CONFLICT (url) DO UPDATE SET answer = %s', [obj['url'], obj['answer'], obj['answer']])

    if 'title' in changed or 'date' in changed or 'source' in changed:
        enqueue_deduplicator(cur, obj['url'])
    if 'title' in changed or 'content' in changed:
        enqueue_answerer(cur, obj['url'])
    enqueue_url(cur, obj['url'])

def update_homepage(cur, source, urls):
    logger.info(f'updating homepage for source {source} with {len(urls)} elements')
    cur.execute('SELECT id FROM source WHERE name = %s', [source])
    source_id = cur.fetchone()[0]
    cur.execute(f'''UPDATE news SET position = NULL WHERE source_id = %s''', [source_id])

    for i, url in enumerate(urls):
        cur.execute(f'''UPDATE news SET position = %s WHERE url = %s''', [i, url])


if __name__ == '__main__':
    pika_connection = pika.BlockingConnection(pika.ConnectionParameters(host='news-queue'))
    channel = pika_connection.channel()
    channel.queue_declare(queue='item', durable=True)

    pg_user = os.getenv("POSTGRES_USER")
    pg_host = 'news-database'
    pg_db = os.getenv("POSTGRES_DB")
    with open('/run/secrets/postgres-password', 'r') as fp:
        pg_password = fp.read().strip()
    dsn = f'postgres://{pg_user}:{urllib.parse.quote(pg_password)}@{pg_host}/{pg_db}'
    backend = get_backend(dsn)
    migrations = read_migrations(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations'))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
    pg_connection = psycopg2.connect(dsn)

    if len(sys.argv) == 2:
        cur = pg_connection.cursor()
        enqueue_url(cur, sys.argv[1], force=True)
        enqueue_deduplicator(cur, sys.argv[1])
        enqueue_answerer(cur, sys.argv[1])
        sys.exit(0)


    for method_frame, properties, body in channel.consume('item'):
        obj = json.loads(body.decode('utf-8'))
        cur = pg_connection.cursor()
        if 'url' in obj:
            update_article(cur, obj)
        elif 'homepage' in obj:
            update_homepage(cur, obj['source'], obj['homepage'])
            cur.execute('''DELETE FROM updated''')
            cur.execute('''INSERT INTO updated (time) VALUES (NOW())''')
        channel.basic_ack(method_frame.delivery_tag)
        pg_connection.commit()
