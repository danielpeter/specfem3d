#!/usr/bin/env python
#
# script to setup topography for a given region
#
# required python modules:
#   - utm       - version 0.4.2
#   - elevation - version 1.0.5
#
# required external packages:
#   - GMT       - version 5.4.2
#   - gdal      - version 2.2.3
#
from __future__ import print_function

import os
import sys
import subprocess
import math
import datetime
import numpy

## elevation package
# see: https://github.com/bopen/elevation
#      http://elevation.bopen.eu/en/stable/
# install by: > sudo pip install elevation
try:
    import elevation
except:
    print("Error importing module `elevation`")
    print("install by: > pip install -U elevation")
    sys.exit(1)

## elevation
# check
elevation.util.selfcheck(elevation.TOOLS)

## UTM zones
# see: https://github.com/Turbo87/utm
# install by: > sudo pip install utm
try:
    import utm
except:
    print("Error importing module `utm`")
    print("install by: > pip install -U utm")
    sys.exit(1)

## DEM analysis (slope, topographic wetness index, ..)
# http://conference.scipy.org/proceedings/scipy2015/pdfs/mattheus_ueckermann.pdf
# install by: > sudo pip install pyDEM


## GMT
## http://gmt.soest.hawaii.edu
## install by: > sudo apt install gmt
## setup gmt functions by:
## > source /usr/share/gmt/tools/gmt_functions.sh
try:
    cmd = 'gmt --version'
    print("> ",cmd)
    version = subprocess.check_output(cmd, shell=True)
except:
    print("Error using `gmt`")
    print("install by: > sudo apt install gmt")
    sys.exit(1)
# avoid bytes string issues with strings like b'Hello', converts to text string
if isinstance(version, (bytes, bytearray)): version = version.decode("utf-8")
version = version.strip()
print("GMT version: %s" % (version))
print("")
# get version numbers for later (grdconvert command format changes between version 5.3 and 5.4)
elem = version.split(".")
gmt_major = int(elem[0])
gmt_minor = int(elem[1])

# GMT python interface
# todo: not used yet, calling gmt commands directly as shell commands...
#
#try:
#    import pygmt
#except:
#    print("Error importing module `pygmt`")
#    print("install by: > pip install -U pygmt")
#    sys.exit(1)


## GDAL/OGR
## https://www.gdal.org
try:
    cmd = 'gdalinfo --version'
    print("> ",cmd)
    version = subprocess.check_output(cmd, shell=True)
except:
    print("Error using `gdalinfo`")
    print("install by: > sudo apt install gdal-bin")
    sys.exit(1)
# avoid bytes string issues with strings like b'Hello', converts to text string
if isinstance(version, (bytes, bytearray)): version = version.decode("utf-8")
version = version.strip()
print("GDAL version: %s" % (version.strip()))
print("")

# GDAL python interface
# todo: not used yet, calling gdal commands directly as shell commands...
#
#try:
#    from osgeo import gdal
#except:
#    print("Error importing module `gdal`")
#    print("install by: > pip install -U gdal")
#    sys.exit(1)


#########################################################################
## USER PARAMETERS

## SRTM data
# type: 'low' == SRTM 90m / 'high' == SRTM 30m / else e.g. 'etopo' == topo30 (30-arc seconds)
SRTM_type = 'low'

## GMT grid sampling (in degrees)
# to convert increment to km: incr_dx * math.pi/180.0 * 6371.0 -> 1 degree = 111.1949 km
# sampling coarse (~5.5km)
#incr_dx = 0.05
# sampling fine (~1.1km)
#incr_dx = 0.01
# sampling fine (~500m)
incr_dx = 0.0045
# sampling fine (~110m)
#incr_dx = 0.001

# second shifted topography
use_topo_shifted = False

# topography shift for 2nd interface (shifts original topography downwards)
toposhift = 8000.0

# scaling factor for topography variations
toposcale = 0.1

## local data directory
datadir = 'topo_data'

# AVS boundaries file, add selected country borders
gmt_country = ''  # for Switzerland: '-ECH'

#########################################################################

# globals
utm_zone = 0
gmt_region = ""
projMerc = 'UTM'
use_moon_ltm = False      # for moon topography outputs
clean_out_files = False   # by default, keep intermediate file outputs

def get_topo_DEM(region,filename_path,res='low'):
    """
    downloads and creates tif-file with elevation data from SRTM 1-arc second or SRTM 3-arc seconds
    """
    # check
    if len(filename_path) == 0:
        print("error invalid filename",filename_path)
        sys.exit(1)

    # region format: #lon_min #lat_min #lon_max #lat_max (left bottom right top) in degrees
    # for example: region = (12.35, 41.8, 12.65, 42.0)
    print("region:")
    print("  longitude min/max = ",region[0],"/",region[2],"(deg)")
    print("  latitude  min/max = ",region[1],"/",region[3],"(deg)")
    print("")

    # earth radius
    earth_radius = 6371000.0
    # earth circumference
    earth_d = 2.0 * 3.14159 * earth_radius # in m ~ 40,000 km
    # lengths
    length_deg = earth_d * 1./360 # length of 1 degree ~ 111 km
    length_arcsec = length_deg * 1.0/3600 # length of 1 arcsecond ~ 30.89 m

    # range / lengths (in km)
    range_lon = region[2]-region[0] # in degreee
    range_lat = region[3]-region[1]
    length_lon = range_lon * length_deg / 1000.0 # in km
    length_lat = range_lat * length_deg / 1000.0
    print("  longitude range: ",length_lon,"(km)")
    print("  latitude  range: ",length_lat,"(km)")
    print("")

    # maximum height of earth curvature
    # e.g., http://earthcurvature.com
    #
    #             ***
    #          *** | ***
    #       ***  h |    ***
    #    A**-------|-------**B       curvature height (h) between point A and B
    #
    # formula:  alpha = (A + B)/2            mid-distance (in degree) as angle
    #           h = R * ( 1 - cos(alpha) )   with R = earth radius 6371.0 km, assuming spherical earth
    alpha = 0.5 * max(range_lon,range_lat)
    alpha = alpha * math.pi/180.0 # in rad
    h = earth_radius * (1.0 - math.cos(alpha) )
    print("  maximum Earth curvature height = ",h,"(m)")
    print("")

    # resolution
    if res == 'low':
        product = 'SRTM3'
        length = 3.0 * length_arcsec
    else:
        product = 'SRTM1'
        length = length_arcsec

    print("resolution: ",res,product)
    print("  step length: ",length,"(m)")
    print("")
    print("elevation module:")
    elevation.info(product=product)
    print("")

    # tiles
    if res == 'low':
        ilon,ilat = elevation.datasource.srtm3_tile_ilonlat(region[0],region[1])
        if ilon < 0 or ilat < 0:
            print("invalid tile number: ",ilon,ilat,"please check if lon/lat order in your input is correct")
            sys.exit(1)
        tiles = list(elevation.datasource.srtm3_tiles_names(region[0],region[1],region[2],region[3]))
    else:
        ilon,ilat = elevation.datasource.srtm1_tile_ilonlat(region[0],region[1])
        if ilon < 0 or ilat < 0:
            print("invalid tile number: ",ilon,ilat,"please check if lon/lat order in your input is correct")
            sys.exit(1)
        tiles = list(elevation.datasource.srtm1_tiles_names(region[0],region[1],region[2],region[3]))
    print("tiles:",len(tiles))
    for name in tiles:
        print("  ",name)
    print("")

    # note: in case elevation fails to download files, check in folder:
    #       /opt/local/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/site-packages/elevation/datasource.py
    #       SRTM 3 files have new address: http://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/tiff
    #       test with:
    #       > curl -s -o srtm_16_09.zip.html http://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/tiff/srtm_16_09.zip

    # get data, bounds: left bottom right top
    print("getting topography DEM file:")
    print("  region : ",region)
    print("  path   : ",filename_path)
    print("  product: ",product)
    elevation.clip(bounds=region,output=filename_path,product=product)

    # cleans cache ( ~/Library/Caches/elevation/)
    elevation.clean(product=product)

    # check
    if not os.path.isfile(filename_path):
        print("error getting topo DEM file: ",filename_path)
        sys.exit(1)

    print("  done")
    print("")


#
#-----------------------------------------------------------------------------
#

