#!/usr/bin/env python

"""Publishes relative path ECEF poordinates from given geodetic coordinates

Subscribes to:
    None

Publishes to:
    /planning/trajectory

Sends nav_msg/Path to "core_control" node (control_node.cpp)

Convenience degrees-minute-second to decimal converter can be found here: https://repl.it/@DRmoto/DMStoDec
"""

from __future__ import print_function
from __future__ import division

import math
import rospy
import utm
from std_msgs.msg import Header
from geometry_msgs.msg import Point, Pose, PoseStamped
from nav_msgs.msg import Path

import gps_parser
from geodesy_conversion_ECEF import GeodesyConverterECEF
from geodesy_conversion_UTM  import GeodesyConverterUTM

class PathInterpolatorECEF(GeodesyConverterECEF):
    def __init__(self, latitudesData, longitudesData, heightsData, centimetersPerPoint=None):
        super(PathInterpolatorECEF, self).__init__(latitudesData, longitudesData, heightsData)
        self.heightsData = heightsData
        self.centimetersPerPoint = 25 if centimetersPerPoint==None else centimetersPerPoint

    def set_dist_between_points(self, centimetersPerPoint):
        """Set distance between points after interpolation"""
        self.centimetersPerPoint = centimetersPerPoint
    
    def get_point_density_ECEF(self, x1, y1, z1, x2, y2, z2, centimetersPerPoint):
        pointDensity = super(PathInterpolatorECEF, self).euclidian_distance_3d(x1, y1, z1, x2, y2, z2) / (centimetersPerPoint / 100.0)

        return int(pointDensity)

    # Instead of different functions for positive and negative
    def interpolate_ECEF(self, i, relativeX, relativeY, relativeZ, numberOfCoarsePoints):
        """Interpolate between two ECEF points, given index of one of the points."""

        finePointsX = []
        finePointsY = []
        finePointsZ = []

        # Vanilla case: for all points except final point
        if i < numberOfCoarsePoints-1:
            # Number of points between each interpolated point
            pointDensity = self.get_point_density_ECEF(relativeX[i], relativeX[i], relativeZ[i], relativeX[i+1], relativeY[i+1], relativeZ[i+1], self.centimetersPerPoint)

            # Declare the first and second positions for interpolation
            x0 = relativeX[i]     
            x1 = relativeX[i+1]
            y0 = relativeY[i]     
            y1 = relativeY[i+1]   
            z0 = relativeZ[i]     
            z1 = relativeZ[i+1]

            for n in range(pointDensity):
                finePointsX.append( x0 + (x1-x0)*(n/pointDensity) )
                finePointsY.append( y0 + (y1-y0)*(n/pointDensity) ) # was previously: finePointsY.append( ((y1-y0) / (x1-x0)) * (finePointsX[n]) + y0*((x1-x0) / (y1-y0)) )
                finePointsZ.append( z0 + (z1-z0)*(n/pointDensity) )

        # Corner case: for final point    
        if i == numberOfCoarsePoints-1:
            pointDensity = self.get_point_density_ECEF(relativeX[i-1], relativeX[i-1], relativeZ[i-1], relativeX[i], relativeY[i], relativeZ[i], 25)

            x0 = relativeX[i-1]
            x1 = relativeX[i]
            y0 = relativeY[i-1]
            y1 = relativeY[i]
            z0 = relativeZ[i-1]     
            z1 = relativeZ[i]

            for n in range(pointDensity):
                finePointsX.append( x0 + (x1-x0)*(n/pointDensity) )
                finePointsY.append( y0 + (y1-y0)*(n/pointDensity) )
                finePointsZ.append( z0 + (z1-z0)*(n/pointDensity) )

        # print("pointDensity used on iteration {} was {}".format(i, pointDensity))
        return finePointsX, finePointsY, finePointsZ

    def interpolation_publish_ECEF(self):
        """Interpolates between all ECEF coordinates and publishes them as a Path.

        Subscribes
        ----------
        None
        
        Publishes
        ---------
        Topic: /planning/trajectory
            Msg: Path
        """

        path_publisher = rospy.Publisher('/planning/trajectory', Path, queue_size=1000)
        rate = rospy.Rate(1)

        xPosition, yPosition, zPosition = super(PathInterpolatorECEF, self).geodetic_data_to_ECEF_data()
        # print("\nxPosition =", xPosition, "\nyPosition =", yPosition, "\nzPosition =", zPosition)
        relativeX, relativeY, relativeZ = super(PathInterpolatorECEF, self).global_to_relative_ECEF(xPosition, yPosition, zPosition)
        # print("\nrelativeX =", relativeX, "\nrelativeY =", relativeY, "\nrelativeZ =", relativeZ, "\n")
        
        # Contains lists of fine points, including coarse points
        xInterpolatedPositions = []
        yInterpolatedPositions = []
        zInterpolatedPositions = []

        numberOfCoarsePoints = len(relativeX)

        for i in range(numberOfCoarsePoints):
            finePointsX, finePointsY, finePointsZ = self.interpolate_ECEF(i, relativeX, relativeY, relativeZ, numberOfCoarsePoints)

            xInterpolatedPositions.extend(finePointsX)
            yInterpolatedPositions.extend(finePointsY)
            zInterpolatedPositions.extend(finePointsZ)
        
        while not rospy.is_shutdown():
            path = Path()
        
            for i in range(len(yInterpolatedPositions)):
                # # Attempting to add points directly in one line without creating point object first
                # path.poses.append(path.poses[i].pose.position.x = 0.0) # finePointsX[i]
                # path.poses[i].pose.position.y = 0.0 # finePointsY[i]
                # path.poses[i].pose.position.z = 0.0

                currentPoseStampMsg = PoseStamped()
                h = Header()

                h.stamp = rospy.Time.now()
                h.seq = i
                currentPoseStampMsg.header.seq = h.seq
                currentPoseStampMsg.header.stamp = h.stamp

                currentPoseStampMsg.pose.position.x = xInterpolatedPositions[i] 
                currentPoseStampMsg.pose.position.y = yInterpolatedPositions[i] 
                currentPoseStampMsg.pose.position.z = zInterpolatedPositions[i]

                path.poses.append(currentPoseStampMsg)
            
            path_publisher.publish(path)
            rospy.loginfo("Published Path with %d steps", i+1)
            rate.sleep()

