import math
from typing import Tuple, List


class CircleToPolygon:
    """
    Converts a gps location and distance into a polygon definition of a circle.

    This class uses a manual calculation to convert a geospatial circle definition into a polygon.
    Manual calculation was used in this instance to avoid installing and importing a full library for a single action.
    Review this decision in the future if multiple aspects of a geospatial calculation library are needed.
    """

    @classmethod
    def generate_polygon_points(cls, center_lon, center_lat, radius_km) -> List[List[float]]:
        """
        Generate a polygon shape that circumscribes a circle, based on a given center point and radius.

        Args:
            center_lat (float): Latitude of the center point in decimal degrees.
            center_lon (float): Longitude of the center point in decimal degrees.
            radius_km (float): Radius of the circle in kilometers.

        Returns:
            List[List[float]]: A geometric shape defined as a polygon suitable for geojson location search
            implementation. The shape is represented as a list of lists of coordinate points, where each point
            is a list containing the latitude and longitude in decimal degrees.

        Note:
            The current implementation uses an octagon that circumscribes the defined circle as the polygon shape.
            However, this method can be easily modified in the future for different shapes if required by future work
            or implementation changes.
        """
        inradius = radius_km
        circumradius, angles = cls._get_octagon_distance_bearing_list(inradius)
        polygon_points = [cls._calculate_destination(lon=center_lon,
                                                     lat=center_lat,
                                                     bearing=angle,
                                                     distance_km=circumradius) for angle in angles]

        return polygon_points

    @staticmethod
    def _calculate_destination(lon: float, lat: float, bearing: float, distance_km: float) -> List[float]:
        """
        Calculate the destination point given a starting latitude and longitude,
        a bearing (in decimal degrees), and a distance (in kilometers).

        Args:
            lon (float): Starting longitude in decimal degrees.
            lat (float): Starting latitude in decimal degrees.
            bearing (float): Bearing in decimal degrees (direction to travel).
            distance_km (float): Distance in kilometers.

        Returns:
            Tuple[float, float]: The destination longitude and latitude in decimal degrees.
        """
        # Specific notes on implementation
        # http://www.movable-type.co.uk/scripts/latlong.html
        # Destination point given distance and bearing from start point
        # Formula:	φ2 = asin( sin φ1 ⋅ cos δ + cos φ1 ⋅ sin δ ⋅ cos θ )
        #             λ2 = λ1 + atan2( sin θ ⋅ sin δ ⋅ cos φ1, cos δ − sin φ1 ⋅ sin φ2 )
        #             where	φ is latitude, λ is longitude, θ is the bearing (clockwise from north),
        #             δ is the angular distance d/R; d being the distance travelled, R the earth’s radius

        # Convert latitude and longitude to radians
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        brng = math.radians(bearing)
        d = distance_km

        # Earth's radius in kilometers
        R = 6371.0

        # Calculate destination point
        lat2 = math.asin(math.sin(lat1) * math.cos(d / R) +
                         math.cos(lat1) * math.sin(d / R) * math.cos(brng))
        lon2 = lon1 + math.atan2(math.sin(brng) * math.sin(d / R) * math.cos(lat1),
                                 math.cos(d / R) - math.sin(lat1) * math.sin(lat2))

        # Convert back to degrees
        lat2 = math.degrees(lat2)
        lon2 = math.degrees(lon2)

        # Normalize longitude to -180...+180 degrees
        lon2 = (lon2 + 540) % 360 - 180

        return [lon2, lat2]

    @staticmethod
    def _get_octagon_distance_bearing_list(inradius_km: float) -> Tuple[float, List[float]]:
        """
       Approximates a circle as an octagon and calculates the distance between the center and the octagon vertices,
       as well as the angle of each vertex.

       Args:
           inradius_km (float): Radius of the circle in kilometers.

       Returns:
           Tuple[float, List[float]]: Tuple[distance_km, List[angles] A tuple containing the distance between the
           center and the octagon vertices, and a list of angles (in degrees) of each vertex.

       Note:
           The defined octagon circumscribes the circle, so the area of the octagon is approximately 5.4% larger than
           the area of the circle. The list of angles is defined as a list of floats to accommodate possible future
           implementations that use geometries with partial degrees.
       """
        # Specific notes on implementation
        # Visualisation of circle radius to octagon process
        # https://calcresource.com/geom-octagon.html#:~:text=Like%20any%20regular%20polygon%2C%20a,are%20diameters%20of%20the%20circumcircle
        # Given the incircle radius, we calculate the circumcircle radius. The distance and vertex angles definition
        # of the octagon is used in later steps to calculate the (lat,lon) for the search polygon.
        #
        # Source equations
        # https://mathworld.wolfram.com/RegularOctagon.html
        # Side length:    a
        # Inradius:       r = 1/2(1+sqrt(2))a
        # Circumradius:   R = 1/2sqrt(4+2sqrt(2))a
        # Area:           A = 2(1+sqrt(2))a^2
        #
        # Derived equations
        # https://www.wolframalpha.com/input?i=simplify
        # Side length:    a = (2sqrt(2)-2)r
        # Inradius        r = user input
        # Circumradius:   R = r(sqrt(2)-1)sqrt(4+2sqrt(2))
        # Area:           A = 8(sqrt(2)-1)r^2
        # Incircle Area:  Ac = (pi)r^2
        # size ratio:     8(sqrt(2)-1):(pi) -> 3.313708:3.141593 -> 1.054786:1

        # circumradius = inradius_km * (math.sqrt(2) - 1) * math.sqrt(4 + 2 * math.sqrt(2))
        # https://www.wolframalpha.com/input?i=%28sqrt%282%29-1%29*sqrt%284%2B2*sqrt%282%29
        circumradius_constant = 1.082392200292393968799
        circumradius = inradius_km * circumradius_constant

        vertex_angles_degrees = [0, 45, 90, 135, 180, 225, 270, 315, 360]

        return circumradius, vertex_angles_degrees