def get_topo(lon_min,lat_min,lon_max,lat_max):
    """
    gets topography data for given region and stores it in file ptopo.xyz
    """
    global incr_dx
    global SRTM_type
    global gmt_region
    global utm_zone
    global use_moon_ltm,projMerc
    global clean_out_files

    # region format: #lon_min #lat_min #lon_max #lat_max (left bottom right top) in degrees
    # for example: region = (12.35, 41.8, 12.65, 42.0)
    region = (lon_min, lat_min, lon_max, lat_max)

    print("*******************************")
    print("get topo:")
    print("*******************************")
    print("  region: ",region)
    print("")

    # enlarge data region slightly to fit desired locations
    # note: xmeshfem will determine the min/max UTM coordinates of the given lat/lon region
    #       and build mesh element coordinates by adding element steps from these UTM coordinates.
    #       to assign topography elevation, it will then convert the UTM coordinates back to lat/lon for reading topo interfaces.
    # get corner UTM coordinates
    utm_xmin = float('inf') # hugeval
    utm_xmax = float('-inf')
    utm_ymin = float('inf')
    utm_ymax = float('-inf')
    # define corner points
    corners = [ (lon_min,lat_min), (lon_min,lat_max), (lon_max,lat_min), (lon_max,lat_max) ]
    for lon,lat in corners:
          if use_moon_ltm:
              # converts to LTM x/y
              x,y = geo2ltm(lon,lat,utm_zone,iway=2)   # iway==2 LONGLAT2UTM
          else:
              # converts to UTM x/y
              x,y = geo2utm(lon,lat,utm_zone,iway=2)   # iway==2 LONGLAT2UTM
          # determines min/max
          if x < utm_xmin: utm_xmin = x
          if x > utm_xmax: utm_xmax = x
          if y < utm_ymin: utm_ymin = y
          if y > utm_ymax: utm_ymax = y

    print(f"  corner {projMerc} coordinates: X min/max = {utm_xmin} / {utm_xmax}")
    print(f"                          Y min/max = {utm_ymin} / {utm_ymax}")
    print("")

    # check
    if utm_xmin == float('inf') or utm_xmax == float('-inf') or utm_ymin == float('inf') or utm_ymax == float('-inf'):
        print(f"Error: could not determine {projMerc} min/max range")
        sys.exit(1)

    # converts back to get extended region
    ext_lon_min = float('inf') # hugeval
    ext_lon_max = float('-inf')
    ext_lat_min = float('inf')
    ext_lat_max = float('-inf')
    # define corners
    utm_corners = [ (utm_xmin,utm_ymin), (utm_xmin,utm_ymax),(utm_xmax,utm_ymin),(utm_xmax,utm_ymax) ]
    for x,y in utm_corners:
          if use_moon_ltm:
              # converts to LTM x/y
              lon,lat = geo2ltm(x,y,utm_zone,iway=1)   # iway==1 UTM2LONGLAT
          else:
              # converts to lon/lat
              lon,lat = geo2utm(x,y,utm_zone,iway=1)   # iway==1 UTM2LONGLAT
          # determines min/max
          if lon < ext_lon_min: ext_lon_min = lon
          if lon > ext_lon_max: ext_lon_max = lon
          if lat < ext_lat_min: ext_lat_min = lat
          if lat > ext_lat_max: ext_lat_max = lat

    # fixed margin extension
    #eps = 0.0001
    #ext_lon_min = lon_min - eps; ext_lat_min = lat_min - eps; ext_lon_max = lon_max + eps; ext_lat_max = lat_max + eps

    print(f"  extended region       : lon min/max = {ext_lon_min} / {ext_lon_max}")
    print(f"                          lat min/max = {ext_lat_min} / {ext_lat_max}")
    print("")

    # round up/down to first digit
    def my_ceil(a,precision=1):
        return round(a + 0.5 * 10**(-precision),precision)
    def my_floor(a,precision=1):
        return round(a - 0.5 * 10**(-precision),precision)
    def get_digits_after_decimal():
        # determines number of digits for rounding precision
        # based on given arguments
        str_lon_min = sys.argv[1]
        str_lat_min = sys.argv[2]
        str_lon_max = sys.argv[3]
        str_lat_max = sys.argv[4]
        # example: "89.1" -> precision = 1
        #          "89.15" -> precision = 2
        precision = 1
        if "." in str_lon_min: precision = max(len(str_lon_min.split(".")[1]),precision)
        if "." in str_lat_min: precision = max(len(str_lat_min.split(".")[1]),precision)
        if "." in str_lon_max: precision = max(len(str_lon_max.split(".")[1]),precision)
        if "." in str_lat_max: precision = max(len(str_lat_max.split(".")[1]),precision)
        return precision

    # gets rounding precision
    precision = get_digits_after_decimal()

    region_extended = ( my_floor(ext_lon_min,precision),
                        my_floor(ext_lat_min,precision),
                        my_ceil(ext_lon_max,precision),
                        my_ceil(ext_lat_max,precision) )

    print("  region extended: ",region_extended)
    print("")

    ## gmt
    # region format: e.g. -R123.0/132.0/31.0/40.0
    #gmt_region = '-R' + str(lon_min) + '/' + str(lon_max) + '/' + str(lat_min) + '/' + str(lat_max)
    # uses extended region
    gmt_region = '-R' + str(region_extended[0]) + '/' + str(region_extended[2]) + '/' + str(region_extended[1]) + '/' + str(region_extended[3])

    # sampling fine (~1.1km)
    gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)

    # current directory
    dir = os.getcwd()

    name = 'ptopo-DEM.tif'
    filename = dir + '/' + name

    print("  current directory:",dir)
    print("  topo file name   :",filename)
    print("")

    ## get topo file
    if SRTM_type == 'low' or SRTM_type == 'high':
        # SRTM data
        get_topo_DEM(region_extended,filename,res=SRTM_type)
    elif SRTM_type == 'etopo2' \
      or SRTM_type == 'topo30' \
      or SRTM_type == 'srtm30s' \
      or SRTM_type == 'srtm_1km' \
      or SRTM_type == 'topo15' \
      or SRTM_type == 'srtm15s' \
      or SRTM_type == 'srtm_500m' \
      or SRTM_type == 'topo3' \
      or SRTM_type == 'srtm3s' \
      or SRTM_type == 'srtm_100m' \
      or SRTM_type == 'topo1' \
      or SRTM_type == 'srtm1s' \
      or SRTM_type == 'srtm_30m' :
        # gmt grid
        gridfile = 'ptopo-DEM.grd'
        if gmt_major >= 6:
            # new version uses grdcut and earth relief grids from server
            # http://gmt.soest.hawaii.edu/doc/latest/datasets.html
            if SRTM_type == 'etopo2':
                # ETOPO2 (2-arc minutes)
                cmd = 'gmt grdcut @earth_relief_02m ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.05 # coarse (~5.5km)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I2m -G' + gridfile
            elif SRTM_type == 'etopo1':
                # ETOPO1 (1-arc minute)
                cmd = 'gmt grdcut @earth_relief_01m ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.01 # fine (~1.1km)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I0.00833 -G' + gridfile
            elif SRTM_type == 'topo30' or SRTM_type == 'srtm30s' or SRTM_type == 'srtm_1km':
                # srtm 30s (30-arc seconds) ~ 1km resolution
                cmd = 'gmt grdcut @earth_relief_30s ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.009 # fine (~1km)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I0.00833 -G' + gridfile
            elif SRTM_type == 'topo15' or SRTM_type == 'srtm15s' or SRTM_type == 'srtm_500m':
                # srtm 15s (15-arc seconds) ~ 0.5km resolution
                cmd = 'gmt grdcut @earth_relief_15s ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.0045 # fine (~500m)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I0.004166 -G' + gridfile
            elif SRTM_type == 'topo3' or SRTM_type == 'srtm3s' or SRTM_type == 'srtm_100m':
                # srtm 3s (3-arc seconds) ~ 100m resolution
                cmd = 'gmt grdcut @earth_relief_03s ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.00083 # fine (~100m)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I0.0008 -G' + gridfile
            elif SRTM_type == 'topo1' or SRTM_type == 'srtm1s' or SRTM_type == 'srtm_30m':
                # srtm 1s (1-arc seconds) ~ 30m resolution
                cmd = 'gmt grdcut @earth_relief_01s ' + gmt_region + ' -G' + gridfile
                # interpolation?
                incr_dx = 0.0003 # fine (~30m)
                gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
                #cmd += '; gmt blockmean ' + gridfile + ' -I0.0003 -G' + gridfile
            else:
                print("Error invalid SRTM_type " + SRTM_type)
                sys.exit(1)
        else:
            # older version < 6, like 5.4 ...
            # or use grdraster for lower resolution
            if SRTM_type == 'etopo2':
                # ETOPO2 (2-arc minutes)
                cmd = 'gmt grdraster ETOPO2 ' + gmt_region + ' -I2m -G' + gridfile
            elif SRTM_type == 'topo30':
                # topo30 (30-arc seconds) ~ 1km resolution
                cmd = 'gmt grdraster topo30 ' + gmt_region + ' -I0.00833 -G' + gridfile
            elif SRTM_type == 'srtm_500m':
                # srtm 500m resolution
                cmd = 'gmt grdraster srtm_500m ' + gmt_region + ' -I0.004166 -G' + gridfile
            else:
                print("Error invalid SRTM_type " + SRTM_type)
                sys.exit(1)
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)

        print("")
        # convert gmt grid-file to gdal GTiff for shading
        if gmt_major >= 5 and gmt_minor >= 4:
            # version > 5.4
            cmd = 'gmt grdconvert ' + gridfile + ' -G' + filename + '=gd:Gtiff'
        else:
            # older version < 5.3
            cmd = 'gmt grdconvert ' + gridfile + ' ' + filename + '=gd:Gtiff'
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")
    elif SRTM_type == 'moon' \
      or SRTM_type == 'moon2m' \
      or SRTM_type == 'moon15' \
      or SRTM_type == 'moon15s':
        # gmt grid
        gridfile = 'ptopo-DEM.grd'
        # new version uses grdcut and earth relief grids from server
        # http://gmt.soest.hawaii.edu/doc/latest/datasets.html
        if SRTM_type == 'moon' or SRTM_type == 'moon2m':
            # Moon (2-arc minutes)
            cmd = 'gmt grdcut @moon_relief_02m ' + gmt_region + ' -G' + gridfile
            incr_dx = 0.05
            gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
        elif SRTM_type == 'moon15' or SRTM_type == 'moon15s':
            # Moon 15s (15-arc seconds)
            cmd = 'gmt grdcut @moon_relief_15s ' + gmt_region + ' -G' + gridfile
            incr_dx = 0.0045
            gmt_interval = '-I' + str(incr_dx) + '/' + str(incr_dx)
        else:
            print("Error invalid SRTM_type " + SRTM_type)
            sys.exit(1)
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")
        # convert gmt grid-file to gdal GTiff for shading
        # version > 5.4
        cmd = 'gmt grdconvert ' + gridfile + ' -G' + filename + '=gd:Gtiff'
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")
    else:
        print("Error invalid SRTM_type " + SRTM_type)
        sys.exit(1)

    print("  GMT:")
    print("  region  : ",gmt_region)
    print("  interval: ",gmt_interval)
    print("")

    # topography info
    cmd = 'gmt grdinfo ' + filename
    print("  topography file info:")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # hillshade
    gif_file = filename + '.hillshaded.gif'
    cmd = 'gdaldem hillshade ' + filename + ' ' + gif_file + ' -of GTiff'
    print("  hillshade figure:")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # defines model region
    ## resampling
    # even sampling
    # note: the region might be slightly off, then this resampling can lead to wrong values.
    #       check output of gmt command and see what region it is using
    #
    # e.g. grdsample etopo.grd $region -I$dx/$dx -Getopo.sampled.grd
    #cmd = 'grdsample ' + filename + ' ' + gmt_region + ' ' + gmt_interval + ' -Getopo.sampled.grd'
    # uses region specified from grid file
    gridfile = 'ptopo.sampled.grd'
    cmd = 'gmt grdsample ' + filename + ' ' + gmt_interval + ' -G' + gridfile
    print("  resampling topo data")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    cmd = 'gmt grdinfo ' + gridfile
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # converts to xyz format
    xyz_file = 'ptopo.xyz'
    cmd = 'gmt grd2xyz ' + gridfile + ' > ' + xyz_file
    print("  converting to xyz")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # gif
    cmd = 'gdaldem hillshade ' + xyz_file + ' ' + xyz_file + '.hillshaded1.gif -of GTiff'
    print("  creating gif-image ...")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # mesh interpolation (only needed when different gridding interval)
    mean_file = 'ptopo.mean.xyz'
    # note: can lead to problems, if mean interval is similar to grid interval
    #cmd = 'gmt blockmean ' + gmt_interval + ' ptopo.xyz ' + gmt_region + ' > ptopo.mean.xyz'
    gmt_interval2 = '-I' + str(incr_dx/10.0) + '/' + str(incr_dx/10.0)

    cmd = 'gmt blockmean ' + gmt_interval2 + ' ' + xyz_file + ' ' + gmt_region + ' > ' + mean_file
    print("  mesh interpolation")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    cmd = 'mv -v ptopo.xyz ptopo.xyz.org; mv -v ptopo.mean.xyz ptopo.xyz'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # gif
    cmd = 'gdaldem hillshade ' + xyz_file + ' ' + xyz_file + '.hillshaded2.gif -of GTiff'
    print("  creating gif-image ...")
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # map
    plot_map(gmt_region)

    # clean
    if clean_out_files:
        # cleanup
        cmd = 'rm -f ' + 'ptopo.xyz.org' + ';'
        cmd += 'rm -f ' + 'ptopo-DEM.grd' + ';'
        if filename: cmd += 'rm -f ' + filename + ';'
        if gif_file: cmd += 'rm -f ' + gif_file + ';'
        if gridfile: cmd += 'rm -f ' + gridfile + ';'
        if xyz_file: cmd += 'rm -f ' + xyz_file + '.hillshaded1.gif' + ';'
        if xyz_file: cmd += 'rm -f ' + xyz_file + '.hillshaded2.gif' + ';'
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")

    return xyz_file

