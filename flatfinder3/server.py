from jinja2 import Template
from flask import Flask, jsonify, make_response
from . import zoopla, webcat, geo, prices
from pkg_resources import resource_string
import pandas as pd
import aljpy
import numpy as np
from cartopy import crs as ccrs
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib as mpl
import json
from pathlib import Path

app = Flask(__name__)

DECISIONS = Path('data/decisions.json')

CUTS = {
    'park': 10,
    'town': 10,
    'propvalue': 10000,
    'friends': 45,
    'aerial': 30,
    'central': 60}

@aljpy.autocache(disk=False, memory=True)
def map_layers():
    base = webcat.basemap()
    maps = aljpy.dotdict({
        'park': geo.green_spaces(base), 
        'town': geo.town_centers(base),
        'propvalue': prices.layer(base)})

    if geo.LOCATIONS:
        maps.update({
            'aerial': geo.aggtim(geo.LOCATIONS['aerial'].values(), 'min'), 
            'central': geo.aggtim(geo.LOCATIONS['central'].values(), 'mean', interval=10), 
            'friends': geo.aggtim(geo.LOCATIONS['friends'].values(), 'mean', interval=10)})

    return maps

@aljpy.autocache(disk=False, memory=True, duration=600)
def dataframe():
    print('Generating dataframe')

    listings = (zoopla.listings()
            .loc[lambda df: df['num_bedrooms'] == 1]
            .loc[lambda df: df['num_bathrooms'] == 1]
            .loc[lambda df: df['rental_prices.per_month'] <= 1500]
            .loc[lambda df: df['rental_prices.shared_occupancy'] == 'N']
            .loc[lambda df: df['furnished_state'] == 'furnished']).copy()
    for k, m in map_layers().items():
        listings[k] = geo.lookup(listings, m)

    df = listings
    for k, c in CUTS.items():
        if k in df:
            df = df.loc[df[k] <= c]
    df = df.copy()

    df['nickname'] = df.listing_id.apply(aljpy.humanhash, n=2)
    df['published'] = pd.to_datetime(df.last_published_date).dt.strftime('%a %-I:%M%p')
    df = df.sort_values('last_published_date', ascending=False)
        
    return df

def decision_dataframe():
    df = dataframe()
    df['decision'] = pd.Series(decisions()).reindex(df.listing_id.values).fillna('').values
    return df

def render(decision, buttons):
    df = decision_dataframe()
    df = df[df.decision == decision]
    template = Template(resource_string(__package__, 'index.j2').decode())
    return template.render(df=df.to_dict(orient='index'), buttons=buttons)
    
@app.route('/')
def index():
    return render(decision='', buttons=True)

@app.route('/decision/<decision>')
def saved(decision):
    return render(decision=decision, buttons=False)

@app.route('/ignored')
def ignored():
    return render(decision='ignore', buttons=False)
    
@app.route('/photos/<lid>')
def photos(lid):
    return jsonify(zoopla.photo_filenames(lid))

@app.route('/photo/<lid>/<filename>')
def photo(lid, filename):
    r = make_response(zoopla.photo(lid, filename))
    ext = filename.split('.')[-1]
    r.headers.set('Content-Type', f'image/{ext}')
    return r

@aljpy.autocache()
def _map(lat, lon, width=10):
    y_km = 6400*2*np.pi/360
    x_km = 6400*2*np.pi/360*np.cos(np.pi/180*lat)
    xw = width/(2*x_km)
    yw = width/(2*y_km)

    fig = mpl.figure.Figure(dpi=100, figsize=(4.3, 4.3))
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.Mercator.GOOGLE, frameon=False)

    ax.imshow(**webcat.basemap())
    ax.set_extent((lon-xw, lon+xw, lat-yw, lat+yw))
    ax.scatter([lon], [lat], transform=ccrs.PlateCarree(), color='r')

    bs = BytesIO()
    fig.savefig(bs, format='png')
    return bs.getvalue()

@app.route('/map/<lat>/<lon>')
def map(lat, lon):
    r = make_response(_map(float(lat), float(lon)))
    r.headers.set('Content-Type', 'image/png')
    return r

def decisions():
    if not DECISIONS.exists():
        DECISIONS.parent.mkdir(exist_ok=True, parents=True)
        DECISIONS.write_text('{}')
    return json.loads(DECISIONS.read_text())

@app.route('/decide/<lid>/<decision>')
def decide(lid, decision):
    ds = decisions()
    ds[lid] = decision
    DECISIONS.write_text(json.dumps(ds))
    return ''

@app.route('/decide/<lid>/')
def reset(lid):
    ds = decisions()
    del ds[lid]
    DECISIONS.write_text(json.dumps(ds))
    return ''

@aljpy.autocache('{cuts}')
def _combomap(cuts):
    base = webcat.basemap()
    layers = map_layers()
    common = set(cuts) & set(layers)
    return geo.reproject(base, *[geo.threshold(layers[name], cuts[name]) for name in common]).all(0).astype(float)

def _bigmap():
    df = decision_dataframe()

    base = webcat.basemap()
    combo = _combomap(CUTS)

    fig = mpl.figure.Figure(dpi=100, figsize=(6.4, 6.4))
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.Mercator.GOOGLE, frameon=False)

    sub = df[df.decision != '']
    color = sub.decision.map({'bad': 'r', 'meh': 'y', 'good': 'b', 'great': 'g'})
    ax.scatter(sub.longitude, sub.latitude, transform=ccrs.PlateCarree(), marker='.', s=50, c=color, alpha=.5)
    xs, ys = ax.get_xlim(), ax.get_ylim()

    rest = df[~df.index.isin(sub.index)]
    ax.scatter(rest.longitude, rest.latitude, transform=ccrs.PlateCarree(), marker='.', s=10, color='k', alpha=.5)

    ax.imshow(**base, alpha=.5)
    ax.imshow(**{**base, 'img': combo}, cmap='Greys_r', alpha=.5)
    ax.set_xlim(xs), ax.set_ylim(ys)

    return ax.figure
    
@app.route('/bigmap')
def bigmap():
    bs = BytesIO()
    _bigmap().savefig(bs, format='png')
    r = make_response(bs.getvalue())
    r.headers.set('Content-Type', 'image/png')
    return r
