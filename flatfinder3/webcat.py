import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import scipy.ndimage
from cartopy.io.img_tiles import GoogleWTS, OSM
import urllib.parse
import aljpy
from cartopy import crs as ccrs
import requests

# ((bot, left), (top, right))
LONDON = (-.489, .236, 51.28, 51.686)
PARAMS = dict(
    scenarioTitle='Base Year',
    timeOfDayId='INTER',
    modeId='All',)
COLORS = ['#460000', '#ED1C24', '#F26522', '#FFF200', '#8DC73F', '#1C9959', '#00AEEF', '#0054A6', '#8686BE', '#662D91', '#000000']

URL = 'https://api-{river}.tfl.gov.uk/TravelTimes/Average/{pinLat}/{pinLon}/tile/{z}/{x}/{y}?'

@aljpy.autocache(disk=False, memory=True, duration=3600)
def river():
    # TfL seems to rotate its API server, declaring that the two which aren't active are 'blocked'
    for river in ['nile', 'tigris', 'ganges']:
        url = f'https://api-{river}.tfl.gov.uk'
        r = requests.get(url)
        if r.status_code == 200:
            return river
    raise ValueError('All three servers failed; check "https://api-tigris.tfl.gov.uk" and the alternatives yourself')

class TIM(GoogleWTS):

    def __init__(self, target, **kwargs):
        super().__init__()
        self._pin = {'pinLat': target[0], 'pinLon': target[1]}
        self._kwargs = kwargs

    def _image_url(self, tile):
        x, y, z = tile
        url = URL.format(**self._pin, z=z, x=x, y=y, river=river()) + urllib.parse.urlencode({**PARAMS, **self._kwargs})
        return url

@aljpy.autocache()
def timmap(target, zoom=12, interval=5):
    imagery = TIM(target, travelTimeInterval=interval)

    ax = plt.axes(projection=imagery.crs)
    ax.set_extent(LONDON)

    extent = ax._get_extent_geom(imagery.crs)
    img, extent, origin = imagery.image_for_domain(extent, zoom)

    plt.close(ax.figure)

    # Swap from colors to integers
    bands = np.full_like(img[:, :, 0], 255)
    for i, c in enumerate(COLORS):
        bands[(img == 255*mpl.colors.to_rgba_array(c)[0, :3]).all(-1)] = i
        
    # Replace the boundaries - which are a mix of colors - with the nearest solid color
    while (bands == 255).any():
        dilated = scipy.ndimage.grey_erosion(bands, size=3)
        bands[bands == 255] = dilated[bands == 255]

    times = interval/2 + interval*np.arange(len(COLORS), dtype=float)
    times[-1] = np.inf

    bands = times[bands]

    return {'img': bands, 'extent': extent, 'origin': origin}

@aljpy.autocache()
def basemap(zoom=12):
    imagery = OSM()

    ax = plt.axes(projection=imagery.crs)
    ax.set_extent(LONDON)
    extent = ax._get_extent_geom(imagery.crs)
    img, extent, origin = imagery.image_for_domain(extent, zoom)
    plt.close(ax.figure)

    return {'img': img, 'extent': extent, 'origin': origin}

def run():
    ax = plt.axes(projection=ccrs.Mercator.GOOGLE)
    ax.set_extent(LONDON)

    base = basemap()
    target = (51.49477, -0.05966)
    band = timmap(target)

    ax.imshow(**base)
    ax.imshow(**band, alpha=.75)
    ax.set_extent((-.1, 0, 51.475, 51.525))