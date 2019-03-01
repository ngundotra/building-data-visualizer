import sys, json
import osmium as osm
import pyproj
import shapely.wkb as wkblib
import shapely.ops as ops
from shapely.geometry import mapping
from functools import partial
import pdb

class BuildingProcessor(osm.SimpleHandler):
    def __init__(self, wkfab, eui_loc, verbosity=0):
        osm.SimpleHandler.__init__(self)

        self.verbose = verbosity
        self.eui_loc = eui_loc
        # Sanity check to make sure the region passed is valid
        self.find_eui()

        self.a = 0
        self.nodes = {}

        self.wkfab = wkfab
        self.height_found = 0 
        self.buildings = []
        # Number of buildings
        self.b = 0
        # Number of named buildings
        self.bn = 0
        # Number of buildings with height
        self.bh = 0
        # Number of buildings with coords
        self.w_coords = 0

#     def parse_building(self, a):
#         tags = a.tags
#         if 'building' in tags:
#             self.b += 1
#             if 'name' in tags:
#                 self.bn += 1
#             if 'height' in tags:
#                 self.bh += 1
#             if 'name' in tags and 'height' in tags:
#                 self.full_info += 1
#                 # Create the GeoJSON from the osmium.Area obj
#                 wkb = self.wkfab.create_multipolygon(a)    
#                 poly = wklib.loads(wkb, hex=True)
#                 geojson = mapping(poly)
# 
#                 # Get remaining info
#                 height = tags['height']
#                 name = tags['name']
#                 self.buildings.append((name, height, geojson))

    def find_eui(self):
        """find energy usage intensity to estimate energy usage in kWh/m^2"""
        name = self.eui_loc.lower()
        if name == 'mumbai':
            return 54
        elif name == 'new delhi':
            return 57
        else:
            raise ValueError("Could not find given region in our EUI lookup: {}".format(self.eui_loc))

    def calculate_energy(self, geojson):
        """Calculate energy based upon information in the geojson"""
        props = geojson['properties']
        levels = int(props.get('building:levels', -1))
        area = props.get('area')
        height = props.get('height', -1)
        
        if height != -1:
            height = self.parse_height(height)

        if levels < 0 and height > 0:
            levels  = height // 3 # assume each level is 3m
        elif levels < 0 and height < 0:
            levels = 1
        eui = self.find_eui()
        return eui * levels * area 

    def parse_height(self, given):
        n = 0
        try:
            n = float(given)
        except ValueError as e:
            # If it's a word, height = 0
            if ord('a') <= ord(given[0].lower()) or ord(given[0].lower()) <= ord('z'):
                return n

            # Look for m/ft at the end 
            meters = True
            given = given.strip(' ')
            if 'ft' in given:
                meters = False
                given = given[:given.indexOf('ft')]
            elif 'm' in given:
                given = given[:given.indexOf('m')]
            elif '\'' or '"' in given:
                meters = False
                quote_idx = given.indexOf('\'')
                if quote_idx > 0:
                    n += int(given[:quote_idx])
                    given = given[quote_idx+1:]
                dquote_idx = given.indexOf('"')
                if dquote_idx > 0:
                    n += int(given[:dquote_idx]) / 12.0
                
            # Just in case there's any remaining white space
            parts = given.split(' ')
            given = parts[0]
            try:
                n = float(given)
            except ValueError as e:
                print(f"{given} couldn't be parsed :/")
                return 0

            if meters:
                return n
            # 1 foot = 0.3048 m
            return n * 0.3048
        return n
    
    def node(self, n):
        if 'height' in n.tags:
            try:
                self.nodes[n.id] = (self.parse_height(n.tags['height']), n.location.lat, n.location.lon)
                print("Number of nodes is: {}".format(len(self.nodes)), end='\n\r')
            except ValueError as e:
                print(f"Error str>flt: {n.tags['height']}")

    def area(self, a): 
        """Try to construct an avg height from the nodes in a building"""
        self.a += 1
        if 'building' not in a.tags:
            return
        # It's a building
        self.b += 1
        
        # Polygon recreation
        wkb = self.wkfab.create_multipolygon(a)
        poly = wkblib.loads(wkb, hex=True)
        geom_area = ops.transform(
                partial(
                    pyproj.transform,
                    pyproj.Proj(init='EPSG:4326'),
                    pyproj.Proj(
                        proj='aea',
                        lat1=poly.bounds[1],
                        lat2=poly.bounds[3])),
                    poly)
        geojson = {'type': 'Feature', 'properties':{},
                'geometry': mapping(poly)}

        geojson['properties']['area'] = geom_area.area

        if 'building:levels' in a.tags:
            self.bh += 1
            geojson['properties']['building:levels'] = a.tags['building:levels']
        if 'height' in a.tags:
            try:
                ht = self.parse_height(a.tags['height'])
                geojson['properties']['height'] = ht
                self.height_found += 1
            except Exception as e:
                print("Couldn't parse height:",a.tags['height'])
                print(e)

        if 'name' in a.tags:
            geojson['properties']['name'] = a.tags['name']
        geojson['properties']['eui'] = self.calculate_energy(geojson)
        self.buildings.append(geojson)
        
