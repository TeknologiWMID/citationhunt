import chdb
import config
import database
from utils import *
from common import *

import collections
import datetime
import urllib
import urlparse

Category = collections.namedtuple('Category', ['id', 'title'])
CATEGORY_ALL = Category('all', '')

def get_category_by_id(lang_code, cat_id):
    if cat_id == CATEGORY_ALL.id:
        return CATEGORY_ALL
    c = database.query_category_by_id(lang_code, cat_id)
    return Category(*c) if c is not None else None

def select_random_id(lang_code, cat = CATEGORY_ALL):
    ret = None
    if cat is not CATEGORY_ALL:
        ret = database.query_snippet_by_category(lang_code, cat.id)

    if ret is None:
        # Try to pick one id at random. For small datasets, the probability
        # of getting an empty set in a query is non-negligible, so retry a
        # bunch of times as needed.
        with log_time('select without category'):
            for retry in range(1000):
                ret = database.query_random_snippet(lang_code)
                if ret: break

    assert ret and len(ret) == 1
    return ret[0]

def select_next_id(lang_code, curr_id, cat = CATEGORY_ALL):
    if cat is not CATEGORY_ALL:
        ret = database.query_next_id(lang_code, curr_id, cat.id)
        if ret is None:
            # curr_id doesn't belong to the category
            return None
        assert ret and len(ret) == 1
        next_id = ret[0]
    else:
        next_id = curr_id
        for i in range(3): # super paranoid :)
            next_id = select_random_id(lang_code, cat)
            if next_id != curr_id:
                break
    return next_id

@validate_lang_code
def citation_hunt(lang_code):
    id = flask.request.args.get('id')
    cat = flask.request.args.get('cat')
    cfg = flask.g._cfg
    strings = flask.g._strings

    lang_dir = cfg.lang_dir
    if flask.current_app.debug:
        lang_dir = flask.request.args.get('dir', lang_dir)

    if cat is not None:
        cat = get_category_by_id(lang_code, cat)
        if cat is None:
            # invalid category, normalize to "all" and try again by id
            cat = CATEGORY_ALL
            return flask.redirect(
                flask.url_for('citation_hunt',
                    lang_code = lang_code, id = id, cat = cat.id))
    else:
        cat = CATEGORY_ALL

    if id is not None:
        sinfo = database.query_snippet_by_id(lang_code, id)
        if sinfo is None:
            # invalid id
            flask.abort(404)
        snippet, section, aurl, atitle = sinfo
        snippet = flask.Markup(snippet)
        next_snippet_id = select_next_id(lang_code, id, cat)
        if next_snippet_id is None:
            # the snippet doesn't belong to the category!
            assert cat is not CATEGORY_ALL
            return flask.redirect(
                flask.url_for('citation_hunt',
                    id = id, cat = CATEGORY_ALL.id,
                    lang_code = lang_code))
        article_url_path = urllib.quote(
            e(urlparse.urlparse(aurl).path.lstrip('/')))
        return flask.render_template('index.html',
            snippet_id = id, snippet = snippet,
            section = section, article_url = aurl,
            article_url_path = article_url_path,
            article_title = atitle, current_category = cat,
            next_snippet_id = next_snippet_id,
            config = cfg,
            lang_tag = flask.g._lang_tag,
            lang_dir = lang_dir,
            lang_code = lang_code,
            strings = strings,
            js_strings = strings['js'])

    id = select_random_id(lang_code, cat)
    return flask.redirect(
        flask.url_for('citation_hunt',
            id = id, cat = cat.id, lang_code = lang_code))

@validate_lang_code
def search_category(lang_code):
    try:
        max_results = int(flask.request.args.get('max_results'))
    except:
        max_results = float('inf')
    return flask.jsonify(
        results = database.search_category(
            lang_code, flask.request.args.get('q'),
            max_results = min(max_results, 400)))

@validate_lang_code
def fixed(lang_code):
    from_ts = flask.request.args.get('from_ts', None)
    try:
        from_ts = datetime.datetime.fromtimestamp(float(from_ts))
    except:
        # Technically an invalid request, but let's just normalize below
        from_ts = None
        pass
    now = datetime.datetime.today()
    max_delta = datetime.timedelta(hours = 24)
    if from_ts is None or abs(now - from_ts) > max_delta:
        from_ts = now - max_delta
    return flask.make_response(
        str(database.query_fixed_snippets(lang_code, from_ts)), 200)
