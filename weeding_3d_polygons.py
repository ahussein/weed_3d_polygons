import sys
import os
import arcpy
import math

arcpy.env.overwriteOutput = True

def is_point_in_line(line, point):
    """
    Checks if a point belongs to the same straight line or not

    @param line: list of points that represents the current line
    @param point:   point (x, y) that need to be checked

    @returns: True if the points belongs to the same straight line, false otherwise
    """
    if len(line) < 2:
        print "Line need to have at least two points"
        return False
    # take the first two points of the current line
    pnt1 = line[0]
    pnt2 = line[1]
    diff = abs((pnt1.Y - pnt2.Y) * (pnt1.X - point.X) - (pnt1.Y - point.Y) * (pnt1.X - pnt2.X))
    return diff < 1e-12


def convert_polygon_to_lines(polygon_obj):
    """
    Converts a polygon object to set of straight lines

    @param polygon_obj: The polygon object to covert
    """
    lines = []
    partnum = 0

    # Step through each part of the feature
    #
    for part in polygon_obj:

        # Step through each vertex in the feature
        #
        start_point = polygon_obj.firstPoint
        line_start_point = None
        current_line = []
        for pnt in polygon_obj.getPart(partnum):
            if pnt:
                if line_start_point is None:
                    line_start_point = pnt
                    current_line = [line_start_point]
                    continue

                # take the first two points since they will always be a line, and then check if the third point belong to the same line
                # if the point belong to the same line then add the point to the line and move on the next point
                # if the point does not belong to the same line then we need to take the last point of the the current line as the start point in the new line and the current point will be the second point
                # of the new line and then we do the same again by taking the next point and checking if it belongs to the same line or not
                if pnt != line_start_point:
                    if len(current_line) < 2:
                        current_line.append(pnt)
                    else:
                        if is_point_in_line(current_line, pnt):
                            current_line.append(pnt)
                        else:
                            lines.append(current_line)
                            line_start_point = current_line[-1]
                            current_line = [line_start_point, pnt]
        if current_line:
            lines.append(current_line)

        partnum += 1
    return lines


def convert_polyline_to_lines(polyline_obj):
    """
    Converts a polyline object to set of stright segments

    @param polyline_obj: The polyline object to covert
    """
    lines = []
    # Step through each part of the feature
    #
    for part in polyline_obj:

        # Step through each vertex in the feature
        #
        start_point = polyline_obj.firstPoint
        line_start_point = None
        current_line = []
        for pnt in part:
            if pnt:
                if line_start_point is None:
                    line_start_point = pnt
                    current_line = [line_start_point]
                    continue

                # take the first two points since they will always be a line, and then check if the third point belong to the same line
                # if the point belong to the same line then add the point to the line and move on the next point
                # if the point does not belong to the same line then we need to take the last point of the the current line as the start point in the new line and the current point will be the second point
                # of the new line and then we do the same again by taking the next point and checking if it belongs to the same line or not
                if pnt != line_start_point:
                    if len(current_line) < 2:
                        current_line.append(pnt)
                    else:
                        if is_point_in_line(current_line, pnt):
                            current_line.append(pnt)
                        else:
                            lines.append(current_line)
                            line_start_point = current_line[-1]
                            current_line = [line_start_point, pnt]
        if current_line:
            lines.append(current_line)

    return lines

def extract_shapes(in_feature_class):
    """
    Extracts shape  objects from input feature class

    @param in_feature_class:    Input feature class

	@returns: shape type and dictionary with the FID as key and the shape object as value
    """
    result = {'shape_type': None, 'shape_data': {}}
    # Identify the geometry field
    #
    desc = arcpy.Describe(in_feature_class)
    shapefieldname = desc.ShapeFieldName

    # Create search cursor
    #
    rows = arcpy.SearchCursor(in_feature_class)

    # Enter for loop for each feature/row
    #
    for row in rows:
        # Create the geometry object
        #
        feat = row.getValue(shapefieldname)
        FID = row.getValue(desc.OIDFieldName)
        if result['shape_type'] is None:
            result['shape_type'] = feat.type
        # we only support one type in the same feature class, either polyline or polygon, no mixed shapes supported at the moment
        elif result['shape_type'] != feat.type:
            raise RuntimeError('Different shape types detected in input feature class. Not supported!')

        result['shape_data'][FID] = feat
    del rows

    return result


# def draw_points(infc, output_fc):
#
#     with arcpy.da.UpdateCursor(output_fc, [f.name for f in arcpy.ListFields(output_fc)]) as cursor:
#         for row in cursor:
#             cursor.deleteRow()
#
#     with arcpy.da.InsertCursor(output_fc, ['SHAPE@XY']) as cursor:
#         result = extract_shapes(infc)
#         for shape in result['shape_data'].itervalues():
#             if result['shape_type'] == 'polygon':
#                 lines = convert_polygon_to_lines(shape)
#             elif result['shape_type'] == 'polyline':
#                 lines = convert_polyline_to_lines(shape)
#             for line in lines:
#                 for point in line:
#                     cursor.insertRow([point])



def transform_3d_line_to_2d_coord(line):
    """
    Transforms the the line that consists of points with z values into a distance, elevation system

    @param line:    set of points consist the line, each point has its z value
    """
    first_point = line[0]
    # we need to have both the coordinates as list of ordered values so that we can maintian the start/end points of the line
    # and we also need the map between the coordinate in 2d and the cooresponding polygon point
    result = {(0, first_point.Z): first_point}
    keys_result = [(0, first_point.Z)]
    first_point_geo = arcpy.PointGeometry(first_point)
    for point in line[1:]:
        #distance = math.sqrt(math.pow(first_point.X - point.X, 2) + math.pow(first_point.Y - point.Y, 2))
        distance = first_point_geo.distanceTo(arcpy.PointGeometry(point))
        keys_result.append((distance, point.Z))
        result[(distance, point.Z)] = point
    return keys_result, result



