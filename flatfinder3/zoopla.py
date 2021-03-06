"""Docs: https://developer.zoopla.co.uk/docs/read/Property_listings"""
import pandas as pd
import time
import json
import requests
from pathlib import Path
from .webcat import LONDON
from . import dataframe
import numpy as np
from bs4 import BeautifulSoup
import aljpy

WEEKS_PER_MONTH = 365/12./7

API_WINDOW = 60*60#seconds
API_LIMIT = 100
GRID_RES = 6

PARAMS = {
    'order_by': 'age',
    'ordering': 'descending',
    'listing_status': 'rent',
    'furnished': 'furnished',
    'page_size': 100,
    'summarised': True,
    'api_key': json.load(open('credentials.json'))['zoopla_key']      
}

CACHE = Path('.cache/zoopla')

ZOOPLA_URL = 'http://api.zoopla.co.uk/api/v1/property_listings.js'

def throttle():
    cache = CACHE / 'zoopla-calls.json'
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r'[]')
    while True:
        calls = json.loads(cache.read_text())
        recent = [c for c in calls if time.time() - c < API_WINDOW]
        if (len(recent) < API_LIMIT):
            break
        time.sleep(1)
    recent.append(time.time())
    cache.write_text(json.dumps(recent))

def listings():
    path = CACHE / 'listings.json'
    if not path.exists():
        return pd.DataFrame()
    data = json.loads(path.read_text())
    return pd.json_normalize(data.values())

def grid_center(i):
    x1, x2, y1, y2 = LONDON

    xd = (x2 - x1)/GRID_RES
    xs = np.arange(x1 + xd/2, x2, xd)

    yd = (y2 - y1)/GRID_RES
    ys = np.arange(y1 + yd/2, y2, yd)

    centers = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)

    y_km = 6400*2*np.pi/360*yd
    x_km = 6400*2*np.pi/360*np.cos(np.pi/180*(y1 + y2)/2)*xd
    rad = (y_km**2 + x_km**2)**.5 / 2 / 1.6 * 1.05 # Overdo it a bit

    return centers[i], rad

def search_page(grid_idx, page=0):
    throttle()
    center, rad = grid_center(grid_idx)
    params = {'longitude': center[0], 'latitude': center[1], 'radius': rad}
    r = requests.get(ZOOPLA_URL, {**PARAMS, **params, 'page_number': page})
    r.raise_for_status()
    raw = json.loads(r.content)

    path = CACHE / 'listings.json'
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_text('{}')
    cache = json.loads(path.read_text())
    for listing in raw['listing']:
        listing['grid_index'] = grid_idx
        cache[listing['listing_id']] = listing
    path.with_suffix('.tmp').write_text(json.dumps(cache))
    path.with_suffix('.tmp').rename(path)

    earliest = pd.Timestamp(min(l['last_published_date'] for l in raw['listing']))
    latest = pd.Timestamp(max(l['last_published_date'] for l in raw['listing']))
    print(f'{grid_idx}/{page}: covered {earliest} to {latest}')

    done = raw['result_count'] <= page*PARAMS['page_size']
    return earliest, done

def cache_dataframe():
    ls = listings()
    df = dataframe.dataframe(ls)
    cache = CACHE / 'dataframe.pkl'
    if not cache.parent.exists():
        cache.parent.mkdir(exist_ok=True, parents=True)
    pd.to_pickle(df, cache)

@aljpy.autocache(disk=False, memory=True, duration=600)
def load_dataframe():
    cache = CACHE / 'dataframe.pkl'
    return pd.read_pickle(cache)

def search():
    for i in range(GRID_RES**2):
        page = 1
        ls = listings()
        latest = pd.Timestamp('2020-05-01')
        if ls.size:
            ls = ls.loc[lambda df: df.grid_index == i]
            if ls.size:
                latest = pd.Timestamp(ls.last_published_date.max())

        while True:
            try:
                earliest, done = search_page(i, page)
            except:
                print(f'{i}: failed, retrying')
            else:
                time.sleep(1)
                if done:
                    print(f'{i}: fetched all listings')
                    break
                if pd.Timestamp(earliest) < latest:
                    print(f'{i}: fetched all recent listings')
                    break

                page = page + 1
                if page == 100:
                    print(f'{i}: ran out of pages')
                    break
            
def loop():
    print('Started')
    nxt = time.time()
    while True:
        if time.time() > nxt:
            search()

            print('Caching dataframe')
            cache_dataframe()

            print('Sleeping for six hours before the next search')
            nxt = time.time() + 6*3600
        time.sleep(15)

def photo(lid, filename):
    url = f'https://lid.zoocdn.com/645/430/{filename}'
    path = CACHE / 'photos' / lid / filename
    if not path.exists():
        if not path.parent.exists():
            path.parent.mkdir(exist_ok=True, parents=True)
        r = requests.get(url)
        if r.status_code == 200:
            path.write_bytes(r.content)
        else:
            print(f'Couldn\'t fetch {url}')
            path.write_bytes(b'')        
    return path.read_bytes()

@aljpy.autocache()
def photo_filenames(lid):
    r = requests.get(f'https://www.zoopla.co.uk/to-rent/details/{lid}')
    soup = BeautifulSoup(r.content, features='html5lib')
    return [t.attrs['src'].split('/')[-1] for t in soup.select(".dp-gallery__image")]