class PathInterpolatorUTM(GeodesyConverterUTM):
    def __init__(self, latitudesData, longitudesData, centimetersPerPoint=25):
        super(PathInterpolatorUTM, self).__init__(latitudesData, longitudesData, centimetersPerPoint)
        self.centimetersPerPoint = centimetersPerPoint

    def set_dist_between_points(self, centimetersPerPoint):
        """Set distance between points after interpolation"""
        self.centimetersPerPoint = centimetersPerPoint
    
    def get_point_density_UTM(self, relativeEasting1, relativeNorthing1, relativeEasting2, relativeNorthing2, centimetersPerPoint):
        pointDensity = super(PathInterpolatorUTM, self).euclidian_distance_2d(relativeEasting1, relativeEasting1, relativeEasting2, relativeNorthing2) / (centimetersPerPoint / 100.0)

        return int(pointDensity)

    def interpolate_UTM(self, i, relativeEasting, relativeNorthing, numberOfCoarsePoints):
        """Interpolate between two UTM points, given index of one of the points."""
        
        finePointsEasting = []
        finePointsNorthing = []

        # Vanilla case: for all points except final point
        if i < numberOfCoarsePoints-1:
            # Number of points between each interpolated point
            pointDensity = self.get_point_density_UTM(relativeEasting[i], relativeEasting[i], relativeEasting[i+1], relativeNorthing[i+1], 25)

            # Declare the first and second positions for interpolation
            x0 = relativeEasting[i]     
            x1 = relativeEasting[i+1]
            y0 = relativeNorthing[i]     
            y1 = relativeNorthing[i+1]   

            for n in range(pointDensity):
                finePointsEasting.append( x0 + (x1-x0)*(n/pointDensity) )
                finePointsNorthing.append( y0 + (y1-y0)*(n/pointDensity) )

        # Corner case: for final point
        if i == numberOfCoarsePoints-1:
            pointDensity = self.get_point_density_UTM(relativeEasting[i-1], relativeEasting[i-1], relativeEasting[i], relativeNorthing[i], 25)

            x0 = relativeEasting[i-1]
            x1 = relativeEasting[i]
            y0 = relativeNorthing[i-1]
            y1 = relativeNorthing[i]

            for n in range(pointDensity):
                finePointsEasting.append( x0 + (x1-x0)*(n/pointDensity) )
                finePointsNorthing.append( y0 + (y1-y0)*(n/pointDensity) )

        # print("pointDensity used on iteration {} was {}".format(i, pointDensity))
        return finePointsEasting, finePointsNorthing

    def interpolation_publish_UTM(self):
        """Interpolates between all ECEF coordinates and publishes them as a Path.

        Subscribes
        ----------
        None
        
        Publishes
        ---------
        Topic: /planning/trajectory
            Msg: Path
        """

        path_publisher = rospy.Publisher('/planning/trajectory', Path, queue_size=1000)
        rate = rospy.Rate(1)
        #############################################################################################################################
        eastings, northings, zoneNumbers, zoneLetters = super(PathInterpolatorUTM, self).geodetic_data_to_UTM_data()
        # print("\neastings =", eastings, "\nnorthings =", northings)
        relativeEastings, relativeNorthings = super(PathInterpolatorUTM, self).global_to_relative_UTM(eastings, northings)
        # print("\nrelativeEasting =", relativeEastings, "\nrelativeNorthings =", relativeNorthings)

        # Contains lists of fine points, including coarse points
        eastingInterpolatedPositions  = []
        northingInterpolatedPositions = []

        numberOfCoarsePoints = len(relativeEastings)

        for i in range(numberOfCoarsePoints):
            finePointsEasting, finePointsNorthing = self.interpolate_UTM(i, relativeEastings, relativeNorthings, numberOfCoarsePoints)

            eastingInterpolatedPositions.extend(finePointsEasting)
            northingInterpolatedPositions.extend(finePointsNorthing)

        while not rospy.is_shutdown():
            path = Path()

            for i in range(len(eastingInterpolatedPositions)):
                # # Attempting to add points directly in one line without creating point object first
                # path.poses.append(path.poses[i].pose.position.x = 0.0) # finePointsX[i]
                # path.poses[i].pose.position.y = 0.0 # finePointsY[i]

                currentPoseStampMsg = PoseStamped()
                h = Header()

                h.stamp = rospy.Time.now()
                h.seq = i
                currentPoseStampMsg.header.seq = h.seq
                currentPoseStampMsg.header.stamp = h.stamp

                currentPoseStampMsg.pose.position.x = eastingInterpolatedPositions[i] 
                currentPoseStampMsg.pose.position.y = northingInterpolatedPositions[i] 

                path.poses.append(currentPoseStampMsg)
            
            path_publisher.publish(path)
            rospy.loginfo("Published Path with %d steps", i+1)
            rate.sleep()

def main():
    rospy.init_node('interpolation_node', anonymous = True)

    chosenHeight = 30.0

    # From https://www.maps.ie/coordinates.html at SJSU
    filePath = rospy.get_param("~file_path")
    inputLatitudes, inputLongitudes, inputHeights = gps_parser.read_file_coarse_points(filePath, chosenHeight)
    # print("\ninputLatitudes: {}\ninputLongitudes: {}\ninputHeights: {}".format(inputLatitudes, inputLongitudes, inputHeights))
    
    ##### ECEF #####
    interpolatorECEF = PathInterpolatorECEF(inputLatitudes, inputLatitudes, inputHeights, chosenHeight)

    ##### UTM #####
    # interpolatorUTM = PathInterpolatorUTM(inputLatitudes, inputLongitudes)
    
    try:
        interpolatorECEF.interpolation_publish_ECEF()
        # interpolatorUTM.interpolation_publish_UTM()
    except rospy.ROSInterruptException:
        pass

if __name__ == '__main__':
    main()