#
#-----------------------------------------------------------------------------
#

def plot_map(gmt_region,gridfile="ptopo.sampled.grd"):
    global datadir
    global clean_out_files

    print("*******************************")
    print("plotting map ...")
    print("*******************************")

    # current directory
    dir = os.getcwd()
    print("  current directory:",dir)
    print("")

    #cmd = 'cd ' + datadir + '/' + ';'
    #status = subprocess.call(cmd, shell=True)
    #check_status(status)

    ps_file = "map.ps"
    pdf_file = "map.pdf"

    # gmt plotting
    cmd = 'gmt pscoast ' + gmt_region + ' -JM6i -Dh -G220 -P -K > ' + ps_file + ';'
    # topography shading
    #makecpt -Cgray -T0/1/0.01 > topo.cpt
    #cmd += 'makecpt -Cglobe -T-2500/2500/100 > topo.cpt' + ';'
    #cmd += 'makecpt -Cterra -T-2500/2500/100 > ptopo.cpt' + ';'
    #cmd += 'makecpt -Ctopo -T-2500/2500/100 > ptopo.cpt' + ';'
    cmd += 'gmt makecpt -Crelief -T-2500/2500/100 > ptopo.cpt' + ';'
    cmd += 'gmt grdgradient ' + gridfile + ' -Nt1 -A45 -Gptopogradient.grd -V' + ';'
    cmd += 'gmt grdimage ' + gridfile + ' -Iptopogradient.grd -J -R -Cptopo.cpt -V -O -K >> ' + ps_file + ';'
    cmd += 'gmt pscoast -R -J -Di -N1/1.5p,gray40 -A1000 -W1 -O -K >> ' + ps_file + ';'
    cmd += 'gmt psbasemap -O -R -J -Ba1g1:"Map": -P -V  >> ' + ps_file + ';'
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("  map plotted in file: ",ps_file)

    # imagemagick converts ps to pdf
    cmd = 'convert ' + ps_file + ' ' + pdf_file
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("  map plotted in file: ",pdf_file)
    print("")

    # clean
    if clean_out_files:
        cmd = 'rm -f ' + 'ptopo.cpt' + ';'
        cmd += 'rm -f ' + 'ptopogradient.grd' + ';'
        if ps_file: cmd += 'rm -f ' + ps_file + ';'
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")

    return

#
#-----------------------------------------------------------------------------
#

