from jinja2 import Template
from flask import Flask, jsonify, make_response
from . import zoopla, webcat, geo, dataframe
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

def decision_dataframe():
    df = zoopla.load_dataframe()
    df['decision'] = pd.Series(decisions()).reindex(df.listing_id.values).fillna('').values
    return df

def render(decision, buttons):
    df = decision_dataframe()
    df = df[df.decision == ''] if decision == 'all' else df[df.decision == decision]
    template = Template(resource_string(__package__, 'index.j2').decode())
    return template.render(df=df.to_dict(orient='index'), buttons=buttons, decision=decision)
    
@app.route('/')
def index():
    return render(decision='all', buttons=True)

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
    layers = dataframe.map_layers()
    common = set(cuts) & set(layers)
    return geo.reproject(base, *[geo.threshold(layers[name], cuts[name]) for name in common]).all(0).astype(float)

def _bigmap(decision='all', df=None):
    df = decision_dataframe() if df is None else df

    base = webcat.basemap()
    combo = _combomap(dataframe.CUTS)

    fig = mpl.figure.Figure(dpi=100, figsize=(6.4, 6.4))
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.Mercator.GOOGLE, frameon=False)

    if decision == 'all':
        sub = df[df.decision != ''].copy()
    else:
        sub = df[df.decision == decision]

    sub['color'] = sub.decision.map({'bad': -2, 'meh': -1, 'good': +1, 'great': +2, 'booked': +2, 'dead': +2})
    sub = sub.sort_values('color')
    ax.scatter(sub.longitude, sub.latitude, transform=ccrs.PlateCarree(), marker='.', s=100, c=sub.color, vmin=-2, vmax=+2, cmap='RdYlGn')

    rest = df[~df.index.isin(sub.index)]
    ax.scatter(rest.longitude, rest.latitude, transform=ccrs.PlateCarree(), marker='.', s=5, color='k', alpha=.5)
    xs, ys = ax.get_xlim(), ax.get_ylim()

    ax.imshow(**base, alpha=.5)
    ax.imshow(**{**base, 'img': combo}, cmap='Greys_r', alpha=.5)
    ax.set_xlim(xs), ax.set_ylim(ys)

    return ax.figure
    
@app.route('/bigmap/<decision>')
def bigmap(decision):
    bs = BytesIO()
    _bigmap(decision).savefig(bs, format='png')
    r = make_response(bs.getvalue())
    r.headers.set('Content-Type', 'image/png')
    return r
