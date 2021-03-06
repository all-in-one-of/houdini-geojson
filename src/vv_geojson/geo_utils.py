import os
import json
import logging
import math

if not os.getenv('DEV'):
    import hou

import pprint
pp = pprint.PrettyPrinter(indent=4)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        # logging.FileHandler("{0}/{1}.log".format(logPath, fileName)),
        logging.StreamHandler()
    ])

logger = logging.getLogger('geo_utils')


# see https://en.wikipedia.org/wiki/Spherical_coordinate_system
def spherical_to_cartesian(lon, lat, radius):

    latitude = math.radians(lat)
    longitude = math.radians(lon)

    x = math.cos(latitude) * math.cos(longitude) * radius
    y = math.cos(latitude) * math.sin(longitude) * radius
    z = math.sin(latitude) * radius  # z is 'up'

    return x, y, z


# see https://stackoverflow.com/questions/14329691/convert-latitude-longitude-point-to-a-pixels-x-y-on-mercator-projection
def spherical_to_mercator(lon, lat, mapwidth, mapheight):
    x = (lon + 180) * (mapwidth / 360)
    latitude_radians = lat * math.pi / 180
    mercator_N = math.log(math.tan((math.pi / 4) + (latitude_radians / 2)))
    y = (mapheight / 2) - (mapwidth * mercator_N / (math.pi * 2))

    return x, y, 0


class GeoJSONParser(object):

    def __init__(self, geo, geojsonpath):
        self._node_geo = geo
        self._geojson_path = geojsonpath
        self._radius = 100

        if not os.path.exists(geojsonpath):
            hou.ui.displayMessage('Please provide a path to an existing file!')
            return

        with open(geojsonpath) as f:
            self.geojson = json.load(f)

    def set_radius(self, value):
        self._radius = value

    def _yield_features(self):
        for feature in self.geojson['features']:
            yield feature

    def _get_geometry(self, typename, feature):
        geometry = feature.get('geometry')
        if not geometry:
            logger.error('No geometry found for current feature')
            return

        if geometry.get('type') != typename:
            logger.error(
                'No %s geo found inside %s feature' % (typename, typename))
            return

        return geometry

    def _add_point(self, coordinates):

        assert len(coordinates) == 2

        lon = coordinates[0]
        lat = coordinates[1]
        point = self._node_geo.createPoint()
        x, y, z = spherical_to_cartesian(lon, lat, self._radius)
        point.setPosition((x, y, z))

        return point

    def _add_multi_point(self, coordinates):

        for coordinate in coordinates:
            self._add_point(coordinate)

    def _add_polygon(self, poly):

        # create the polygon that will host the points
        hou_polygon = self._node_geo.createPolygon()
        # hou_polygon.setIsClosed(False)
        hou_polygon.setIsClosed(True)

        for ri, ring in enumerate(poly):
            logger.info('adding ring %i ' % ri)
            for coordinates in ring:
                point = self._add_point(coordinates)
                hou_polygon.addVertex(point)

    def _add_multi_polygon(self, coordinates):

        # TODO: check for inner holes
        logger.info('adding MultiPolygon')

        for pi, polygon in enumerate(coordinates):
            logger.info('adding polygon %i ' % pi)
            logger.info(polygon)
            self._add_polygon(polygon)

    def _parse_geometry(self, featuretype, geometry):
        coordinates = geometry.get('coordinates')

        if not coordinates:
            logger.error(
                'No coordinates found for current %s, skipping' % featuretype)
            return

        if featuretype == 'Point':
            self._add_point(coordinates)

        elif featuretype == 'MultiLineString':
            pass

        elif featuretype == 'LineString':
            pass

        elif featuretype == 'MultiPoint':
            self._add_multi_point(coordinates)

        elif featuretype == 'MultiPolygon':
            self._add_multi_polygon(coordinates)

    def create_geo(self):

        _features = self.geojson.get('features')
        if not _features:

            if self.geojson.get('type') == 'GeometryCollection':
                geometries = self.geojson.get('geometries')

                if not geometries:
                    message = 'The given GeoJSON has a GeometryCollection '
                    message += "that doesn't contain anything!"
                    hou.ui.displayMessage(message)
                    return

                for geometry in geometries:
                    feature_type = geometry.get('type')
                    logger.info('feature type: %s' % feature_type)

                    if not feature_type:
                        hou.ui.displayMessage('The given GeoJSON has no features and ' +
                                            'is not a GeometryCollection!')
                        logger.error('Feature <type> field not found.')
                        continue

                    self._parse_geometry(feature_type, geometry)

            return

        for feature in self._yield_features():
            # pp.pprint('index: %s, feature: %s\n' % (index, feature))

            # attribs = feature["properties"]
            # pp.pprint('properties: %s' % attribs)

            feature_type = feature["geometry"].get('type')
            logger.info('feature type: %s' % feature_type)

            if not feature_type:
                logger.error('Feature type property not found.')
                return

            geometry = self._get_geometry(feature_type, feature)
            if not geometry:
                continue

            self._parse_geometry(feature_type, geometry)