def create_AVS_file():
    global datadir
    global utm_zone
    global gmt_region,gmt_country
    global use_moon_ltm
    global clean_out_files

    # only output borders for Earth...
    if use_moon_ltm: return

    print("*******************************")
    print("creating AVS border file ...")
    print("*******************************")

    # current directory
    dir = os.getcwd()
    #print("current directory:",dir)
    #print("")

    # GMT segment file
    name = "map_segment.dat"
    if len(gmt_country) > 0:
        # uses country border (w/ full resolution -Df)
        cmd = 'gmt pscoast ' + gmt_region + ' ' + gmt_country + ' -Df -M > ' + name + ';'
    else:
        # shore lines (w/ high resolution -Dh)
        cmd = 'gmt pscoast ' + gmt_region + ' -W -Dh -M > ' + name + ';'
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("  GMT segment file plotted in file: ",name)

    # note: GMT segment file has format
    # > Shore Bin # .., Level ..
    #   lon1 lat1
    #   lon2 lat2
    # > Shore Bin # .., Level ..
    #   ..

    print("  Getting boundaries from file %s ..." % name)

    # reads gmt boundary file
    with open(name,'r') as f:
        content = f.readlines()

    if len(content) == 0:
        print("")
        print("  INFO: no boundaries in file")
        print("")
        return

    # counts segments and points
    numsegments = 0
    numpoints = 0
    for line in content:
        if ">" in line:
            # new segment
            numsegments += 1
        else:
            # point
            numpoints += 1

    print("  There are %i contours" % numsegments)
    print("  There are %i data points" % numpoints)

    # read the GMT file to get the number of individual line segments
    currentelem = 0
    previous_was_comment = 1
    for line in content:
        line = line.strip()
        #debug
        #print("currentelem %i %i %s" % (currentelem,previous_was_comment,line))
        # skip comment lines
        if line[0:1] == "#": continue
        # get line marker (comment in file)
        if ">" in line:
            previous_was_comment = 1
        else:
            if previous_was_comment == 0: currentelem += 1
            previous_was_comment = 0

    num_individual_lines = currentelem
    print("  There are %i individual line segments" % num_individual_lines)

    print("")
    print("converting to .inp format:")

    avsfile = "AVS_boundaries_utm.inp"
    with open(avsfile,'w') as f:
        # write header for AVS (with point data)
        f.write("%i %i 1 0 0\n" % (numpoints,num_individual_lines))

        # read the GMT file to get the points
        currentpoint = 0
        for line in content:
            line = line.strip()
            # skip comment lines
            if line[0:1] == "#": continue

            #   get point only if line is not a comment
            if ">" not in line:
                currentpoint += 1
                elem = line.split()

                ## global lon/lat coordinates
                # longitude is the number before the white space
                lon = float(elem[0])
                # latitude is the number after the white space
                lat = float(elem[1])

                # perl example
                # convert geographic latitude to geocentric colatitude and convert to radians
                # $pi = 3.14159265;
                # $theta = $pi/2. - atan2(0.99329534 * tan($latitude * $pi / 180.),1) ;
                # $phi = $longitude * $pi / 180. ;
                # compute the Cartesian position of the receiver (ignore ellipticity for AVS)
                # assume a sphere of radius one
                # $r_target = 1. ;
                ## DK DK make the radius a little bit bigger to make sure it is
                ## DK DK correctly superimposed to the mesh in final AVS figure
                # $r_target = 1.015 ;
                # $x_target = $r_target*sin($theta)*cos($phi) ;
                # $y_target = $r_target*sin($theta)*sin($phi) ;
                # $z_target = $r_target*cos($theta) ;

                ## UTM
                # utm_x is the number before the white space
                #utm_x = float(elem[0])
                # utm_y is the number after the white space
                #utm_y = float(elem[1])
                #x_target = utm_x
                #y_target = utm_y

                # converts to UTM x/y
                x,y = geo2utm(lon,lat,utm_zone)

                # location
                x_target = x
                y_target = y
                z_target = 0.0     # assuming models use depth in negative z-direction

                f.write("%i %f %f %f\n" % (currentpoint,x_target,y_target,z_target))

        # read the GMT file to get the lines
        currentline = 0
        currentelem = 0
        currentpoint = 0
        previous_was_comment = 1
        for line in content:
            line = line.strip()
            # skip comment lines
            if line[0:1] == "#": continue
            #   get line marker (comment in file)
            if ">" in line:
                # check if previous was line was also a segment
                # for example: there can be empty segment lines
                #  > Shore Bin # 4748, Level 1
                #  > Shore Bin # 4748, Level 1
                #  > Shore Bin # 4748, Level 1
                #  136.117036698   36.2541237507
                #  136.121248188   36.2533302815
                #  ..
                if currentline > 0 and previous_was_comment :
                    continue
                else:
                    currentline += 1
                    currentpoint += 1
                    previous_was_comment = 1
                #print("processing contour %i named %s" % (currentline,line))
            else:
                if previous_was_comment == 0:
                    previouspoint = currentpoint
                    currentelem  +=1
                    currentpoint  +=1
                    # new line
                    f.write("%i %i line %i %i\n" % (currentelem,currentline,previouspoint,currentpoint))
                previous_was_comment = 0

        # dummy variable names
        f.write(" 1 1\n")
        f.write(" Zcoord, meters\n")
        # create data values for the points
        for currentpoint in range(1,numpoints+1):
            f.write("%i 255.\n" % (currentpoint))

    # check
    if numpoints != currentpoint:
        print("  WARNING:")
        print("    possible format corruption: total number of points ",numpoints," should match last line point id ",currentpoint)
        print("")

    print("  see file: %s" % avsfile)
    print("")

    # clean
    if clean_out_files:
        if name:
            cmd = 'rm -f ' + name + ';'
            print("  > ",cmd)
            status = subprocess.call(cmd, shell=True)
            check_status(status)
            print("")

    return

#
#-----------------------------------------------------------------------------
#

def topo_extract(filename):
    global use_topo_shifted,toposhift,toposcale

    # ./topo_extract.sh ptopo.mean.xyz
    #cmd = './topo_extract.sh ptopo.mean.xyz'
    print("*******************************")
    print("extracting interface data for xmeshfem3D ...")
    print("*******************************")

    if not filename:
        print("Error: empty file name")
        sys.exit(1)

    file1 = filename + '.1.dat'

    ## shift/downscale topography
    if use_topo_shifted:
        print("  topo shift   = ",toposhift,"(m)")
        print("  scale factor = ",toposcale)
        print("")
        file2 = filename + '.2.dat'

    # statistics
    cmd = 'gmt gmtinfo ' + filename
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # cleanup
    cmd = 'rm -f ' + file1 + ';'
    if use_topo_shifted:
        if file2: cmd += 'rm -f ' + file2 + ';'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # reads in lon/lat/elevation
    print("  reading file " + filename + " ...")
    data = numpy.loadtxt(filename)
    #debug
    #print(data)
    elevation = data[:,2]

    # extracts only elevation data
    with open(file1,'w') as f:
        for i in range(0,len(elevation)):
            f.write("%f\n" % (elevation[i]) )

    print("")
    print("  check: ",file1)

    # shifts topography surface down
    if use_topo_shifted:
        with open(file2,'w') as f:
            for i in range(0,len(elevation)):
                f.write("%f\n" % (elevation[i] * toposcale - toposhift) )
        print("  check: ",file2)

    print("")

    cmd = 'gmt gmtinfo ' + file1 + ';'
    if use_topo_shifted:
        cmd += 'gmt gmtinfo ' + file2 + ';'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    print("  number of points along x (NXI) and y (NETA):")
    x0 = data[0,0]
    y0 = data[0,1]
    i0 = 1
    nx = 0; ny = 0
    xmin = x0; xmax = x0
    ymin = y0; ymax = y0

    for i in range(1,len(data)):
      x = data[i,0]
      y = data[i,1]
      dx = x - x0
      x0 = x
      if x < xmin: xmin = x
      if x > xmax: xmax = x
      if y < ymin: ymin = y
      if y > ymax: ymax = y
      if dx < 0.0:
          ii = i + 1
          if nx > 0 and ii - i0 != nx:
              print("  non-regular nx: ",nx,ii-i0,"on line ",i+1)
          nx = ii - i0
          ny += 1
          deltay = y - y0
          y0 = y
          i0 = ii
      else:
          deltax = dx

    ii = len(data) + 1
    if nx > 0 and ii - i0 != nx:
        print("  non-regular nx: ",nx,ii-i0,"on line ",ii)
    nx = ii - i0
    ny += 1
    print("  --------------------------------------------")
    print("  NXI  = ",nx)
    print("  NETA = ",ny)
    print("  xmin/xmax = ",xmin,xmax)
    print("  ymin/ymax = ",ymin,ymax)
    print("  deltax = ",deltax,"average = ",(xmax-xmin)/(nx-1))
    print("  deltay = ",deltay,"average = ",(ymax-ymin)/(ny-1))
    print("  --------------------------------------------")
    print("")

    interface_region = ( xmin, xmax, ymin, ymax )

    return nx,ny,deltax,deltay,interface_region



#
#-----------------------------------------------------------------------------
#

def check_status(status):
    if status != 0:
        print("error: status returned ",status)
        sys.exit(status)
    return

#
#-----------------------------------------------------------------------------
#

