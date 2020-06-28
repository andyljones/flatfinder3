from cartopy import crs as ccrs
from shapely.geometry import MultiPoint
import numpy as np
from . import webcat, zoopla, geo, server
import matplotlib.pyplot as plt
import subprocess


def details(df):
    for _, r in df.sort_values('rental_prices.per_month').head(1).iterrows():
        subprocess.check_call(['open', r.details_url])
    
def cuts():
    layers = server.map_layers()

    fig, axes = plt.subplots(5, 1, subplot_kw={'projection': ccrs.Mercator.GOOGLE})
    base = webcat.basemap()
    cuts = {'park': 10, 'town': 10, 'aerial': 30, 'central': 60, 'friends': 45}
    for ax, name in zip(axes.flatten(), layers):
        ax.imshow(**base)
        ax.imshow(**geo.threshold(layers[name], cuts[name]), alpha=.5, cmap='Greys_r')
        ax.set_title(name)
        ax.set_extent((-.25, +0.1, 51.4, 51.6))
    fig.set_size_inches(10, 40)

def decisions():
    df = server.decision_dataframe()

    base = webcat.basemap()

    ax = plt.axes(projection=ccrs.Mercator.GOOGLE)
    ax.figure.set_size_inches(10, 10)

    sub = df[df.decision.isin(('good', 'great'))]
    color = sub.decision.map({'bad': 'r', 'meh': 'y', 'good': 'b', 'great': 'g'})
    ax.scatter(sub.longitude, sub.latitude, transform=ccrs.PlateCarree(), marker='.', s=200, c=color)
    xs, ys = ax.get_xlim(), ax.get_ylim()

    rest = df[~df.index.isin(sub.index)]
    ax.scatter(rest.longitude, rest.latitude, transform=ccrs.PlateCarree(), marker='.', s=10, color='k')

    ax.imshow(**{**base, 'img': base['img'].mean(-1)}, cmap='Greys_r', alpha=.5)
    ax.set_xlim(xs), ax.set_ylim(ys)
