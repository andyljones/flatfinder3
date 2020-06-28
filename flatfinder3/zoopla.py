"""Docs: https://developer.zoopla.co.uk/docs/read/Property_listings"""
import pandas as pd
import time
import json
import requests
from pathlib import Path
from .webcat import LONDON
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

def listing_dir(lid):
    return (CACHE / 'listings' / lid[:3] / lid[:6])

def add_listing(listing):
    lid = listing['listing_id']
    path = (listing_dir(lid) / lid).with_suffix('.json')    
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(listing))

def listings():
    data = []
    for p in (CACHE / 'listings').glob('**/*.json'):
        data.append(json.loads(p.read_text()))
    return pd.io.json.json_normalize(data)

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

    for listing in raw['listing']:
        listing['grid_index'] = grid_idx
        add_listing(listing)

    earliest = min(l['last_published_date'] for l in raw['listing'])
    done = raw['result_count'] <= page*PARAMS['page_size']
    return pd.Timestamp(earliest), done

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
                print(f'Failed while fetching page {page} of index {i}')
                time.sleep(API_WINDOW/(API_LIMIT - 10))
            else:
                print(f'Fetched page {page} of index {i}, back until {earliest}')
                time.sleep(API_WINDOW/(API_LIMIT - 10))
                if done:
                    print(f'Fetched all listings of index {i}')
                    break
                if pd.Timestamp(earliest) < latest:
                    print(f'Fetched all recent listings of index {i}')
                    break

                page = page + 1
                if page == 100:
                    print(f'Ran out of pages on index {i}')
                    break

def photo(lid, filename):
    url = f'https://lid.zoocdn.com/645/430/{filename}'
    path = listing_dir(lid) / lid / filename
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