def update_Mesh_Par_file(dir,lon_min,lat_min,lon_max,lat_max,nx,ny,dx,dy,interface_region,xyz_file):
    global datadir
    global utm_zone
    global use_topo_shifted

    # change working directory back to DATA/
    path = dir + '/' + 'DATA/meshfem3D_files/'

    # checks if DATA/meshfem3D_files/ folder available
    if not os.path.isdir(path):
        print("#")
        print("# Info: DATA/meshfem3D_files/ folder not found in current directory,")
        print("#       will continue without modifying Mesh_Par_file ...")
        print("# ")
        return

    # updates Mesh_Par_file
    os.chdir(path)

    print("*******************************")
    print("updating Mesh_Par_file ...")
    print("*******************************")
    print("  working directory: ",os.getcwd())
    print("  Mesh_Par_file region min lon/lat      : ",lon_min,"/",lat_min)
    print("                       max lon/lat      : ",lon_max,"/",lat_max)
    print("")

    cmd = 'echo "";'
    cmd += 'echo "setting lat min/max = ' + str(lat_min) + ' ' + str(lat_max) + '";'
    cmd += 'echo "        lon min/max = ' + str(lon_min) + ' ' + str(lon_max) + '";'
    cmd += 'echo "        utm zone = ' + str(utm_zone) + '";'
    cmd += 'echo "";'
    cmd += 'sed -i "s:^LATITUDE_MIN .*:LATITUDE_MIN                    = ' + str(lat_min) + ':" Mesh_Par_file' + ';'
    cmd += 'sed -i "s:^LATITUDE_MAX .*:LATITUDE_MAX                    = ' + str(lat_max) + ':" Mesh_Par_file' + ';'
    cmd += 'sed -i "s:^LONGITUDE_MIN .*:LONGITUDE_MIN                   = ' + str(lon_min) + ':" Mesh_Par_file' + ';'
    cmd += 'sed -i "s:^LONGITUDE_MAX .*:LONGITUDE_MAX                   = ' + str(lon_max) + ':" Mesh_Par_file' + ';'
    cmd += 'sed -i "s:^UTM_PROJECTION_ZONE .*:UTM_PROJECTION_ZONE             = ' + str(utm_zone) + ':" Mesh_Par_file' + ';'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # interfaces.dat file
    interface_lon_min = interface_region[0]   # xmin
    interface_lon_max = interface_region[1]   # xmax
    interface_lat_min = interface_region[2]   # ymin
    interface_lat_max = interface_region[3]   # ymax

    print("  interfaces region min lon/lat      : ",interface_lon_min,"/",interface_lat_min)
    print("                    max lon/lat      : ",interface_lon_max,"/",interface_lat_max)
    print("")

    nxi = nx
    neta = ny

    dxi = dx
    deta = dy

    if dx < 0.0:
        # negative increment, starts from maximum location
        lon = interface_lon_max
    else:
        # positive increment, starts from minimum location
        lon = interface_lon_min

    if dy < 0.0:
        # negative increment, starts from maximum location
        lat = interface_lat_max
    else:
        # positive increment, starts from minimum location
        lat = interface_lat_min

    # format:
    # #SUPPRESS_UTM_PROJECTION #NXI #NETA #LONG_MIN #LAT_MIN #SPACING_XI #SPACING_ETA
    # .false. 901 901   123.d0 40.0d0 0.01 -0.01
    cmd = 'echo "";'
    cmd += 'echo "interfaces nxi = ' + str(nxi) + ' neta = ' + str(neta) + '";'
    cmd += 'echo "           long = ' + str(lon) + ' lat = ' + str(lat) + '";'
    cmd += 'echo "           spacing_xi = ' + str(dxi) + ' spacing_eta = ' + str(deta) + '";'
    cmd += 'echo "";'
    line = '.false. ' + str(nxi) + ' ' + str(neta) + ' ' + str(lon) + ' ' + str(lat) + ' ' + str(dxi) + ' ' + str(deta)
    cmd += 'sed -i "s:^.false. .*:' + line + ':g" interfaces.dat' + ';'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    if not datadir:
        print("Error: empty data dir name")
        sys.exit(1)

    # link to topography files
    topodir = '../../' + datadir

    if not xyz_file:
        print("Error: empty xyz_file name")
        sys.exit(1)

    xyz_file1 = xyz_file + '.1.dat'
    cmd = 'rm -f ' + xyz_file1 + ';'
    cmd += 'ln -s ' + topodir + '/' + xyz_file1 + ';'

    if use_topo_shifted:
        xyz_file2 = xyz_file + '.2.dat'
        cmd += 'rm -f ' + xyz_file2 + ';'
        cmd += 'ln -s ' + topodir + '/' + xyz_file2 + ';'

    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    print("  file updated: %s/Mesh_Par_file" % path)
    print("")

    return

#
#-----------------------------------------------------------------------------
#


def update_Par_file(dir):
    global datadir
    global utm_zone

    # change working directory back to DATA/
    path = dir + '/' + 'DATA/'

    # checks if DATA/ folder available
    if not os.path.isdir(path):
        print("#")
        print("# Info: DATA/ folder not found in current directory,")
        print("#       will continue without modifying Par_file ...")
        print("# ")
        return

    # updates Par_file in DATA/ folder
    os.chdir(path)

    print("*******************************")
    print("updating Par_file ...")
    print("*******************************")
    print("  working directory: ",os.getcwd())
    print("  utm_zone = ",utm_zone)
    print("")

    cmd = 'sed -i "s:^UTM_PROJECTION_ZONE .*:UTM_PROJECTION_ZONE             = ' + str(utm_zone) + ':" Par_file' + ';'
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    print("  file updated: %s/Par_file" % path)
    print("")

    return


#
#----------------------------------------------------------------------------------------
#