#         # Check for building heights in any of the node tags
#         for i, ring in enumerate(a.outer_rings()):
#             if self.verbose > 2:
#                 print("entered outer_ring loop:", i)
#             avg_height = 0
#             avg_n = 0
#             for j, n in enumerate(ring):
#                 # We don't calculate anything for the last coord bc == 1st coord
#                 if j == len(ring) - 1:
#                     continue
#                 if self.verbose > 2:
#                     print("\tentered nodes in outer ring:", j)
#                 # Convert from reference node to actual node
#                 if n.ref not in self.nodes:
#                     continue
#                 if self.verbose > 2:
#                     print("\t\tfound node w height")
#                 n_height, lat, lon = self.nodes.pop(n.ref, (None, None, None))
#                 if n_height is None or lat is None or lon is None:
#                     raise ValueError(f"{n.ref} not found in self.nodes :/")
#                 avg_height += n_height
#                 avg_n += 1
#                 print('\t\t',avg_n)
#             # if there were nodes that had height data, then
#             # we can construct an avg height for the area
#             if avg_n > 0:
#                 avg_height = avg_height / avg_n 
#                 self.height_found += 1
#                 if self.verbose > 1:
#                     print("Heights found:", self.height_found)
# 

if __name__ == '__main__':
    """
    We scrape an OSM file, looking for named buildings with heights, and store them into an optional output file.
    i.e. `python scrape.py OSM_FILE REGION OUTPUT_FILE`
    `python scrape.py mumbai.osm Mumbai mumbai.geojson`
    where OUTPUT_FILE is optional
    """
    if len(sys.argv) < 3:
        raise ValueError("Missing a filename to parse")
    elif len(sys.argv) == 3:
        _this_, to_parse, region = sys.argv
        fname_to_save = to_parse.replace(".osm.pbf", ".geojson")
        fname_to_save = to_parse.replace(".osm", ".geojson")
    elif len(sys.argv) == 4:
        region = sys.argv[-2]
        fname_to_save = sys.argv[-1]
    else:
        raise ValueError("Too many arguments passed (>4)")

    to_parse = sys.argv[1] 
    print("Reading file: {}".format(to_parse))
   
    wkbfab = osm.geom.WKBFactory()
    tlhandler = BuildingProcessor(wkbfab, region)
    tlhandler.apply_file(to_parse)

    # Print statistics
    print("Number of buildings:", tlhandler.b)
    print("Number of bldg heights found:", tlhandler.height_found, "{:<.3f}%".format(tlhandler.height_found / tlhandler.b*100))
    print("Number of bldg levels found:", tlhandler.bh, "{:<.3f}%".format(tlhandler.bh / tlhandler.b*100))
    
    # Save the buildings with heights & names to a file
    print("Saving named & heighted buildings to {}".format(fname_to_save))
    with open(fname_to_save, 'w') as out_file:
        geodict = {'type': 'FeatureCollection', 'features': tlhandler.buildings}
        json.dump(geodict, out_file)