def douglas_peucker(_2d_coord, z_threshold):
    """
    Simplifies a line based on the douglas peucker algorithm
    This code is copied from https://github.com/sebleier/RDP/blob/master/__init__.py
    """
    def distance(a, b):
        return  math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def point_line_distance(point, start, end):
        if (start == end):
            return distance(point, start)
        else:
            n = abs(
                (end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (end[1] - start[1])
            )
            d = math.sqrt(
                (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
            )
            return n / d
    dmax = 0.0
    index = 0
    for i in range(1, len(_2d_coord) - 1):
        d = point_line_distance(_2d_coord[i], _2d_coord[0], _2d_coord[-1])
        if d > dmax:
            index = i
            dmax = d
    if dmax >= z_threshold:
        print 'Dmax is: %s' % dmax
        results = douglas_peucker(_2d_coord[:index+1], z_threshold)[:-1] + douglas_peucker(_2d_coord[index:], z_threshold)
    else:
        results = [_2d_coord[0], _2d_coord[-1]]
    return results



def weed_line(line, z_threshold):
    """
    Works on a straight lines that has z-values, eliminates the points in the line where z-value variation of these points are less
    then the given threshold

    @param line:    set of points consist the line, each point has its z value
    @param z_threshold: threshold of the allowed variation of z the values
    """
    _2d_coord, _2d_coord_point_map = transform_3d_line_to_2d_coord(line)
    reduced_points = douglas_peucker(_2d_coord, z_threshold)
    modified_line_points = []
    for point in reduced_points:
        modified_line_points.append(_2d_coord_point_map[point])

    # now we need to remove the points that does not exist in the reduced points from the line object
    for point in list(line):
        if point not in modified_line_points:
            line.remove(point)



def weed_3d_shapes(in_fc, z_threshold):
    """
    Extracts all the 3d shapes (only works for polygons or polylines) from the input feature class
    Decompose all the shapes to straight lines
    For each straight line, the points that make up the line will be weeded according to their z-value and its variation according to the z_threshold

    @param in_fc:   Input feature class, we expect this to contain 3d polygons
    @param z_threshold: The max allowed variation in each straight segment
    """
    # extract all the shapes from the input feature class
    print "Extracting shapes from input feature class"
    result = extract_shapes(in_fc)
    shape_type, shape_data = result['shape_type'], result['shape_data']

    # create a map that will contain a shape object as key and list of stright lines of that shape as value
    shape_lines_map = {}

    # convert each shape to stright lines
    for FID, shape in shape_data.iteritems():
        if shape_type == 'polygon':
            shape_lines_map[FID] = convert_polygon_to_lines(shape)
        elif shape_type == 'polyline':
            shape_lines_map[FID] = convert_polyline_to_lines(shape)

    # for each shape, go through the lines and weed the lines based on the z-variation
    for lines in shape_lines_map.itervalues():
        for line in lines:
            weed_line(line, z_threshold)

	# after weeding all the lines, create new shapes for the weeded vertices
	updated_shapes = {}
    for FID, lines in shape_lines_map.iteritems():
        all_points = []
        for line in lines:
            for point in line:
                all_points.append(point)
        if shape_type == 'polygon':
            shape = arcpy.Polygon(arcpy.Array(all_points), shape_data[FID].spatialReference, True, False)
        elif shape_type == 'polyline':
            shape = arcpy.Polyline(arcpy.Array(all_points), shape_data[FID].spatialReference, True, False)
        updated_shapes[FID] = shape
    return updated_shapes


def update_fc(fc, data):
    """
    Updates a feature class with an updated values
    """
    desc = arcpy.Describe(fc)
    cursor = arcpy.UpdateCursor(fc)
    for row in cursor:
        FID = row.getValue(desc.OIDFieldName)
        row.setValue(desc.shapeFieldName, data[FID])
        cursor.updateRow(row)
    del cursor


def main(in_fc, z_threshold):
    """
    Main entry point
    """
    base_dir = os.path.dirname(in_fc)
    output_dir = os.path.join(base_dir, 'output')
    # if the output directory does not exist, then create it
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_fc = os.path.join(output_dir, "output.shp")

    # copy the input feature class to the output feature class
    arcpy.CopyFeatures_management(in_fc, output_fc)

    print "Weeding 3D shapes."
    result = weed_3d_shapes(in_fc, z_threshold)

    print "Done"

    # update the output feature class with the new weeded data
    print "Updating output feature class"
    update_fc(output_fc, result)
    print "Done"


    # #draw all the points from the in_fc and output_fc for comparison
    # in_fc_points = os.path.join(output_dir, 'infc_points.shp')
    # out_fc_points = os.path.join(output_dir, 'outfc_points.shp')
    # draw_points(in_fc, in_fc_points)
    # draw_points(output_fc, out_fc_points)
    # # now we want to draw all the points to check how they look like
    # # all_points = []
    # # for lines in result.itervalues():
    # #     for line in lines:
    # #         for pnt in line:
    # #             all_points.append(pnt)
    #
    # # draw_points(all_points, os.path.join(os.path.dirname(in_fc), 'Points.shp'))


if __name__ == "__main__":
    # if we want to create toolbox in arcmap then we get the values from the user provided parameters
    infc = arcpy.GetParameterAsText(0)
    z_threshold = arcpy.GetParameter(1)
    main(infc, z_threshold)