def geo2utm(lon,lat,zone,iway=2):
    """
    from utm_geo.f90

    convert geodetic longitude and latitude to UTM, and back
    use iway = ILONGLAT2UTM for long/lat to UTM, IUTM2LONGLAT for UTM to lat/long
    a list of UTM zones of the world is available at www.dmap.co.uk/utmworld.htm
    Use zones +1 to +60 for the Northern hemisphere, -1 to -60 for the Southern hemisphere

    implicit none

    include "constants.h"

    -----CAMx v2.03

    UTM_GEO performs UTM to geodetic (long/lat) translation, and back.

    This is a Fortran version of the BASIC program "Transverse Mercator
    Conversion", Copyright 1986, Norman J. Berls (Stefan Musarra, 2/94)
    Based on algorithm taken from "Map Projections Used by the USGS"
    by John P. Snyder, Geological Survey Bulletin 1532, USDI.

    Input/Output arguments:

      rlon                  Longitude (deg, negative for West)
      rlat                  Latitude (deg)
      rx                    UTM easting (m)
      ry                    UTM northing (m)
      UTM_PROJECTION_ZONE  UTM zone
      iway                  Conversion type
                              ILONGLAT2UTM = geodetic to UTM
                              IUTM2LONGLAT = UTM to geodetic
    """
    PI      = math.pi
    degrad  = PI/180.0
    raddeg  = 180.0/PI

    # Clarke 1866
    #semimaj = 6378206.4
    #semimin = 6356583.8
    # WGS84 (World Geodetic System 1984) - default
    semimaj = 6378137.0
    semimin = 6356752.314245

    scfa    = 0.9996

    # some extracts about UTM:
    #
    # There are 60 longitudinal projection zones numbered 1 to 60 starting at 180 W.
    # Each of these zones is 6 degrees wide, apart from a few exceptions around Norway and Svalbard.
    # There are 20 latitudinal zones spanning the latitudes 80 S to 84 N and denoted
    # by the letters C to X, ommitting the letter O.
    # Each of these is 8 degrees south-north, apart from zone X which is 12 degrees south-north.
    #
    # To change the UTM zone and the hemisphere in which the
    # calculations are carried out, need to change the fortran code and recompile. The UTM zone is described
    # actually by the central meridian of that zone, i.e. the longitude at the midpoint of the zone, 3 degrees
    # from either zone boundary.
    # To change hemisphere need to change the "north" variable:
    #  - north=0 for northern hemisphere and
    #  - north=10000000 (10000km) for southern hemisphere. values must be in metres i.e. north=10000000.
    #
    # Note that the UTM grids are actually Mercators which
    # employ the standard UTM scale factor 0.9996 and set the
    # Easting Origin to 500,000;
    # the Northing origin in the southern
    # hemisphere is kept at 0 rather than set to 10,000,000
    # and this gives a uniform scale across the equator if the
    # normal convention of selecting the Base Latitude (origin)
    # at the equator (0 deg.) is followed.  Northings are
    # positive in the northern hemisphere and negative in the
    # southern hemisphere.
    north = 0.0
    east  = 500000.0

    IUTM2LONGLAT = 1
    ILONGLAT2UTM = 2

    #---------------------------------------------------------------
    # default uses conversion to UTM
    #iway = ILONGLAT2UTM

    # zone
    UTM_PROJECTION_ZONE = zone

    # lon/lat
    if iway == ILONGLAT2UTM:
        rlon = lon
        rlat = lat
        rx = 0.0
        ry = 0.0
    else:
        rx = lon
        ry = lat
        rlon = 0.0
        rlat = 0.0

    #---------------------------------------------------------------

    # save original parameters
    rlon_save = rlon
    rlat_save = rlat
    rx_save = rx
    ry_save = ry

    # define parameters of reference ellipsoid
    e2 = 1.0 - (semimin/semimaj)**2
    e4 = e2 * e2
    e6 = e2 * e4
    ep2 = e2/(1.0 - e2)

    #----- Set Zone parameters
    # zone
    lsouth = False
    if UTM_PROJECTION_ZONE < 0: lsouth = True
    zone = abs(UTM_PROJECTION_ZONE)

    cm = zone * 6.0 - 183.0       # set central meridian for this zone
    cmr = cm*degrad

    if iway == IUTM2LONGLAT:
        xx = rx
        yy = ry
        if lsouth: yy = yy - 1.e7
    else:
        dlon = rlon
        dlat = rlat

    #---- Lat/Lon to UTM conversion
    if iway == ILONGLAT2UTM:

        rlon = degrad*dlon
        rlat = degrad*dlat

        delam = dlon - cm
        if delam < -180.0: delam = delam + 360.0
        if delam > 180.0: delam = delam - 360.0

        delam = delam*degrad

        f1 = (1. - e2/4.0 - 3.0*e4/64.0 - 5.0*e6/256.0)*rlat
        f2 = 3.0*e2/8.0 + 3.0*e4/32.0 + 45.0*e6/1024.0
        f2 = f2 * math.sin(2.0*rlat)
        f3 = 15.0*e4/256.0 + 45.0*e6/1024.0
        f3 = f3 * math.sin(4.0*rlat)
        f4 = 35.0*e6/3072.0
        f4 = f4 * math.sin(6.0*rlat)
        rm = semimaj*(f1 - f2 + f3 - f4)

        if dlat == 90.0 or dlat == -90.0:
            xx = 0.0
            yy = scfa*rm
        else:
            rn = semimaj/math.sqrt(1.0 - e2*math.sin(rlat)**2)
            t = math.tan(rlat)**2
            c = ep2 * math.cos(rlat)**2
            a = math.cos(rlat) * delam

            f1 = (1.0 - t + c) * a**3/6.0
            f2 = 5.0 - 18.0*t + t**2 + 72.0*c - 58.0*ep2
            f2 = f2 * a**5/120.0
            xx = scfa*rn*(a + f1 + f2)
            f1 = a**2/2.0
            f2 = 5.0 - t + 9.0*c + 4.0*c**2
            f2 = f2*a**4/24.0
            f3 = 61.0 - 58.0*t + t**2 + 600.0*c - 330.0*ep2
            f3 = f3 * a**6/720.0
            yy = scfa*(rm + rn*math.tan(rlat)*(f1 + f2 + f3))

        xx = xx + east
        yy = yy + north

    else:
        #---- UTM to Lat/Lon conversion
        xx = xx - east
        yy = yy - north
        e1 = math.sqrt(1.0 - e2)
        e1 = (1.0 - e1)/(1.0 + e1)
        rm = yy/scfa
        u = 1.0 - e2/4.0 - 3.0*e4/64.0 - 5.0*e6/256.0
        u = rm/(semimaj*u)

        f1 = 3.0*e1/2.0 - 27.0*e1**3.0/32.0
        f1 = f1*math.sin(2.0*u)
        f2 = 21.0*e1**2/16.0 - 55.0*e1**4/32.0
        f2 = f2*math.sin(4.0*u)
        f3 = 151.0*e1**3/96.0
        f3 = f3*math.sin(6.0*u)
        rlat1 = u + f1 + f2 + f3
        dlat1 = rlat1*raddeg

        if dlat1 >= 90.0 or dlat1 <= -90.0:
            dlat1 = min(dlat1,90.0)
            dlat1 = max(dlat1,-90.0)
            dlon = cm
        else:
            c1 = ep2*math.cos(rlat1)**2
            t1 = math.tan(rlat1)**2
            f1 = 1.0 - e2*math.sin(rlat1)**2
            rn1 = semimaj/math.sqrt(f1)
            r1 = semimaj*(1.0 - e2)/math.sqrt(f1**3)
            d = xx/(rn1*scfa)

            f1 = rn1*math.tan(rlat1)/r1
            f2 = d**2/2.0
            f3 = 5.0 + 3.0*t1 + 10.0*c1 - 4.0*c1**2 - 9.0*ep2
            f3 = f3*d**2*d**2/24.0
            f4 = 61.0 + 90.0*t1 + 298.0*c1 + 45.0*t1**2 - 252.0*ep2 - 3.0*c1**2
            f4 = f4*(d**2)**3/720.0
            rlat = rlat1 - f1*(f2 - f3 + f4)
            dlat = rlat*raddeg

            f1 = 1.0 + 2.0*t1 + c1
            f1 = f1*d**2*d/6.0
            f2 = 5.0 - 2.0*c1 + 28.0*t1 - 3.0*c1**2 + 8.0*ep2 + 24.0*t1**2
            f2 = f2*(d**2)**2*d/120.0
            rlon = cmr + (d - f1 + f2)/math.cos(rlat1)
            dlon = rlon*raddeg
            if dlon < -180.0: dlon = dlon + 360.0
            if dlon > 180.0: dlon = dlon - 360.0

    if iway == IUTM2LONGLAT:
        rlon = dlon
        rlat = dlat
        rx = rx_save
        ry = ry_save
        return rlon,rlat

    else:
        rx = xx
        if lsouth: yy = yy + 1.e7
        ry = yy
        rlon = rlon_save
        rlat = rlat_save
        return rx,ry

#
#----------------------------------------------------------------------------------------
#

