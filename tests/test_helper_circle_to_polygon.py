"""
This test validates the circle-to-polygon logic implementation to ensure that any changes to the algorithm either
do not impact the results, or force the tester to account for them in testing.

Circle to polygon test process:
1. call circle_to_polygon class with input point (lon,lat) and distance
2. validate the output results are within 10m of the defined expected output
3. perform test with expected reasonable distance searches at 10km and 250km

Initial test data setup to define the expected output:
1. generate calculated results (polygon vertices) for the specified point (lon,lat) and distance
2. calculate the midpoint between polygon vertices to locate the circum circle tangent points (http://www.geomidpoint.com/)
3. calculate the distance between the center and vertices, and between the center and circum circle tangent points (https://boulter.com/gps/distance/)
4. confirm the calculated distances are accurate and within expected tolerances

Based on the geometric properties of an octagon that circumscribes a circle, the octagon is expected to have a surface
area about 5.5% larger than the circle when working in cartesian space. The difference in area may be larger when the
octagon and circle are projected onto a spherical space.
Circum circle tangent point distances are within approximately +/- 0.2% of the specified distance.
Vertex point distances are approximately 8% larger than the specified distance.
"""

import pytest
import math

from app.helpers.circle_to_polygon import CircleToPolygon

# variable for test result evaluation
TEN_METER_GPS_RESOLUTION = 0.0001

# kings park war memorial gps coordinates
k_lon = 115.84468164000201
k_lat = -31.960738430689943


ten_km_calculated_result = CircleToPolygon.generate_polygon_points(center_lon=k_lon,
                                                                   center_lat=k_lat,
                                                                   radius_km=10)


# octagon vertices at 10 km specified distance
ten_km_expected_result = [
    (115.84468164000202, -31.863396561509866),
    (115.92575032253717, -31.8918815752825),
    (115.95941592601673, -31.960686839767195),
    (115.9258719404163, -32.029543695082566),
    (115.84468164000202, -32.05808029987003),
    (115.76349133958774, -32.029543695082566),
    (115.72994735398731, -31.960686839767195),
    (115.76361295746676, -31.8918815752825),
    (115.84468164000202, -31.863396561509866)]

# midpoints between 10km vertices, only used for test setup validation and viewing
# ten_km_circum_circle_tangent_points = [
#     (115.88521, -31.877645),
#     (115.942577, -31.926285),
#     (115.94265, -31.995116),
#     (115.885283, -32.043818),
#     (115.80408, -32.043818),
#     (115.746713, -31.995116),
#     (115.746786, -31.926285),
#     (115.804154, -31.877645)]

two_fifty_km_calculated_result = CircleToPolygon.generate_polygon_points(center_lon=k_lon,
                                                                         center_lat=k_lat,
                                                                         radius_km=250)

# octagon vertices at 250 km specified distance
two_fifty_km_expected_result = [
    (115.84468164000202, -29.527191701187782),
    (117.83598455151082, -30.224387169202185),
    (118.7123689608004, -31.92850458969386),
    (117.91201848899584, -33.664819890361),
    (115.84468164000202, -34.394285160192105),
    (113.77734479100809, -33.664819890361),
    (112.97699431920364, -31.92850458969386),
    (113.85337872849323, -30.224387169202185),
    (115.84468164000202, -29.527191701187782)]

# midpoints between 250km vertices, only used for test setup validation and viewing
# two_fifty_km_circum_circle_tangent_points = [
#     (116.836853, -29.879526),
#     (118.270249, -31.077187),
#     (118.316101, -32.797298),
#     (116.882794, -34.033877),
#     (114.806569, -34.033877),
#     (113.373262, -32.797298),
#     (113.419114, -31.077187),
#     (114.852511, -29.879526)]


def generate_pytest_parametrized_list(calc, exp):
    assert len(calc) == len(exp), f"Data length mismatch: Calculated [{len(calc)}], Expected [{len(exp)}]."
    result = []
    for num, val in enumerate(calc):
        result.append({"calc_lon": calc[num][0],
                       "calc_lat": calc[num][1],
                       "exp_lon": exp[num][0],
                       "exp_lat": exp[num][1]})
    return result


@pytest.mark.parametrize("result", generate_pytest_parametrized_list(ten_km_calculated_result, ten_km_expected_result))
def test_ten_km_circle_definition(result):
    assert math.isclose(result["calc_lon"], result["exp_lon"], abs_tol=TEN_METER_GPS_RESOLUTION), \
        f"Calculated longitude [{result['calc_lon']}] is too far from expected longitude [{result['exp_lon']}]"
    assert math.isclose(result["calc_lat"], result["exp_lat"], abs_tol=TEN_METER_GPS_RESOLUTION), \
        f"Calculated latitude [{result['calc_lat']}] is too far from expected latitude [{result['exp_lat']}]"


@pytest.mark.parametrize("result", generate_pytest_parametrized_list(two_fifty_km_calculated_result, two_fifty_km_expected_result))
def test_two_fifty_km_circle_definition(result):
    assert math.isclose(result["calc_lon"], result["exp_lon"], abs_tol=TEN_METER_GPS_RESOLUTION), \
        f"Calculated longitude [{result['calc_lon']}] is too far from expected longitude [{result['exp_lon']}]"
    assert math.isclose(result["calc_lat"], result["exp_lat"], abs_tol=TEN_METER_GPS_RESOLUTION), \
        f"Calculated latitude [{result['calc_lat']}] is too far from expected latitude [{result['exp_lat']}]"
