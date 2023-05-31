#!/usr/bin/env python
import sqlite3
import feedparser
import base64
from dateutil.parser import parse
from dateutil import tz
import tomli
from bs4 import BeautifulSoup
import os
from datetime import datetime, timezone

with open("config.toml", mode="rb") as fp:
    config = tomli.load(fp)

db_file = 'sqlite.db'

tzinfos = {'PDT': tz.gettz('America/Los_Angeles')}

def cleanup(files):
    '''Remove intermediate database files.'''
    if os.path.isfile(db_file):
        os.remove(db_file)
    if files == "all":
        if os.path.isfile(config["html_output"]):
            os.remove(config["html_output"])

def truncate_html(html, length): 
    '''Truncate strings while still maintaining (and terminating) html.'''
    return str(BeautifulSoup(html[:length], "html.parser"))

def process_rss(url):
    '''Gather posts from RSS feed and put them into sqlite.'''
    feed = feedparser.parse(url)
    for post in feed.entries:
        title = post.title
        title_encoded = summary_encoded = base64.b64encode(title.encode("utf-8")).decode()
        link = post.link
        summary = post.summary
        summary_encoded = base64.b64encode(summary.encode("utf-8")).decode()
        parsed_date = parse(post.published, tzinfos=tzinfos)
        # exclude duplicates
        check_sql = f"select * from articles where title = \"{title_encoded}\""
        cursor.execute(check_sql)
        row = cursor.fetchall() 
        if not row:
            sql = f'''insert into articles 
            (summary, title, link, published) 
            values 
            ('{summary_encoded}', '{title_encoded}', '{link}', '{parsed_date}')'''
            cursor.execute(sql)
            conn.commit()

def read_feeds():
    '''Process all the feeds in feeds.txt.'''
    with open("feeds.txt", "r") as file:
        for url in file:
            process_rss(url.strip())


def build_page():
    '''Generate the aggregated page.'''
    # read the header template
    with open('header.tmpl', 'r') as file:
        base_head = file.read()
    all_content = base_head
    dt_now = datetime.now(timezone.utc).strftime("%Y/%m/%d, %H:%M:%S %Z")
    all_content += f"Last updated: {dt_now}<br><hr>"
    # select the latest 100 posts and write them to the body
    query = f'SELECT title, link, summary, published FROM articles ORDER BY datetime(published) DESC LIMIT {config["max_posts"]}'
    cursor.execute(query)
    row = cursor.fetchall()
    base_body = ""
    if row:
        for r in row:
            END = -1
            print_string = ""
            title = base64.b64decode(r[0]).decode()
            link = r[1]
            summary = base64.b64decode(r[2]).decode()
            if len(summary) > config["max_summary_size"]:
                summary = truncate_html(summary, config["max_summary_size"])
                summary = f"{summary} [...]"
            published = r[3]
            print_string += f"""<h2><a href=\"{link}\" target=\"_blank\">{title.strip()}</a></h2>\n
            <b>Published:</b> {published}<p>
            <b>Summary:</b><br>
            {summary.strip()}<br>
            <hr><p>"""
            base_body += print_string.strip()
    all_content += base_body
    # read the footer template
    with open('footer.tmpl', 'r') as file:
        base_foot = file.read()
    all_content += base_foot
    return all_content

if __name__ == '__main__':
    print("Starting feed generation...")
    cleanup("all")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    sql = '''CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                published TEXT NOT NULL
            )'''
    cursor.execute(sql)
    read_feeds()
    output_file = open(config["html_output"], "w")
    contents = build_page()
    output_file.write(contents)
    output_file.close()
    cursor.close()
    conn.close()
    conn.close()
    cleanup("db")
    print("Finished feed generation.")