def geo2ltm(lon, lat, zone=None, iway=2):
    """
    Lunar Transverse Mercator (LTM) and Lunar Polar Stereographic (LPS) projection for polar regions

    this routine assumes a perfectly spherical Moon.
    LTM implementation is a simplified Spherical Transverse Mercator, 8-degree zones.

    note: by default, the LTM implementation in the python script LGRS_Coordinate_Conversion_mk7.2.py provided by USGS astrogeology site
          https://astrogeology.usgs.gov/search/map/lunar-map-projections-and-grid-reference-system-for-artemis-astronaut-surface-navigation
          uses a spherical Moon for their LTM projection.

          However, they still use the formula for a Gauss-Schreiber projection,
          that combines a projection of an ellipsoid to a sphere followed by a spherical transverse Mercator formula.
          Assuming the ellipsoid is perfectly spherical, then the first projection is an identity transform and only the second,
          spherical transverse Mercator formula is needed.
          Here, we use this simplification of applying directly the spherical transverse Mercator projection, assuming a spherical Moon.

    lon - longitude in degree range [-180,180]
    lat - latitude in degree range [-90,90]

    zone - LTM zones use 1 to 45, positive for Northern hemisphere, negative for Southern hemisphere
           LPS zones use 46 for North pole, -46 for South pole

    iway = 1  from LTM     to lon/lat
    iway = 2  from lon/lat to LTM
    """

    PI = math.pi
    degrad = PI / 180.0
    raddeg = 180.0 / PI

    # ---- Lunar spherical radius ----
    R = 1737400.0   # mean lunar radius (meters)

    # ---- Scale factor ----
    # Lunar map projection scale factors
    scfa = 0.999         # transverse Mercator (LTM)
    scfa_polar = 0.994   # polar stereographic (LPS)

    # ---- False origins ----
    false_east  =  250000.0
    false_north = 2500000.0

    false_east_polar  =  500000.0
    false_north_polar =  500000.0

    ILTM2LONGLAT = 1
    ILONGLAT2LTM = 2

    #----- Set Zone parameters
    # determine zone
    # for convenience, if zone is unspecified in forward mode, this computes it for the given longitude/latitude position
    # and returns only the zone number
    if iway == ILONGLAT2LTM and (zone is None or zone == 0):
        # checks latitute range for LTM [-82,82], beyond is polar region
        if lat >= -82.0 and lat <= 82.0:
            # LTM
            # longitudinal zone
            zone = int((lon + 180.0) // 8) + 1   # note: uses +1 because USGS's LGRS_Coordinate_Conversion_mk7.2.py has zone index starting at 1
            # 180-degree values sometimes come up as 46. We assign it back to zone 1
            if zone > 45:
                zone -= 45
            # we use negative values for Southern hemisphere
            if lat < 0.0:
                zone = -zone
        else:
            # LPS
            # polar region
            if lat >= 0.0:
                zone = 46    # north pole
            else:
                zone = -46   # south pole
        # just return zone
        return zone

    # zone is given as input, check if valid
    if zone is None or zone == 0 or int(abs(zone)) > 46:
        print(f"error: geo2ltm routine has as input zone {zone}, which is invalid. zone must be +/- 1-45 for LTM and +/- 46 for LPS")
        sys.exit(1)

    # zone index absolute
    z = int(abs(zone))

    # polar region
    use_polar = False
    # check if LPS or LTM
    if z == 46: use_polar = True

    # Lunar Polar Stereographic (LPS) projection
    if use_polar:
        if iway == ILONGLAT2LTM:
            # Forward transformation: lon/lat to LPS
            # Snyder (1987) spherical equations
            rlon = lon * degrad
            rlat = lat * degrad

            # Calculate polar stereographic spherical scale error
            A = 2.0 * R * scfa_polar

            if zone < 0:
                # South pole
                t = math.tan(PI/4.0 + rlat/2.0)
            else:
                # North pole
                t = math.tan(PI/4.0 - rlat/2.0)

            # stereographic map projection, Snyder (1987)
            # note: here, we use +cos(lon) as done in routine spherical_stereographic_map_y() of the USGS script LGRS_Coordinate_Conversion_mk7.2.py
            #       for both, North and South poles. the standard polar stereographic projection defined by Snyder would use
            #       North Pole: x = 2 R k0 tan(pi/4 - phi/2) sin(lambda - lambda0)
            #                   y = - 2 R k0 tan(pi/4 - phi/2) cos(lambda - lambda0)
            #       South Pole: x = 2 R k0 tan(pi/4 + phi/2) sin(lambda - lambda0)
            #                   y = 2 R k0 tan(pi/4 + phi/2) cos(lambda - lambda0)
            #       (see Snyder 1987, page 158, chapter 21 "Stereographic Projection", section "Formulas for the Sphere",
            #        eqs. 21-5, 21-6 and 21-9,21-10.
            #        https://pubs.usgs.gov/pp/1395/report.pdf ).
            # we'll take the convention from the USGS implementation to use +cos for both poles.
            #
            # X coordinate for a s
            x = A * t * math.sin(rlon)
            # Y coordinate for a stereographic map projection
            y = A * t * math.cos(rlon)

            # Add false Eastings and Northings
            x += false_east_polar
            y += false_north_polar

            # all done
            return x, y

        else:
            # Inverse transformation: LPS t0 lon/lat
            # remove false origins (must be same values used in forward)
            x = lon - false_east_polar
            y = lat - false_north_polar

            # radial distance from projection origin
            rho = math.hypot(x, y)

            # at the pole: rho == 0
            if rho == 0.0:
                deglat = -90.0 if zone < 0 else 90.0
                deglon = 0.0
                return deglon, deglat

            A = 2.0 * R * scfa_polar

            # t = tan( PI/4 ± lat/2 )  where sign depends on hemisphere in forward
            t = rho / A

            if zone < 0:
                # South pole
                # forward used: tan(PI/4 + lat/2) = t  -> lat = 2*atan(t) - PI/2
                latr = 2.0 * math.atan(t) - PI/2.0
            else:
                # North pole
                # forward used: tan(PI/4 - lat/2) = t  -> lat = PI/2 - 2*atan(t)
                latr = PI/2.0 - 2.0 * math.atan(t)

            # longitude from sin/cos ordering used in forward: x = factor*sin(lon), y = factor*cos(lon)
            lonr = math.atan2(x, y)

            deglon = lonr * raddeg
            deglat = latr * raddeg

            # normalize lon to -180..180
            if deglon > 180.0:
                deglon -= 360.0
            if deglon < -180.0:
                deglon += 360.0

            return deglon, deglat


    # Lunar Transverse Mercator (LTM) Projection
    # ---- Central meridian of 8-degree zone ----
    # central meridian
    cm = -180.0 + ((z - 1) + 0.5) * 8.0      # longitude of central meridian (note: z-1 because zones start at 1)
    cmr = cm * degrad

    # ----------------------------------------------------------------------
    # Forward transformation: lon/lat to LTM
    # ----------------------------------------------------------------------
    if iway == ILONGLAT2LTM:
        rlon = lon * degrad
        rlat = lat * degrad

        dlam = rlon - cmr

        # ---- Spherical Transverse Mercator (forward) ----
        B = math.cos(rlat) * math.sin(dlam)

        x = 0.5 * R * scfa * math.log((1.0 + B) / (1.0 - B))
        y = R * scfa * math.atan2(math.tan(rlat), math.cos(dlam))

        # False origins
        x += false_east
        # only for South sections
        if zone < 0:
            y += false_north

        return x, y

    # ----------------------------------------------------------------------
    # Inverse transformation: LTM to lon/lat
    # ----------------------------------------------------------------------
    else:
        # remove false origins
        x = lon - false_east
        if zone < 0:
            # only for South sections
            y = lat - false_north
        else:
            y = lat

        # ---- Spherical TM inverse ----
        D = y / (R * scfa)
        T = x / (R * scfa)

        lonr = cmr + math.atan2(math.sinh(T), math.cos(D))
        latr = math.asin(math.sin(D) / math.cosh(T))

        deglon = lonr * raddeg
        deglat = latr * raddeg

        # normalize lon to -180..180
        if deglon > 180.0:
            deglon -= 360.0
        if deglon < -180.0:
            deglon += 360.0

        return deglon, deglat

#
#----------------------------------------------------------------------------------------
#

def convert_lonlat2utm(file_in,zone,file_out):
    """
    converts file with lon/lat/elevation to output file utm_x/utm_y/elevation
    """
    global use_moon_ltm,projMerc

    print(f"converting lon/lat to {projMerc}: " + file_in + " ...")
    print("  zone: %i " % zone)

    # checks argument
    if abs(zone) < 1 or abs(zone) > 60:  sys.exit("error zone: zone not UTM zone")

    if not file_in:
        print("Error: empty input file name")
        sys.exit(1)

    # grab all the locations in file
    with open(file_in,'r') as f:
        content = f.readlines()

    nlines = len(content)
    print("  number of lines: %i" % nlines)
    print("")
    if nlines == 0:
        print("Error: no data lines in input file, exiting...")
        sys.exit(1)

    print("  output file: " + file_out)
    print("  format: #UTM_x #UTM_y #elevation")

    # write out converted file
    with open(file_out,'w') as f:
        for line in content:
            # reads lon/lat coordinates
            items = line.split()
            lon = float(items[0])
            lat = float(items[1])
            ele = float(items[2])

            if use_moon_ltm:
                # converts to LTM x/y
                x,y = geo2ltm(lon,lat,zone)
            else:
                # converts to UTM x/y
                x,y = geo2utm(lon,lat,zone)

            #print("%18.8f\t%18.8f\t%18.8f" % (x,y,ele))
            f.write("%18.8f\t%18.8f\t%18.8f\n" % (x,y,ele))

#
#-----------------------------------------------------------------------------
#


def setup_simulation(lon_min,lat_min,lon_max,lat_max):
    """
    sets up directory for a SPECFEM3D simulation
    """
    global datadir
    global utm_zone
    global incr_dx
    global use_topo_shifted,toposhift,toposcale
    global SRTM_type
    global use_moon_ltm,projMerc
    global clean_out_files

    print("")
    print("*******************************")
    print("setup simulation topography")
    print("*******************************")
    print("")
    print("  topo                  : ",SRTM_type)
    print("  grid sampling interval: ",incr_dx,"(deg) ",incr_dx * math.pi/180.0 * 6371.0, "(km)")
    if use_topo_shifted:
        print("  topo down shift       : ",toposhift)
        print("  topo down scaling     : ",toposcale)
    print("")

    # current directory
    dir = os.getcwd()

    # creates data directory
    cmd = 'mkdir -p ' + datadir
    print("  > ",cmd)
    status = subprocess.call(cmd, shell=True)
    check_status(status)
    print("")

    # change working directory to ./topo_data/
    path = dir + '/' + datadir
    os.chdir(path)
    print("  working directory     : ",os.getcwd())
    print("")

    # check min/max is given in correct order
    if lat_min > lat_max:
        tmp = lat_min
        lat_min = lat_max
        lat_max = tmp

    if lon_min > lon_max:
        tmp = lon_min
        lon_min = lon_max
        lon_max = tmp

    # use longitude range in [-180,180]
    # (there could be issues with determining the correct UTM zone in routine utm.latlon_to_zone_number() below
    #  if the longitudes are > 180)
    if lon_min < -180.0 and lon_max < -180.0:
        lon_min += 360.0
        lon_max += 360.0
    if lon_min > 180.0 and lon_max > 180:
        lon_min -= 360.0
        lon_max -= 360.0

    # check for moon
    if 'moon' in SRTM_type:
        print("")
        print("  using moon topography and Lunar Transverse Mercator (LTM) projection")
        print("")
        use_moon_ltm = True
        projMerc = 'LTM'  # Lunar Transverse Mercator (LTM) (or Lunar Polar system for pole regions)

    ## UTM zone
    print("*******************************")
    print(f"determining {projMerc} coordinates...")
    print("*******************************")
    print(f"  region: lon min/max = {lon_min} / {lon_max}")
    print(f"          lat min/max = {lat_min} / {lat_max}")
    print("")

    midpoint_lat = (lat_min + lat_max)/2.0
    midpoint_lon = (lon_min + lon_max)/2.0

    # determine UTM zone
    if use_moon_ltm:
        # Moon LTM/LPS zone
        zone = geo2ltm(midpoint_lon,midpoint_lat,zone=None,iway=2) # iway==2 LONGLAT2UTM, zone set to None to determine it
        # LTM zones from 1 to 45, LPS is +/- 46
        utm_zone = zone
        utm_zone_letter = f"{utm_zone}"  # no particular lettering for LTM, just 1N, 1S, .., 45N, 45S
        # hemisphere N for lat >= 0
        if midpoint_lat >= 0.0:
            hemisphere = 'N'
        else:
            hemisphere = 'S'
        # check if LTM or LPS
        if int(abs(utm_zone)) == 46: projMerc = 'LPS'  # Lunar Polar Stereographic (LPS)

    else:
        # UTM zone
        utm_zone_letter = utm.latitude_to_zone_letter(midpoint_lat)  # zone letters: XWVUTSRQPN north, MLKJHGFEDC south
        hemisphere = 'N' if utm_zone_letter in "XWVUTSRQPN" else 'S'

        utm_zone = utm.latlon_to_zone_number(midpoint_lat,midpoint_lon)

    print(f"  region midpoint lat/lon: {midpoint_lat:.2f} / {midpoint_lon:.2f}")
    print(f"  {projMerc} zone: {utm_zone}{hemisphere}")
    print("")

    # SPECFEM uses positive (+) zone numbers for Northern, negative (-) zone numbers for Southern hemisphere
    if not use_moon_ltm and hemisphere == 'S':
        utm_zone = - utm_zone
        print("  Southern hemisphere")
        print("  using negative zone number: {} (for SPECFEM format)".format(utm_zone))
        print("")

    # get topography data
    xyz_file = get_topo(lon_min,lat_min,lon_max,lat_max)

    # converting to utm
    if use_moon_ltm:
        utm_file = 'ptopo.ltm'
    else:
        utm_file = 'ptopo.utm'

    convert_lonlat2utm(xyz_file,utm_zone,utm_file)
    #script version
    #cmd = '../topo/convert_lonlat2utm.py ' + xyz_file + ' ' + str(utm_zone) + ' > ' + utm_file
    #print("converting lon/lat to UTM: ptopo.utm ...")
    #print("> ",cmd)
    #status = subprocess.call(cmd, shell=True)
    #check_status(status)
    print("")

    # AVS UCD file with region borders
    create_AVS_file()

    # extracts interface data for xmeshfem3D
    # uses file with degree increments to determine dx,dy in degrees, as needed for interfaces.dat
    nx,ny,dx,dy,interface_region = topo_extract(xyz_file)

    # creates parameter files
    # main Par_file
    update_Par_file(dir)

    # mesher Mesh_Par_file
    update_Mesh_Par_file(dir,lon_min,lat_min,lon_max,lat_max,nx,ny,dx,dy,interface_region,xyz_file)

    # clean
    if clean_out_files:
        # cleanup files in topo_data/ directory
        os.chdir(path)
        cmd = 'rm -f ' + 'ptopo.xyz' + ';'
        if utm_file: cmd += 'rm -f ' + utm_file + ';'
        if os.path.isfile('gmt.history'): cmd += 'rm -f ' + 'gmt.history' + ';'
        print("  > ",cmd)
        status = subprocess.call(cmd, shell=True)
        check_status(status)
        print("")

    print("")
    print("topo output in directory: ",datadir)
    print("")
    print("all done")
    print("")
    return

#
#-----------------------------------------------------------------------------
#

def usage():
    global incr_dx,toposhift,toposcale

    # default increment in km
    incr_dx_km = incr_dx * math.pi/180.0 * 6371.0

    print("usage: ./run_get_simulation_topography.py lon_min lat_min lon_max lat_max [--SRTM=SRTM] [--dx=incr_dx] [--toposhift=toposhift] [--toposcale=toposcale] [--clean]")
    print("   where")
    print("       lon_min lat_min lon_max lat_max - region given by points: left bottom right top")
    print("                                         for example: 12.35 42.0 12.65 41.8 (Rome)")
    print("       SRTM                            - (optional) name options are:")
    print("                                          'low'  == SRTM 90m ")
    print("                                          'high' == SRTM 30m")
    print("                                          'etopo2' == ETOPO2 (2-arc minutes)")
    print("                                          'topo30' / 'srtm30s' / 'srtm_1km' == SRTM topo 30s (30-arc seconds)")
    print("                                          'topo15' / 'srtm15s' / 'srtm_500m' == SRTM topo 15s (15-arc seconds)")
    print("                                          'topo3' / 'srtm3s' / 'srtm_100m' == SRTM topo 3s (3-arc seconds)")
    print("                                          'topo1' / 'srtm1s' / 'srtm_30m' == SRTM topo 1s (1-arc seconds)")
    print("                                          'moon' == Moon 2m (2-arc minutes) / 'moon15s' == Moon 15s (15-arc seconds)")
    print("       incr_dx                         - (optional) GMT grid sampling (in degrees)")
    print("                                         e.g., 0.01 == (~1.1km) [default %f degrees ~ %f km]" % (incr_dx,incr_dx_km))
    print("       toposhift                       - (optional) topography shift for 2nd interface (in m)")
    print("                                         to shift original topography downwards [default %f m]" % toposhift)
    print("       toposcale                       - (optional) scalefactor to topography for shifted 2nd interface (e.g., 0.1) [default %f]" %toposcale)
    print("       clean                           - (optional) cleans out informative files, only keeps important ones")
    sys.exit(1)

if __name__ == '__main__':
    # gets arguments
    if len(sys.argv) < 5:
        usage()

    else:
        lon_min = float(sys.argv[1])
        lat_min = float(sys.argv[2])
        lon_max = float(sys.argv[3])
        lat_max = float(sys.argv[4])

        i = 0
        for arg in sys.argv:
            #print("argument "+str(i)+": " + arg)
            # get arguments
            if "--help" in arg:
                usage()
            elif "--SRTM=" in arg:
                # type: 'low' == SRTM 90m / 'high' == SRTM 30m / else e.g. 'etopo' == topo30 (30-arc seconds)
                SRTM_type = arg.split('=')[1]
            elif "--dx=" in arg:
                # GMT grid sampling interval
                incr_dx = float(arg.split('=')[1])
            elif "--toposhift" in arg:
                # topography shift for 2nd interface
                use_topo_shifted = True
                if len(arg.split('=')) > 1:
                    toposhift = float(arg.split('=')[1])
            elif "--toposcale" in arg:
                # topography scalefactor
                if len(arg.split('=')) > 1:
                    toposcale = float(arg.split('=')[1])
            elif "--clean" in arg:
                clean_out_files = True
            elif i >= 5:
                print("argument not recognized: ",arg)
                usage()
            i += 1

    # logging
    cmd = " ".join(sys.argv)
    filename = './run_get_simulation_topography.log'
    with open(filename, 'a') as f:
      print("command call --- " + str(datetime.datetime.now()),file=f)
      print(cmd,file=f)
      print("command logged to file: " + filename)

    # initializes
    setup_simulation(lon_min,lat_min,lon_max,lat_max)

