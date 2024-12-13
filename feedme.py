#!/usr/bin/env python
import sqlite3
import feedparser
import base64
from dateutil.parser import parse
from dateutil import tz
import tomli
from bs4 import BeautifulSoup
import os
import html
from datetime import datetime, timezone
import logging
import niquests

# Set up logging
logging.basicConfig(level=logging.DEBUG if os.getenv("DEBUG_LOGGING") == "1" else logging.INFO)
logger = logging.getLogger()

with open("config.toml", mode="rb") as fp:
    config = tomli.load(fp)

db_file = 'sqlite.db'

tzinfos = {
    'PDT': tz.gettz('America/Los_Angeles'),
    'PST': tz.gettz('America/Los_Angeles'),
    'EST': tz.gettz('America/New_York'),
    'EDT': tz.gettz('America/New_York'),
}

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
    try:
        response = niquests.get(url, timeout=30)
        feed = feedparser.parse(response.content)
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return  # Exit the function if there's an error
    for post in feed.entries:
        title = post.title
        title_encoded = summary_encoded = base64.b64encode(title.encode("utf-8")).decode()
        link_raw = post.link
        link = html.escape(link_raw)
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
            logger.debug(f"Inserting article: {sql}")
            cursor.execute(sql)
            conn.commit()

def read_feeds():
    '''Process all the feeds in feeds.txt.'''
    logger.debug("Reading feeds from feeds.txt")
    with open("feeds.txt", "r") as file:
        for url in file:
            logger.debug(f"Processing URL: {url.strip()}")
            process_rss(url.strip())


def build_page():
    '''Generate the aggregated page.'''
    # read the header template
    with open('header.tmpl', 'r') as file:
        base_head = file.read()
    all_content = base_head
    dt_now = datetime.now(timezone.utc).strftime("%Y/%m/%d, %H:%M:%S %Z")
    all_content += f"Last updated: {dt_now} (updates every 4 hours)<br><hr>"
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
            print_string += f"""<h3><a href=\"{link}\" target=\"_blank\">{title.strip()}</a></h3>\n
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
    logger.info("Starting feed generation...")
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
    logger.info("Finished feed generation.")
