from . import webcat, geo, prices
import pandas as pd
import aljpy
from pathlib import Path

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

def dataframe(listings):
    listings = (listings
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