# Scrape.py

Uses Shapely and Osmium to create GeoJSON from small OSM (XML) files.

`python scrape.py berkeley.osm` -> generates to berkeley.geojson
`python scrape.py india.osm.pbf india-bldgs.out` -> generates to india-bldgs.out if it doesn't segfault parsing gigantic osm files

Please only use on small files, or the parser will blow up memory and segfault.
