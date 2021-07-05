import json
import re
import html
import traceback

import pika
from transformers import pipeline

sentiment_analysis = pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-emotion")
en_es_translator = pipeline("translation_en_to_es", model='Helsinki-NLP/opus-mt-en-es')
es_en_translator = pipeline("translation_es_to_en", model='Helsinki-NLP/opus-mt-es-en')
summarizer = pipeline("summarization")

def cleanhtml(raw_html):
  cleantext = re.sub('<.*?>', '', re.sub('</p.*?>', '\n', raw_html))
  return html.unescape(cleantext)

def es_en(text):
    lines_es = text.split('\n')
    lines_es = [x.strip() for x in lines_es]
    lines_es = [x for x in lines_es if x != '']
    if len(lines_es) == 0:
        return ''
    lines_es = [' '.join(x.split(' ')[:512]) for x in lines_es]
    lines_en = es_en_translator(lines_es)
    return '\n'.join(x['translation_text'] for x in lines_en)

def summary_line(line):
    MAX_SUMMARY = 40
    if len(line.split(' ')) < MAX_SUMMARY:
        return line
    else:
        return summarizer(' '.join(line.split(' ')[:1024]), min_length=0, max_length=MAX_SUMMARY)[0]['summary_text']

def summarize(text):
    lines_total = text.split('\n')
    lines_total = [x.strip() for x in lines_total]
    lines_total = [x for x in lines_total if x != '']
    if len(lines_total) == 0:
        return ''
    lines_summary = []

    text_summary = ' '.join([summary_line(line) for line in lines_total])
    return summary_line(text_summary)

def get_summary_and_sentiment(text):
    en = es_en(cleanhtml(text))
    summarized = summarize(en)
    es = en_es_translator(summarized)[0]['translation_text']
    sentiment = sentiment_analysis(summarized)[0]['label']
    s = {
        'LABEL_0': 1,
        'LABEL_1': 2,
        'LABEL_2': 3,
        'LABEL_3': 4,
    }.get(sentiment, 0)

    return ''.join(es), s

if __name__ == '__main__':
    pika_connection = pika.BlockingConnection(pika.ConnectionParameters(host='news-queue', heartbeat=600, blocked_connection_timeout=6000))
    channel = pika_connection.channel()
    channel.queue_declare(queue='summary_item', durable=True)
    for method_frame, properties, body in channel.consume('summary_item'):
        obj = json.loads(body.decode('utf-8'))
        try:
            summary, sentiment = get_summary_and_sentiment(obj['title'] + '\n' + obj['content'])
            channel.basic_publish(
                exchange='',
                routing_key='item',
                body=json.dumps({
                    'url': obj['url'],
                    'summary': summary,
                    'sentiment': sentiment,
                }),
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=1,
                )
            )
        except:
            traceback.print_exc()
        channel.basic_ack(method_frame.delivery_tag)