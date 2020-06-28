import requests
import mapbox_vector_tile
import json
import pandas as pd
import geopandas as gpd
from io import BytesIO
import aljpy
import rasterio.features
import scipy.ndimage
from cartopy import crs as ccrs
from . import geo

@aljpy.autocache()
def prices():
    """From: https://houseprices.anna.ps/"""
    url = 'https://b.tiles.mapbox.com/v4/annapowellsmith.2kq8mrxg/{z}/{x}/{y}.vector.pbf?access_token=pk.eyJ1Ijoid2hvb3duc2VuZ2xhbmQiLCJhIjoiY2l6ZDcwNW1uMDAzdjMyb3llczN6bDh6ZyJ9.laaDJGqsBHQLIZRy9dWlxA'
    tiles = []
    for x in [254, 255, 256]:
        for y in [169, 170]:
            r = requests.get(url.format(z=9, x=x, y=y))
            if r.status_code == 200:
                tiles.append(mapbox_vector_tile.decode(r.content))

    props = []
    for t in tiles: 
        for f in t['postcode_sectors_englandgeojson']['features']:
            props.append(f['properties'])
    return pd.DataFrame(props)

@aljpy.autocache()
def shapes():
    """Districts from: https://www.opendoorlogistics.com/downloads/"""
    url = 'https://www.opendoorlogistics.com/wp-content/uploads/Data/UK-postcode-boundaries-Jan-2015-topojson/Districts.json'
    r = requests.get(url)
    return gpd.read_file(BytesIO(r.content)).set_index('name').drop('id', 1)

def data():
    return shapes().merge(prices().groupby('PostDist').first(), left_index=True, right_index=True)

@aljpy.autocache('')
def layer(base):
    t, shape = geo.transform(base)

    # Guess at the CRS
    d = data().set_crs('epsg:4326').to_crs(ccrs.Mercator.GOOGLE.proj4_params)

    # Flip it because rasterio expects a top origin
    img = rasterio.features.rasterize([(r.geometry, r.price_by_postcode_district_price_per_sq_m) for _, r in d.iterrows()], out_shape=shape, transform=t)[::-1]

    # Replace the boundaries - which are a mix of colors - with the nearest solid color
    while (img == 0).any():
        dilated = scipy.ndimage.grey_dilation(img, size=3)
        img[img == 0] = dilated[img == 0]
    
    return {**base, 'img': img}