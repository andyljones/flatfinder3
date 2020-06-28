This is a flat finding tool I put together in two days for my own purposes. Under the general principle of if-you-don't-have-a-good-reason-not-to-then-you-should-open-source-your-work, here's the source! I, uh, don't actually expect anyone to use this as-is - if it has any utility to anyone, it'll be as a stack of code to pull useful bits out of.

If you _are_ interested in getting it working, know that it's designed to be used in tandem with vscode and Jupyter, since that's how I roll.

## Setup

```
# Build the image
docker build docker -t flatfinder3     

# Start the container
docker run -td --name flatfinder3 -v $(pwd):/code flatfinder3:latest

# Connect vscode to it
code --folder-uri $(python -c "import json; desc = json.dumps({'containerName': '/flatfinder3'}); print(f'vscode-remote://attached-container+{desc.encode().hex()}/code')")
```

Now go to the 'Remote Explorer' tab on the left-hand toolbar of vscode, and click the little '+' by the 5000 port at the bottom to forward it. Then navigate to `localhost:5000/noterminal` in your browser. You should get [a shiny new Jupyter window](https://github.com/andyljones/noterminal), from which you can play with the flatfinder data.

## Scraping Zoopla
To scrape Zoopla, [sign up the for developer API](https://developer.zoopla.co.uk/home) and then add the API key to a `credentials.json` file in your working directory formatted as
```
{"zoopla_key": "KEY_HERE"}
```
Then from the Jupyter notebook - or a terminal - run
```
from flatfinder3.zoopla import *
search()
```
It'll go through the London area in a grid, scraping the most recent 10,000 listings from the API for each grid cell. By default there are 36 grid cells and it'll take a few hours to run. You can check its progress  in a second window using 
```
from flatfinder3 import *

df = zoopla.listings()
base = webcat.basemap()

ax = plt.axes(projection=ccrs.Mercator.GOOGLE)
ax.scatter(df.longitude, df.latitude, marker='.', color='r', transform=ccrs.PlateCarree(), s=1)
ax.imshow(**base)
ax.figure.set_size_inches(10, 10)
```
Fetching the basemap might be slow the first time, then the caching layer will kick in. Loading the listings will be (after you've downloaded thousands of listigns) slow _every_ time since it's not cached, so try to only do that once per Jupyter session.

## Running the web server
Use `ctrl+` in vscode to open a terminal, then run
```
FLASK_ENV=development FLASK_APP=flatfinder3/server.py flask run --port 5001
```
to start a [Flask development server](https://flask.palletsprojects.com/en/1.1.x/quickstart/#debug-mode) on 5001. Again, use the Remote Explorer pane of vscode to forward the port, then go to `localhost:5001` to see the UI. 

Like with the code above, loading the listings can be slow but there's a lot of caching that'll go on after that. 

If you want to only show flats within a certain travel time of a point - or points - have a look at the `geo.aggtim` calls, which hook into TfL's travel time data. It's disabled by default because it depends on a list of locations that are specific to me (like, where my friends live, which I obviously don't want to put on GitHub), but looking at the `geo.LOCATIONS` conditionals will point you in the right direction about how to adapt it.