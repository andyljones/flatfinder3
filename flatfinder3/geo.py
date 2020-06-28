import cartopy.crs as ccrs
from shapely.geometry import MultiPoint
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from zipfile import ZipFile
import tempfile
import shapely
import rasterio.transform
import rasterio.features
import scipy.ndimage
import requests
from io import BytesIO
import aljpy
from . import webcat
import json
from pathlib import Path

locations = Path('locations.json')
if locations.exists():
    LOCATIONS = json.loads(locations.read_text())
else:
    LOCATIONS = {}

def as_indices(coords, img, extent, **kwargs):
    """Coords should be (lat, lon)"""
    h, w = img.shape[:2]
    x1, x2, y1, y2 = extent

    proj = np.array(ccrs.Mercator.GOOGLE.project_geometry(MultiPoint(coords[..., ::-1])))

    # Measured from bottom cause the origin's always 'lower'
    j = (w*(proj[:, 0] - x1)/(x2 - x1))
    i = (h*(proj[:, 1] - y1)/(y2 - y1))

    indices = np.stack([i, j], -1).astype(int)

    return indices

def lookup(listings, mapdata, interval=5):

    coords = np.stack([listings['latitude'], listings['longitude']], -1)
    indices = as_indices(coords, **mapdata)

    h, w = mapdata['img'].shape[:2]
    b = mapdata['img'][indices[:, 0].clip(0, h-1), indices[:, 1].clip(0, w-1)]
    b[(indices[:, 0] < 0) | (indices[:, 0] >= h)] = np.nan
    b[(indices[:, 1] < 0) | (indices[:, 1] >= w)] = np.nan

    return b

def transform(mapdata):
    shape = mapdata['img'].shape[:2]
    w, e, s, n = mapdata['extent']
    t = rasterio.transform.from_bounds(w, s, e, n, *shape)
    return t, shape

def distances(base, shp):
    t, shape = transform(base)

    # Flip it because rasterio expects a top origin
    img = rasterio.features.rasterize([shp], out_shape=shape, transform=t)[::-1]

    # Hand-calculated this scale. Should calculate it explicitly really.
    dist = 22*scipy.ndimage.distance_transform_edt(1 - img)
    time = dist/(60*1.5)

    return {'img': time, 'extent': base['extent'], 'origin': base['origin']}

@aljpy.autocache('')
def green_spaces(base, width=250):
    """From: https://geospatialwandering.wordpress.com/2015/05/22/open-spaces-shapefile-for-london """

    url = 'http://download1648.mediafire.com/uagkonyt1k3g/uvvwp9hjiatqyss/Green+spaces+London.zip'
    r = requests.get(url)
    with ZipFile(BytesIO(r.content)) as zf, \
            tempfile.TemporaryDirectory() as tmp:
        zf.extractall(tmp)
        shp = gpd.read_file(tmp + '/Green spaces London/Green_spaces_excluding_private.shp')

    shp = shp.geometry[shp.geometry.area > width**2]
    shp = shapely.ops.unary_union(shp.to_crs(ccrs.Mercator.GOOGLE.proj4_params))
    return distances(base, shp)

@aljpy.autocache()
def _town_centers():
    url = "https://data.london.gov.uk/download/town-centre-locations/50e12a40-90c4-4a46-af20-9891d1441a5c/LP_2016_town_centre_points.zip"
    r = requests.get(url)
    with ZipFile(BytesIO(r.content)) as zf, \
            tempfile.TemporaryDirectory() as tmp:
        zf.extractall(tmp)
        shp = gpd.read_file(tmp + '/LP_2016_town_centre_points.shp')
    return shp

@aljpy.autocache('')
def town_centers(base):
    shp = _town_centers()
    shp = shp[shp['Classifi_1'].isin(['International', 'Metropolitan', 'Major', 'District'])]
    shp = shp.geometry.to_crs(ccrs.Mercator.GOOGLE.proj4_params)
    shp = shapely.ops.unary_union(shp)
    return distances(base, shp)

def reproject(ref, *mapdata):
    dst_transform, dst_shape = transform(ref)
    crs = ccrs.Mercator.GOOGLE.proj4_params
    dsts = []
    for m in mapdata:
        src_transform, _ = transform(m)
        dst = np.zeros(dst_shape)
        rasterio.warp.reproject(m['img'], dst, 
            src_transform=src_transform, dst_transform=dst_transform,
            src_crs=crs, dst_crs=crs)
        dsts.append(dst)
    return np.stack(dsts)

def threshold(mapdata, t):
    return {**mapdata, 'img': (mapdata['img'] < t).astype(float)}

def aggtim(targets, method, interval=5):
    layers = [webcat.timmap(tuple(target), interval=interval) for target in targets]
    stack = reproject(*layers)
    return {**layers[0], 'img': getattr(stack, method)(0)}
    
