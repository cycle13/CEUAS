#!/usr/bin/env python
import sys, os.path, glob 
import subprocess
import urllib.request
import xarray as xr
#import numpy
#import h5pickle as h5py
#import numpy
import h5py
from datetime import date, datetime
import time
from multiprocessing import Pool
from netCDF4 import Dataset
import gzip
import pandas as pd    
from functools import partial
#from rasotools.utils import *
from numba import *
import matplotlib.pylab as plt
import cartopy.crs as ccrs
import argparse
#import copy
from io import StringIO
#import h5netcdf
import numpy as np
from eccodes import *
import warnings
import numpy
warnings.simplefilter(action='ignore', category=FutureWarning) # deactivates Pandas warnings 


debug = False


""" Some colors for pretty printout """ 
red    = '\033[91m' 
cend   = '\033[0m'
blue   = '\033[34m'
green  = '\033[92m'
yellow = '\033[33m'

""" Possible variable types as listed int he CMD tables S80 is a fixed 80 char. string. Compression does not work well with normal strings. """
okinds={'varchar (pk)':np.dtype('|S80'),
               'varchar':np.dtype('|S80'), 
               'numeric':np.float32, 'int':np.int32,
               #'timestamp with timezone':np.datetime64,
               'timestamp with timezone':np.float32,
               
               'int[]*':list,
               'int[]':list,
               'varchar[]*':list,
               'varchar[]':list}

""" Variable types to be used in the compressed netCDF files """
kinds={'varchar (pk)':str,
             'varchar':str,
             'numeric':np.float32,
             'int':np.int32,
             'int(pk)' : np.int32,
             #'timestamp with timezone':np.datetime64,  # gives errore when wiritng out the netCDF file with the np.datetime64 
             'timestamp with timezone':np.float32,             
             'int[]*':list,
             'int[]':list,
             'varchar[]*':list,
             'varchar[]':list}


def make_datetime(dvar,tvar):
    """ Converts into date-time standard format """
    dvari=dvar.values.astype(numpy.int)
    tvari=tvar.values.astype(numpy.int)
    df=pd.DataFrame({'year':dvar//10000,'month':(dvar%10000)//100,'day':dvar%100,
                        'hour':tvar//10000,'minute':(tvar%10000)//100,'second':tvar%100})
    dt=pd.to_datetime(df).values
    return dt


""" Dictionaries mapping the input variable names (from the ODBs and from the other sourc files) to cdm variable names """
cdmfb={'observation_value':'obsvalue@body',
               'observed_variable':'varno@body',
               'z_coordinate_type':'vertco_type@body',
               'z_coordinate':'vertco_reference_1@body',
               'date_time':[make_datetime,'date@hdr','time@hdr'],
               'longitude':'lon@hdr',
               'latitude':'lat@hdr',
               'record_id': 'seqno@hdr' ,
               'observation_id': 'observation_id' ,
               'report_id':'report_id' , 
               'units' : 'units',               
               'file_name':'file_name'}

cdmfb_noodb={'observation_value':'obsvalue@body',
                          'observed_variable':'varno@body',
                          'z_coordinate_type':'vertco_type@body',
                          'z_coordinate':'vertco_reference_1@body',
                          'date_time':'record_timestamp', 
                          'release_time': 'report_timestamp' , # only available for igra2 
                          'longitude':'lon@hdr',
                          'latitude':'lat@hdr',
                          'observation_id':'observation_id' ,
                          'source_file':'source_file',
                          #'product_code': 'product_code' ,
                          'report_id':'report_id' ,
                          'number_of_pressure_levels' : 'number_of_pressure_levels',
                          'units' : 'units',
                          'source_id': 'source_id',                          
                           }  



def check_read_file(file='', read= False):
    """ Simple utility to check if file exists and uncompress it, then optionally read the lines (in case of text files e.g. igra2 and UADB)
        and store them as entry of a list. Return the list.
        Used to prepare the igra2 and UADB files. 
        Adapted from https://github.com/MBlaschek/igra/blob/master/igra/read.py 
        
        Args:
             file (str): path to the file
            read (bool): set to True to return the list of lines in case of txt files 
        Returns:
             lines (list) read from the file """

    if not os.path.isfile(file):
        raise IOError("File not Found! %s" % file)

    if read:
        if '.zip' in file:
            archive = zipfile.ZipFile(file, 'r')
            inside = archive.namelist()
            tmp = archive.open(inside[0])
            tmp = io.TextIOWrapper(tmp, encoding='utf-8')
            tmp = tmp.read()
            archive.close()
            data = tmp.splitlines()  # Memory (faster) 

        elif '.gz' in file:
            with gzip.open(file, 'rt',  encoding='utf-8') as infile:
                tmp = infile.read()  # alternative readlines (slower)                                                                                                                                                                                                            
                data = tmp.splitlines()  # Memory (faster)                                                                                                                                                                                                                              
        else:
            with open(file, 'rt') as infile:
                tmp = infile.read()  # alternative readlines (slower)                                                                                                                                                                                                                   
                data = tmp.splitlines()  # Memory (faster)  

        return data


""" Dictionary mapping generic names of the variables to odbs numbering scheme. 
The numbers will be then converted to the CDM convention by the funcion 'fromfb' 
            tr[1]=117  # should change , geopotential height
            tr[2]=85 # air temperature	K
            tr[3]=104 # eastward wind speed
            tr[4]=105 # northward wind speed 
            tr[7]=39 # spec hum
            tr[29]=38 # relative hum
            tr[59]=36 # dew point
            tr[111]=106 #dd wind from direction
            tr[112]=107  #ff wind speed 
            #
            tr[39]= 85 # 2m T ### FIX THESE NUMBERS !!!! 
            tr[40]= 36 # 2m Td
            tr[41]= 104 #10m U
            tr[42]= 105  #10m V
            tr[58]= 38 # 2m rel hum


"""

# See:
# https://github.com/glamod/common_data_model/blob/master/tables/observed_variable.dat
# https://github.com/glamod/common_data_model/blob/master/tables/units.dat
# https://apps.ecmwf.int/odbgov/varno/

""" Dictionary mapping names, odb_codes and cdm_codes . """ 
cdmvar_dic = {'temperature'          : { 'odb_var': 2      , 'cdm_unit': 5        , 'cdm_var': 85}     ,  # K
              
                         'wind_direction'      : { 'odb_var': 111   , 'cdm_unit': 110    , 'cdm_var': 106}   ,  # degree (angle)
                         'wind_speed'           : { 'odb_var': 112  , 'cdm_unit': 731     , 'cdm_var': 107 } ,  # m/s 
                         'uwind'                    : { 'odb_var': 3       , 'cdm_unit': 731     , 'cdm_var': 104}   ,  # m/s
                         'vwind'                    : { 'odb_var': 4       , 'cdm_unit': 731     , 'cdm_var': 105}    ,  # m/s
                         
                         'dew_point'             : { 'odb_var': 59             , 'cdm_unit': 5  , 'cdm_var': 36}     ,  # K
                         'dew_point_depression' : { 'odb_var': 299  , 'cdm_unit': 5     , 'cdm_var': 34}   ,  # K fake number, does not exhist in ODB file 
                         
                         'relative_humidity'  : { 'odb_var': 29     , 'cdm_unit': 300    , 'cdm_var': 38}     ,  # per cent 
                         'gph'                       : { 'odb_var': 1       , 'cdm_unit': 1         , 'cdm_var': 117}    ,  # need to verify from original data source

                         'pressure'               : { 'odb_var': 999    , 'cdm_unit': 32       , 'cdm_var': 57}      , # Pa  (it goes into z_coordinate type)
                          }

""" CDM variable codes for the corresponding ODB variables """
cdm_odb_var_dic = { 1    : 117    , # geopotential
                                   2    : 85        , # temperature K
                                   
                                   3    : 104    , # uwind m/s , upper air u component 
                                   4    : 105    ,  # vwind m/s
                                  111 : 106    , # degree (angle) , wind from direction 
                                  112 : 107    , # m/s , wind force 
                                  
                                  29   : 38      , # relative humidity in %
                                 59    : 36      , # dew point (available in ODB files )
                                 
                                 999  : 57      , # Pa  (NOTE: it goes into z_coordinate type, not in the observed variables)                                 
                                 99    : 34   , # dew_point depression (non existing in ODB files )
                          }

"""
34	humidity	atmospheric	surface; upper-air	dew point depression	K	Dew point depression is also called dew point deficit. It is the amount by which the air temperature exceeds its dew point temperature. 
Dew point temperature is the temperature at which a parcel of air reaches saturation upon being cooled at constant pressure and specific humidity.

36	humidity	atmospheric	surface; upper-air	dew point temperature	K	Dew point temperature is the temperature at which a parcel of air reaches saturation upon being cooled at constant pressure and specific humidity.

"""

""" Common columns of the read dataframes (not from ODB files, which have their own fixed column names definitions """
column_names = ['source_file', 'source_id', 'report_id',  'observation_id', 'record_timestamp' , 'iday', 'station_id', 'lat@hdr', 'lon@hdr', 'vertco_reference_1@body', 'obsvalue@body', 'varno@body' , 'units',  'number_of_pressure_levels' ]
column_names_igra2 = column_names 
column_names_igra2.append('report_timestamp')

# record_timestamp: same as date_time in the observations_table
# report_timestamp: only for igra2, representes the release time of the sonde 



def bufr_to_dataframe(file=''):
    """ Read a bufr file and convert to a Pandas DataFrame 
        Variables used inside the DataFrame are already CDM compliant                                                                                                                                                                                                               

        Args:                                                                                                                                                                                                                                                                       
             file (str): path to the bufr  file  

        Returns:                                                                                                                                                                                                                                                                    
             Pandas DataFrame with cdm compliant column names    
    
    """
    
    if debug:
        print("Running bufr_to_dataframe for: ", file)
         
    check_read_file (file = file, read= False)

    f = open(file)
    source_file = [l for l in file.split('/') if '.bfr' in l][0]
    
    """ Dicts mapping the names of the variables in the bufr files (keys) to the cdm names (values) 
    cdm_header_dic =  {'stationNumber'  : 'station_name' ,
                       'blockNumber'     : ''             ,
                       'heightOfStation' : ''             ,
                       'latitude'              : 'latitude'     ,
                       'longitute'            : 'longitude'   ,
                       'typicalDate'        : '',
                       'typicalTime'        : '' 
                       }
                       """
    #cdmvar_dic = { 'airTemperature' : {'units':'C_to_tenths'       , 'cdm_name': 'temperature'         },
    #              'windDirection'  : {'units':'ms_to_tenths'      , 'cdm_name': 'wind_speed'          },
    #                'windSpeed'      : {'units':'degree'            , 'cdm_name': 'wind_direction'      },
    #                'dewpointTemperature' : {'units': ' '           , 'cdm_name': 'dew_point'           },
    #                'pressure'       : {'units': ' '                , 'cdm_name': 'pressure'            } }
    
    bufr_values = []
    
    """ Name of the columns as they will appear in the pandas dataframe (not necessarily CDM compliant) """
    #column_names = ['report_timestamp' , 'iday',  'station_id', 'latitude', 'longitude', 'pressure', 'value','varno@body']
       
    lat, lon, alt, blockNumber, stationNumber, statid = np.nan, np.nan, np.nan, np.nan, np.nan, np.nan
    
    obs_id, report_id = -1, 0 # progressive observation id
    
    while 1:
        #lista = [] # temporary list
        bufr = codes_bufr_new_from_file(f)
   
        if bufr is None:
            break
   
        codes_set(bufr, 'unpack', 1) # eCcodes must expand all the descriptors and unpack the data section
    
        date = '19'+codes_get_array(bufr, "typicalDate")[0][2:]
        timePeriod = codes_get_array(bufr, "typicalTime")[0]   
        
        year, month, day =  date[0:4], date[4:6] , date[6:8]
        hour, minutes = timePeriod[0:2] , timePeriod[2:4]
                       
        idate =  datetime.strptime(year + month + day + hour + minutes, '%Y%m%d%H%M')
        iday = int(year + month + day )

        pressure             = codes_get_array(bufr, "pressure") 
        temperature       = codes_get_array(bufr, "airTemperature")           
        wind_direction    = codes_get_array(bufr, "windDirection")
        wind_speed        = codes_get_array(bufr, "windSpeed")
        
        try:  # not all the bufr files have the dewpoint measurements
            dew_point          = codes_get_array(bufr, "dewpointTemperature")
        except:
            dew_point= np.empty((1, len(temperature)))
            dew_point[:] = np.nan
            
        num_lev             = len(pressure) # number of  distinct pressure levels 
        
        try:
            geopotential   = codes_get_array(bufr, "nonCoordinateGeopotentialHeight")         
        except:
            geopotential = np.full( (1,len(temperature)) , np.nan )[0,:]
                
        if report_id == 0:
            ''' Check again but these values should remain the same for all cnt, so it makes no sense to read them every time '''
            lat                     = codes_get(bufr, "latitude")
            lon                    = codes_get(bufr, "longitude")
            alt                     = float(codes_get(bufr, "heightOfStation"))
            blockNumber    = codes_get(bufr, "blockNumber")
            stationNumber = codes_get(bufr, "stationNumber")
            statid                = str(blockNumber*1000+stationNumber)
            
        codes_release(bufr)
   
        miss_value = -1.e100     
        
        for i in range(len(temperature)):
            obs_id = obs_id + 1 
            airT         = temperature[i]
            winds      = wind_speed[i]
            windd      = wind_direction[i]
            press       = pressure[i]
            gph         =  geopotential[i]
            dp = dew_point[i]
            if dp == miss_value:
                dp = np.nan
            if airT == miss_value :    # replacing none values with numpy nans
                airT = np.nan 
            if winds == miss_value:
                winds = np.nan
            if windd == 2147483647:
                windd = np.nan 
                
            for value,var in zip( [gph, airT, winds, windd, dp],  ['gph', 'temperature', 'wind_speed', 'wind_direction', 'dew_point'] ):
                obs_id = obs_id + 1 
                bufr_values.append( (source_file, 'BUFR', report_id, obs_id,  idate, iday, statid, lat, lon, press, value, cdmvar_dic[var]['odb_var'] , cdmvar_dic[var]['cdm_unit'], num_lev  ) ) 
        
        report_id += 1
            
    #column_names = ['source_file', 'product_code', 'report_id',  'observation_id', 'report_timestamp' , 'iday', 'station_id', 'lat@hdr', 'lon@hdr', 'vertco_reference_1@body', 'obsvalue@body', 'varno@body' , 'units',  'number_of_pressure_levels' ]
    df = pd.DataFrame(data= bufr_values, columns= column_names)
    
    df.sort_values(by = ['record_timestamp', 'vertco_reference_1@body' ] )    
    return df.to_xarray()
    
    

def uadb_ascii_to_dataframe(file=''):
    """ Read an uadb stationfile in ASCII format and convert to a Pandas DataFrame.                                                                                                                                                                                          
        Adapted from https://github.com/MBlaschek/CEUAS/tree/master/CEUAS/data/igra/read.py                                                                                                                                                                                         
        Variables used inside the DataFrame are already CDM compliant   
        Documentation available at: https://rda.ucar.edu/datasets/ds370.1/docs/uadb-format-ascii.pdf
        
        Args:
             file (str): path to the uadb station file

        Returns:
             Pandas DataFrame with cdm compliant column names
             
    """     
     
    if debug:
        print("Running uadb_ascii_to_dataframe for: ", file)    
         
    data = check_read_file(file=file, read=True)
    
    source_file = [l for l in file.split('/') if '.txt' in l][0]

    nmiss = 0
    search_h = False   
    read_data = []
    
    usi,idate, usi, lat, lon, lat, stype, press, gph, temp, rh, wdir, wspd = np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan

    obs_id = 0
    for i, line in enumerate(data):
        if line[0] == 'H':
            try:
                # Header
                usi      = int(line[2:14])  # unique station identifier
                ident    = line[15:21].replace(' ','')# WMO
                if len(ident) == 4:
                    ident = '0' + ident 
                #idflag   = int(line[22:24])  # id flag
                #d_src    = int(line[25:28])  # source dataset
                #version  = float(line[29:34])  # version
                #dateflag = int(line[35:37])  # date flag
                year     = line[38:42]  # year
                month    = "%02d" % int(line[43:45])
                day      = "%02d"  % int(line[46:48])
                hour     = line[49:53]
                #locflag  = int(line[54:56])  # Location Flag
                lat      = float(line[57:67])
                lon      = float(line[68:78])
                #ele      = float(line[79:85])
                stype    = int(line[86:88])
                numlev   = int(line[89:93])
                #pvers    = line[94:102]

                '''
                if '99' in hour:
                    hour = hour.replace('99', '00')
        
                if '99' in day:
                    search_h = True
                    continue
                '''                
                minutes = int(hour) % 100                
                hour = "%02d" % (int(hour) // 100)
                if minutes > 60 or minutes < 0:
                    minutes = 0
                minutes = "%02d" % minutes
                idate = datetime.strptime(year + month + day + hour + minutes, '%Y%m%d%H%M')
                iday = int(year + month + day)
                #pday = int(day)
                search_h = False

            except Exception as e:
                print("Error: ", i, line, repr(e), "Skipping Block:")
                search_h = True
                #iprev = i

        elif search_h:
            nmiss += 1
            continue  # Skipping block

        else:
            # Data
            #ltyp      = int(line[0:4])
            p   = float(line[5:13])
            
            if p != -99999.0 and p != 9999.9: 
                press   = float(line[5:13])*100  # converting to Pa, since P is given in mb (1 mb = 1 hPa) 
            else:
                press = np.nan                 
                
            gph = float(line[14:22]) # gph [m]
            if gph == -99999.0 or gph == -99999.00 or gph >= 99999.0:
                gph = np.nan
         
            temp = float(line[23:29])
            if temp == -999.0:
                temp = np.nan 
            else:
                temp = temp + 273.15
                
            rh  = float(line[30:36])  # %
            if rh == -999.0:
                rh = np.nan
            else:
                rh = rh / 100.  # convert to absolute ratio 

            wdir    = float(line[37:43])
            if wdir == -999.0 or wdir == -999 :
                wdir = np.nan
            
            wspd   = float(line[44:50])  # [m/s], module of the velocity
            if wspd <0 :
                wspd = np.nan             
                
            for value,var in zip([gph, temp, wspd, wdir, rh],  ['gph', 'temperature', 'wind_speed', 'wind_direction', 'relative_humidity'] ):
                obs_id = obs_id +1
                read_data.append( (source_file, 'NCAR', usi, obs_id, idate, iday, ident, lat, lon, press, value, cdmvar_dic[var]['odb_var'] , cdmvar_dic[var]['cdm_unit'], numlev) )
              
              
    
    #column_names = ['source_file', 'product_code', 'report_id', 'observation_id', 'report_timestamp' , 'iday', 'station_id', 'lat@hdr', 'lon@hdr', 'vertco_reference_1@body', 'obsvalue@body', 'varno@body' ,  'units',  'number_of_pressure_levels' ]
    
    df = pd.DataFrame(data= read_data, columns= column_names)        
    df['vertco_type@body'] = 1
    df.sort_values(by = ['record_timestamp', 'vertco_reference_1@body' ] )    
    
    return df.to_xarray()


def igra2_ascii_to_dataframe(file=''):
    """ Read an igra2 stationfile in ASCII format and convert to a Pandas DataFrame. 
        Adapted from https://github.com/MBlaschek/CEUAS/tree/master/CEUAS/data/igra/read.py 
        Variables used inside the DataFrame are already CDM compliant
        
        Args:
             file (str): path to the igra2 station file

        Returns:
             Pandas DataFrame with cdm compliant column names
    """
    if debug:
        print("Running igra2_ascii_to_dataframe for: ", file)    
         
    data = check_read_file(file=file, read=True)
    source_file = [l for l in file.split('/') if '.txt' in l][0]
    read_data = [] #  Lists containing the raw data from the ascii file, and the observation dates
    """ Data to be extracted and stored from the igra2 station files 
        Some info is contained in the header of each ascent, some in the following data """

    """ Initialize the variables that can be read from the igra2 files """
    ident,year,month,day,hour,reltime,p_src,np_src,lat, lon = np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan 
    lvltyp1,lvltyp2,etime,press,pflag,gph,zflag,temp,tflag,rh,dpdep,wdir,wspd = np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan # initialize to zeros
    idate = np.nan
    count = 0
    head_count = 0
    
    obs_id = 0
    for i, line in enumerate(data):
        if line[0] == '#':
            head_count = head_count +1 
            # Info from the Header line of each ascent                                                                                                                                                                                                                   
            ident     = line[1:12]               # station identifier
            ident     = ident[6:12]
            year      = line[13:17]               # year, months, day, hour of the observation
            month   = line[18:20]
            day       = line[21:23]
            hour      = line[24:26]               
            reltime  = line[27:31]            # release time of the sounding.
            numlev  = int(line[32:36])        # number of levels in the sounding == number of data recorded in the ascent
            p_src     = line[37:45]              # data source code for the pressure levels 
            np_src   = line[46:54]             # data source code for non-pressure levels
            lat         = int(line[55:62]) / 10000.  # latitude and longitude
            lon        = int(line[63:71]) / 10000.
            #observation_id = i
            if int(hour) == 99:
                time = reltime + '00'
            else:
                time = hour + '0000'
           
            if '99' in time:
                time = time.replace('99', '00')

            idate = datetime.strptime(year + month + day + time, '%Y%m%d%H%M%S') # constructed according to CDM
            iday =  int(year + month + day)
            count = count + 1
        else:
           # Data of each ascent
            lvltyp1 = int(line[0])            # 1-  1   integer major level type indicator
            lvltyp2 = int(line[1])            # 2-  2   integer minor level type indicator
            etime   = int(line[3:8])          # 4-  8   integer elapsed time since launch
            press   = int(line[9:15])         # 10- 15  integer reported pressure
            pflag   = line[15]                # 16- 16  character pressure processing flag
            
            gph     = int(line[16:21])        # 17- 21  integer geopotential height  [m]
            
            if gph == -9999 or gph == -8888:   # reading the values andh check if they are missing or removed as -9999 or -8888 before dividing by 10 as the instructions say 
                gph = np.nan # 23- 27  integer temperature, [Celsius to Kelvin ]    
                
            zflag   = line[21]                # 22- 22  character gph processing flag, 
        
            temp    = int(line[22:27])              
            if temp != -9999 and temp != -8888:   # reading the values andh check if they are missing or removed as -9999 or -8888 before dividing by 10 as the instructions say 
                temp = temp / 10.   + 273.15 # 23- 27  integer temperature, [Celsius to Kelvin ]    
            else:
                temp = np.nan 
                                
            tflag   = line[27]    # 28- 28  character temperature processing flag
            
            rh      = int(line[28:33])  # 30- 34  integer relative humidity [%]           
            if rh != -8888 and rh != -9999:
                rh = rh / 1000.  # converting from percentage to absolute ratio 
            else:
                rh = np.nan
                
            dpdp    = int(line[34:39]) 
            if dpdp != -9999 and dpdp !=-8888:                
                dpdp    = dpdp / 10.  # 36- 40  integer dew point depression (degrees to tenth e.g. 11=1.1 C)    
            else:
                dpdp = np.nan 
           
            wdir    = int(line[40:45])        # 41- 45  integer wind direction (degrees from north, 90 = east)
            if wdir == -8888 or wdir == -9999 :
                wdir = np.nan         
            
            wspd    = int(line[46:51])   # 47- 51  integer wind speed (meters per second to tenths, e.g. 11 = 1.1 m/s  [m/s]
            if wspd != -8888 and wspd != -9999 :
                wspd = wspd / 10.  
            else:
                wspd = np.nan                  
                
            for value,var in zip([gph, temp, wspd, wdir, rh, dpdp],  ['gph', 'temperature', 'wind_speed', 'wind_direction', 'relative_humidity' , 'dew_point_depression'] ):
                obs_id = obs_id +1 
                #read_data.append( (source_file, 'NCAR', usi, obs_id,                idate, iday, ident, lat, lon, press, value, cdmvar_dic[var]['odb_var'] , cdmvar_dic[var]['cdm_unit'], numlev) )
                read_data.append ( (source_file, 'IGRA', head_count,  obs_id,  idate, iday, ident, lat, lon, press, value, cdmvar_dic[var]['odb_var'], cdmvar_dic[var]['cdm_unit'], numlev, reltime ) )
                #print('check', value, cdmvar_dic[var] , var )                   
            #column_names = ['source_file', 'product_code', 'report_id', 'observation_id', 'report_timestamp' , 'iday', 'station_id', 'lat@hdr', 'lon@hdr', 'vertco_reference_1@body', 'obsvalue@body', 'varno@body', 'number_of_pressure_levels' , 'units']
            
    df = pd.DataFrame(data= read_data, columns= column_names_igra2)
    df['vertco_type@body'] = 1    
    df.sort_values(by = ['record_timestamp', 'vertco_reference_1@body' ] )    
    return df.to_xarray()

 
def read_all_odbsql_stn_withfeedback(odbfile):
    print("Running read_all_odbsql_stn_withfeedback for: ***  ", odbfile)
    
    if debug: 
        print("Running read_all_odbsql_stn_withfeedback for: ", odbfile)
        
    #alldata='' REMOVE

    alldict=xr.Dataset()
    t=time.time()
    #sonde_type , obstype =True , True REMOVE

    if os.path.getsize(odbfile)>0:
        """ Read first the odb header to extract the column names and type """
        try:
            rdata=subprocess.check_output(["odb","header",odbfile])
            rdata=rdata.decode('latin-1').split('\n')
            columns=[]
            kinds=[]
            tdict={}
            for r in rdata[2:-2]:
                try:
                    #print(r[:6]) REMOVE
                    if r[:6]=='Header':
                        break
                    else:    
                        columns.append(r.split('name: ')[1].split(',')[0])
                        kinds.append(r.split('type: ')[1].split(',')[0])
                        if kinds[-1]=='REAL':
                            tdict[columns[-1]]=numpy.float32
                        elif kinds[-1] in ('INTEGER','BITFIELD'):
                            if columns[-1]=='date@hdr':
                                tdict[columns[-1]]=numpy.int32
                            else: 
                                tdict[columns[-1]]=numpy.float32
                        else:
                            tdict[columns[-1]]=numpy.dtype('S8') # dict containing column name and type
                                     
                            
                except IndexError:
                    pass
        except:
            print('could not read odbfile '+odbfile)
            return alldict
        try:
            rdata=subprocess.check_output(["odb","sql","-q","select *","-i",odbfile,'--no_alignment']) # after reading the header it does the query
            # returns a byte string
            #print('after odb:',time.time()-t)
            rdata=''.join(rdata.decode('latin-1').split("'")) # decoding the string into a unicode
            f=StringIO(rdata) # access the string like a file, return a file pointer to read the string with pandas
            # nb  if you have null values, reading of integer fails and are read as floats
            # to improve, you can convert the columns with nans in the alldicts (pandas data frame) into int(np.nans)
            # date values are large so float 32 precision is not sufficient  FF TODO
            alldict=pd.read_csv(f,delimiter='\t',quoting=3,comment='#',dtype=tdict)
            del f,rdata

 
            """ alternative method to read the odb           # REMOVE
            if False:
                
                rdata='nan'.join(rdata.decode('latin-1').split('NULL'))
                rdata=''.join(rdata.split("'"))
                rdata='\t'.join(rdata.split('\n')[1:-1])
                rdata=tuple(rdata.split('\t'))
                
                print('after odb:',time.time()-t)
                #xdata=numpy.fromstring(rdata,sep='\t')
                cl=len(columns)
                rl=len(rdata)//cl
                #for k in range(cl):
                    #if kinds[k]=='REAL':
                        #alldict[columns[k]]=({'obslen':rl},numpy.empty(rl,dtype=numpy.float32))
                    #elif kinds[k] in ('INTEGER','BITFIELD'):
                        #alldict[columns[k]]=({'obslen':rl},numpy.empty(rl,dtype=numpy.int32))
                    #else:
                        #alldict[columns[k]]=({'obslen':rl},numpy.empty(rl,dtype='|S8'))
                #print(odbfile,time.time()-t)
                for k in range(cl):
                    if kinds[k]=='REAL':
                        alldict[columns[k]]=({'obslen':rl},numpy.float32(rdata[k::cl]))
                    elif kinds[k] in ('INTEGER','BITFIELD'):
                        rds=rdata[k::cl]
                        if 'nan' in rds: 
                            alldict[columns[k]]=({'obslen':rl},numpy.asarray(rds,dtype=float).astype(numpy.int32))
                        else:
                            alldict[columns[k]]=({'obslen':rl},numpy.asarray(rds,dtype=numpy.int32))
                    else:
                        alldict[columns[k]]=({'obslen':rl},numpy.asarray(rdata[k::cl],dtype='|S8'))
             """
       
            #input('FF check alldict')
            # alldict.head() # pandas method to print the columns name . alldict is now a panda dataframe with e.g. 22000*63 columns where the 63 columns are read from the odb file 
            
        except subprocess.CalledProcessError as e:
            print('odb failed!:'+' '+odbfile)
            return alldict

    #print(odbfile,time.time()-t)
    #idy=numpy.lexsort((alldict['varno@body'],
                       #-alldict['vertco_reference_1@body'],
                       #alldict['time@hdr'],
                       #alldict['date@hdr']))
    #for k in alldict.columns:
        #alldict[k]=alldict[k][idy]

    #print(odbfile,time.time()-t)

    """ may not be necessary to convert into x_array since you can write a pandas df into an HDF file """

    #print('FF alldict_to_xarray is: ', alldict.to_xarray )
   # input('verifica alldicts.to_xarray')
   
   
    alldict.sort_values(by = ['date@hdr', 'time@hdr' , 'vertco_reference_1@body' ] )        
    alldict['observation_id'] = list(alldict.index)  # adding the indices as the observation_id variable, so it can be read afterwards 
    

    
    
    """ Calculate units from variable """      
    # https://github.com/glamod/common_data_model/blob/master/tables/units.dat
    units = []
    var = np.array(alldict['varno@body']).astype(int)
    for f in var:
        try:             
            units.append(cdm_odb_var_dic[f])
            #print(f , ' ',  cdm_odb_var_dic[f] )
        except:
            #print('var is ', f )
            units.append(5555) # should never happen
                
    alldict['units'] = np.array(units).astype(int)
    
    #alldict['vertco_type@body'] = 1
    
    

    return alldict.to_xarray()


            
def fromfb(fbv, cdmfb):
    """ 
    Convert variables from the odb convention to the cdm , e.g.
     tr[1]=117  where 1=geopotential in the odb , 117=geopotential in the cdm 
    """
    
    x=0
    # checks if the type of the variable is a list, so that it uses the function to extract the date time 
    if type(cdmfb) is list:
        x=cdmfb[0](fbv[cdmfb[1]], fbv[cdmfb[2]])
    else:
        if cdmfb=='varno@body': # see , see https://github.com/glamod/common_data_model/blob/master/tables/observed_variable.dat  
            
            #tr=numpy.zeros(113,dtype=int) # fixed length of 113 since the highest var number is 112 
            tr=numpy.zeros(300,dtype=int) # fixed length of 113 since the highest var number is 112 
            
            """ translate odb variables (left) number to CDM numbering convention (right) """
            tr[1]=117  # should change , geopotential height
            tr[2]=85 # air temperature	K
            tr[3]=104 # eastward wind speed
            tr[4]=105 # northward wind speed 
            tr[7]=39 # spec hum
            tr[29]=38 # relative hum
            tr[59]=36 # dew point
            
            tr[111]=106 #dd wind from direction
            tr[112]=107  #ff wind speed 
            #
            #tr[39]= 85 # 2m T ### FIX THESE NUMBERS !!!! 
            tr[40]= 36 # 2m Td
            tr[41]= 104 #10m U
            tr[42]= 105  #10m V
            tr[58]= 38 # 2m rel hum
            try:
                tr[299]= 34 # 2m rel hum
            except:
                pass 
            x=tr[fbv[cdmfb].values.astype(int)] 
        else:    
            x=fbv[cdmfb].values
        
    return x

def ttrans(cdmtype, kinds=kinds):
    """ convert the cdm types to numpy types """    
    nptype=numpy.float32
    try:
        nptype=kinds[cdmtype.strip()]
    except:
        pass
        #print(cdmtype,'not found, using numpy.float32')   
    return nptype


'''
#@njit
def find_dateindex(y):
    """ creates the indices list from the dates, for quick access 
        nb the benchmark script will not work with these files since the definition of the array size is swapped i.e. (x.shape[0], 3)"""        

    
    if debug: 
        print("Running find_dateindex for: ", y)
        
    x=numpy.unique(y)
    z=numpy.zeros((3, x.shape[0]), dtype=numpy.int32 )
    z-=1
    j=0
    for i in range(len(y)):
        m=y[i]
        if x[j]==y[i]:
            if z[1,j]==-1:
                z[1,j]=i
                #print(j,i)
            else:
                if z[2,j]<i:
                    z[2,j]=i
        elif x[j]<y[i]:
            j+=1
            if x[j]==y[i]:
                if z[1,j]==-1:
                    z[1,j]=i
                    #print(j,i)
                else:
                    if z[2,j]<i:
                        z[2,j]=i
            else:
                print('Error Dateindex')
        else:
            j-=1
            if x[j]==y[i]:
                if z[1,j]==-1:
                    z[1,j]=i
                    #print(j,i)
                else:
                    if z[2,j]<i:
                        z[2,j]=i
            else:
                print('Error Dateindex')
    z[0,:]=x
    return z
'''

def find_date_indices(datetime):
    """ Extracts the list of observation dates, and store the indices of the first and last observations 
          Args:: 
                  list of *sorted* observation date_times
          Return:: numpy array (3,:) where the first list is the list of unique obs date_times, the second are the indices of first obs  date_time, the second the list of last obs date_time. 
          """            
    #if debug: 
    #   print("Running find_dateindex")
    #print ('Running find_date_indices *** ')
    datetime =np.array(datetime)     
    #date_times, counts = numpy.unique(datetime, return_counts = True)
    
    date_times, indices, counts = numpy.unique(datetime, return_counts = True, return_index= True)
    
    #z=numpy.zeros((3, date_times.shape[0]), dtype=numpy.int32 )    
    #first, last = [], []    
    
    '''
    for dt, count in zip(date_times, counts):
        f = int( min(np.where( datetime == dt )[0] ) )
        first.append(f)
        last.append(f + count - 1) 

    #z[0,:] = np.array(date_times , dtype='datetime64[ns]')
    #z[1,:] = np.array(first)
    #z[2,:] = np.array(last)
    '''
    
    # convert to date_time object 
    try:
        date_times = [  datetime.strptime(  str(int(i)) , '%Y%m%d%H%M') for i in date_times ]
    except:
        #print('already date_time')
        pass

    return np.array(indices) , date_times,  counts  
          
          
          
          
def readvariables_encodings(fbds):
    """ Extracts the list of variables from the xarray, read from different sources, and assign a variable type for the encodings         
        Args:
               pandas dataframe 
        Return:
               dictionary where each key is a cdm variable, and the values are the variable type and compression methods to be used in the hdf files """  
    
    fbencodings={}
    for d in fbds._variables.keys():
        if fbds.variables[d].dtype==numpy.dtype('float64'):
            if d!='date@hdr' or d!='report_timestamp':             
                fbencodings[d]={'dtype':numpy.dtype('float32'),'compression': 'gzip'} # !! probably dtype not necessary, but compression must be there
            else:
                fbencodings[d]={'dtype':numpy.dtype('int32'),'compression': 'gzip'}               
        else:
                fbencodings[d]={'compression': 'gzip'}
                
    return  fbencodings          
                
def initialize_convertion(fn, output_dir):
    """ Simple initializer for writing the output netCDF file """
    
    fnl=fn.split('/')
    fnl[-1]='ch'+fnl[-1]
    fno=output_dir + '/' + fnl[-1] + '.nc' # creating an output file name e.g. chera5.conv._10393.nc  , try 01009 faster
    return fno 
    
#def get_encodings(cdm, cdmd,fdbs):
#    """ Extract the correct encodings for the variables in the tables """
    
    

def df_to_cdm(cdm, cdmd, out_dir, dataset, fn):
    """ Convert the  pandas dataframe from the file into cdm compliant netCDF files. Use with bufr, igra2 and ncar databases.
        According to each file type, it will use the appropriate reading function to extract a Pandas DataFrame
        input:
              fn       :: odb file name (e.g. era5.conv._10393)
              cdm   :: cdm tables (read with pandas)
              cdmd :: cdm tables definitions ("")  """    
    
    if debug:
        print("Running df_to_cdm for: ", fn)
        
    station_id_fails = open('station_id_fail.log' , 'a') 
    station_id_ok = open('station_id_correct.log' , 'a')
    
    t=time.time()
    fno = initialize_convertion(fn, out_dir )

    station_id = '' 
    if not False:
        
            # era5 analysis feedback is read from compressed netcdf files era5.conv._?????.nc.gz in $RSCRATCH/era5/odbs/1
            """ Reading the odb and convert to xarray """  
            if  '.bfr' in fn:
                fbds= bufr_to_dataframe(fn) # fdbs: the xarray converted from the pandas dataframe 
            elif  'uadb' in fn:
                fbds = uadb_ascii_to_dataframe(fn)
            elif  'data' in fn:
                #print(" analysing an igra dataset")
                fbds = igra2_ascii_to_dataframe(fn)
            else:
                print('Unidentified file is: ', fn)
                raise ValueError('Cannot identify the type of file to be analized!!! ')
                   
            station_id = str( fbds['station_id'].values[0].replace(' ','') )
            
            """ Extract the unique indices of each date observation, one for only dates, one for date_time (i.e. record index). Create an xarray to be saved as a separate variable in the netCDF """  
            di=xr.Dataset() 
            
            indices, date_times, counts = find_date_indices( fbds['iday'].values )   #only date information
            di['dateindex']  = ( { 'dateindex' :  date_times.shape } , date_times )
            
            indices, date_times , counts  = find_date_indices( fbds['record_timestamp'].values ) #date_time plus indices           
            di['recordindex']          =  ( {'recordindex' : indices.shape } , indices )
            di['recordtimestamp']  = (  {'recordtimestamp' : date_times.shape }, date_times  )
            

            """ Extracting the variables type encodings """
            fbencodings = readvariables_encodings(fbds)    
    
            """ Here we extract the name of the variables from the xarray, and we check the type. 
                  According to it, we set the type of the variable in the hdf compressed variable and store the encoding in the fbencodings dictionary
                  Looks like fbencodings = { 'obsvalue@body': {'compression': 'gzip'}, 'sonde_type@conv': {'compression': 'gzip'}, ... } 
 
                  Empty dictionaries for hdf groups (one for each table) and their  hdf encoding description.
                  Each entry in the group dict is an xarray mapping to a single table_definition """
            
            groups={} 
            groupencodings={}
        
            """" Loop over every table_definition in the cdmd dictionary of pandas DF 
                   Two possibilities: 1. the corresponding  table already exists in the cdm (case in the final else)
                                              2. the corr table needs to be created from the local data sources (e.g. the feedback or IGRA or smt else). 
                                                  e.g. the observation_tables, the header_tables and the station_configuration.
                                                  These tables are contained in the CEUAS GitHub but not in the cdm GitHub """
            sci_found = False
            for k in cdmd.keys(): # loop over all the table definitions e.g. ['id_scheme', 'crs', 'station_type', 'observed_variable', 'station_configuration', 'station_configuration_codes', 'observations_table', 'header_table']
                groups[k]=xr.Dataset() # create an xarray for each table
                groupencodings[k]={} # create a dict of group econding for each table
                
                """ Loop over each row in the definition table.
                     In the CDM, the def. tables have the 4 columns ['element_name', 'kind', 'external_table', 'description' ] 
                     d is each element in the DF, so e.g. d.external_table will return the correpsonding value """    
                
                for i in range(len(cdmd[k])): 
                    d=cdmd[k].iloc[i] # extract the element at the i-th row, e.g.   element_name           z_coordinate_type, kind                                 int, external_table    z_coordinate_type:type, description         Type of z coordinate
                                                                             
                    if k in ('observations_table'):
                        try:                                                     
                            groups[k][d.element_name]=( {'hdrlen':fbds.variables['record_timestamp'].shape[0] }, fromfb(fbds._variables, cdmfb_noodb[d.element_name] ) ) # variables contained in the fb extracted from the file
                            
                        except KeyError:
                            x=numpy.zeros(fbds.variables['record_timestamp'].values.shape[0], dtype= numpy.dtype(ttrans(d.kind, kinds=okinds)))
                            x.fill(numpy.nan)
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['record_timestamp'].shape[0]}, x)
                            
                    elif k in ('header_table'):
                        # if the element_name is found in the cdmfb dict, then it copies the data from the odb into the header_table
                        try:
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['record_timestamp'].shape[0] }, fromfb(fbds._variables, cdmfb_noodb[d.element_name] ) )
                        except KeyError:
                            # if not found, it fills the columns with nans of the specified kind. Same for the observation_tables 
                            x= numpy.zeros(fbds.variables['record_timestamp'].values.shape[0],dtype=numpy.dtype(ttrans(d.kind,kinds=okinds) ) )
                            x.fill(numpy.nan)
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['record_timestamp'].shape[0]}, x)
                            
                    elif k in ('station_configuration'): # station_configurationt contains info of all the stations, so this extracts only the one line for the wanted station with the numpy.where
                        try:   
                            if 'sci' not in locals(): 
                                sci = numpy.where(cdm[k]['primary_id']=='0-20000-0-'+ station_id) [0]
                                
                            if len(sci)>0:
                                #print('Found a primary_if matching the station_id: ', station_id)
                                groups[k][d.element_name]=({k+'_len':1},  cdm[k][d.element_name].values[sci] )
                                sci_found = True
                                
                            elif len(sci) == 0:
                                    secondary = list (cdm[k]['secondary_id'].values ) # list of secondary ids in the station_configuration file. I find the element with that specific secondary id
                                    #secondary = [ eval(s)[0] for s in secondary ]
                                    for s in secondary:
                                        lista = [eval(s)[0] ] 

                                        if int(station_id) in lista:
                                                sec = numpy.where(cdm[k]['secondary_id']== s )
                                                groups[k][d.element_name]=({k+'_len':1},  cdm[k][d.element_name].values[sec] )         
                                                sci_found = True
                                                continue
                                    
                        except KeyError:
                            pass
                    elif k in ('source_configuration'): # storing the source configuration info, e.g. original file name, 
                        try:
                            groups[k][d.element_name]=( {'hdrlen':fbds.variables['record_timestamp'].shape[0] }, fromfb(fbds._variables, cdmfb_noodb[d.element_name] ) ) # variables contained in the fb extracted from the file
                        except:    
                            x=numpy.zeros(fbds.variables['record_timestamp'].values.shape[0], dtype= numpy.dtype(ttrans(d.type, kinds=okinds)))
                            x.fill(numpy.nan)
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['record_timestamp'].shape[0]}, x)
                            
                    else : # this is the case where the cdm tables DO exist in th CDM GitHub 
                        try:   
                            groups[k][d.element_name]=({k+'_len':len(cdm[k] ) }, cdm[k][d.element_name].values)  # element_name is the netcdf variable name, which is the column name of the cdm table k 
                        except KeyError:
                            pass
                    try:
                        groups[k][d.element_name].attrs['external_table'] = d.external_table # defining variable attributes that point to other tables (3rd and 4th columns)
                        groups[k][d.element_name].attrs['description']      = d.description
                        #print('good element in cdm table: ' , k, d.element_name ) 
                        groupencodings[k][d.element_name] = {'compression': 'gzip'}
                    except KeyError:
                        #log_file.write('k_d.element_name_error_'  + fn + '\n') 
                        print('bad:', k, d.element_name)
                        pass
    
            #this writes the dateindex to the netcdf file. For faster access it is written into the root group
            """ Writing the di (date index) as a separate xarray. """
            di.to_netcdf(fno, format='netCDF4', engine='h5netcdf', mode='w')
   
            """ Writing the content of the original odb file to the netCDF. For each variable, use the proper type encoding."""
            fbds.to_netcdf(fno, format= 'netCDF4', engine= 'h5netcdf', encoding= fbencodings, group= 'era5fb', mode= 'a')
                        
            """ Writing each separate CDM table to the netCDF file """
            for k in groups.keys():
                #print('check date_time', k)
                
                groups[k].to_netcdf(fno, format='netCDF4', engine='h5netcdf', encoding=groupencodings[k], group=k, mode='a') 
                
            print('sizes: in: {:6.2f} out: {:6.2f}'.format( os.path.getsize( fn) /1024/1024, os.path.getsize( fno )/1024/1024) )
            del fbds
    if sci_found == True: 
        station_id_ok.write(fn + '_' + station_id + '\n' )
    if sci_found == False:
        station_id_fails.write(fn + '_' + station_id + '\n')
    station_id_fails.close()
    station_id_ok.close()
    #print(fno,time.time()-t)
    
    return 0



def odb_to_cdm(cdm, cdmd, output_dir, dataset, fn):
    """ Convert the  file into cdm compliant netCDF files. 
        According to each file type, it will use the appropriate reading function to extract a Pandas DataFrame
        input:
              fn       :: odb file name (e.g. era5.conv._10393)
              cdm   :: cdm tables (read with pandas)
              cdmd :: cdm tables definitions ("")  """

    source_file = [ f for f in fn.split('/') if '.conv' in f][0]
    
    if debug:
        print("Running odb_to_cdm for: ", fn)

    station_id_fails = open('station_id_fail.log' , 'a')
    station_id_ok    = open('station_id_correct.log' , 'a')
        
    t=time.time()
    fno = initialize_convertion(fn, output_dir) 
    station_id = ''    
    if not False:
        
            # era5 analysis feedback is read from compressed netcdf files era5.conv._?????.nc.gz in $RSCRATCH/era5/odbs/1
            """ Reading the odb and convert to xarray """                      
            fbds=read_all_odbsql_stn_withfeedback(fn) # fdbs: the xarray converted from the pandas dataframe 

            station_id = fbds['statid@hdr'].values[0].decode('latin1').replace(' ','')
            if ':' in station_id:
                station_id = station_id.split(':')[1] 
            if len(station_id)==4:
                station_id = '0' + station_id
                 
            """ Extract the unique indices of each date observation. Create an xarray to be saved as a separate variable in the netCDF """         
            di=xr.Dataset() 
                        
            # The variable iday contains only dates (no time information)
            indices, dates, counts = find_date_indices( fbds['date@hdr'].values )
            di['dateindex']  = ( { 'dateindex' :  indices.shape } , indices )
            
            # Add the record_index (date + time information)
            date_time=fbds['date@hdr'].values*100+fbds['time@hdr'].values//10000 # creating the date_time variable for odb files 
            
            
            
            #date_time = [ datetime.strptime(str(int(i)), '%Y%m%d%H') for i in date_time  ] # convert to datetime object 
            
            indices, date_times , counts = find_date_indices (date_time) 
            
            date_times = np.array( [ datetime.strptime(str(int(i)), '%Y%m%d%H') for i in date_times  ] )# convert to datetime object 
            
            di['recordindex']          = ( {'recordindex' : indices.shape } , indices )
            di['recordtimestamp']  = ( {'recordtimestamp' : date_times.shape }, date_times )    
            
            """ Building report_id to add to the header table - only needed for era5 datasets """
            report_id = []
            for c, i in zip (counts, range(1,len(counts)+1) ) :
                for t in range(c):
                    report_id.append(i)
            
            report_id = np.array(report_id).astype(int)
            
            #fbds['report_id'] = ( {'report_id' : report_id.shape }, report_id ) 
            
            fbds['report_id']          = ( {'index' : report_id.shape } , report_id )
            
                       
            """
            indices, date_times = find_date_indices( fbds['iday'].values )   #only date information
            di['dateindex']  = ( { 'dateindex' :  date_times.shape } , date_times )
            
            indices, date_times   = find_date_indices( fbds['report_timestamp'].values ) #date_time plus indices           
            di['recordindex']          =  ( {'recordindex' : indices.shape } , indices )
            di['recordtimestamp']  = (  {'recordtimestamp' : date_times.shape }, date_times  )
            """
            
            """ Extracting the variables type encodings """
            fbencodings = readvariables_encodings(fbds)
            
            """ Here we extract the name of the variables from the xarray, and we check the type. 
                  According to it, we set the type of the variable in the hdf compressed variable and store the encoding in the fbencodings dictionary
                  Looks like fbencodings = { 'obsvalue@body': {'compression': 'gzip'}, 'sonde_type@conv': {'compression': 'gzip'}, ... } 
 
                  Empty dictionaries for hdf groups (one for each table) and their  hdf encoding description.
                  Each entry in the group dict is an xarray mapping to a single table_definition """
            
            groups={} 
            groupencodings={}
        
            """" Loop over every table_definition in the cdmd dictionary of pandas DF 
                   Two possibilities: 1. the corresponding  table already exists in the cdm (case in the final else)
                                              2. the corr table needs to be created from the local data sources (e.g. the feedback or IGRA or smt else). 
                                                  e.g. the observation_tables, the header_tables and the station_configuration.
                                                  These tables are contained in the CEUAS GitHub but not in the cdm GitHub """
            sci_found = False
            
            print ('Starting the loop: ***** ' )
            for k in cdmd.keys(): # loop over all the table definitions e.g. ['id_scheme', 'crs', 'station_type', 'observed_variable', 'station_configuration', 'station_configuration_codes', 'observations_table', 'header_table']
                groups[k]=xr.Dataset() # create an xarray for each table
                groupencodings[k]={} # create a dict of group econding for each table
                
                """ Loop over each row in the definition table.
                     In the CDM, the def. tables have the 4 columns ['element_name', 'kind', 'external_table', 'description' ] 
                     d is each element in the DF, so e.g. d.external_table will return the correpsonding value """    
                
                for i in range(len(cdmd[k])): 
                    d=cdmd[k].iloc[i] # extract the element at the i-th row, e.g.   element_name           z_coordinate_type, kind                                 int, external_table    z_coordinate_type:type, description         Type of z coordinate
                                                                             
                    if k in ('observations_table'):
                        #print('Doing the observations_table ****')
                        
                        try:                                                     
                            groups[k][d.element_name]=( {'hdrlen':fbds.variables['date@hdr'].shape[0] }, fromfb(fbds._variables, cdmfb[d.element_name] ) )
                            
                        except KeyError:
                            x=numpy.zeros(fbds.variables['date@hdr'].values.shape[0], dtype= numpy.dtype(ttrans(d.kind, kinds=okinds)))
                            x.fill(numpy.nan)
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['date@hdr'].shape[0]}, x)
                            
                    elif k in ('header_table'):
                        #print('Doing the header_table ****')
                        
                        # if the element_name is found in the cdmfb dict, then it copies the data from the odb into the header_table
                        try:
                            if d.element_name == 'report_id':                                
                                groups[k][d.element_name]= ({'hdrlen':fbds.variables['date@hdr'].shape[0] }, report_id )
                            else:
                                groups[k][d.element_name]= ({'hdrlen':fbds.variables['date@hdr'].shape[0] }, fromfb(fbds._variables, cdmfb[d.element_name] ) )
                                
                                
                        except KeyError:
                            # if not found, it fills the columns with nans of the specified kind. Same for the observation_tables 
                            x= numpy.zeros(fbds.variables['date@hdr'].values.shape[0],dtype=numpy.dtype(ttrans(d.kind,kinds=okinds)))
                            x.fill(numpy.nan)
                            groups[k][d.element_name]= ({'hdrlen':fbds.variables['date@hdr'].shape[0]}, x)
                            
                    elif k in ('station_configuration'): # station_configurationt contains info of all the stations, so this extracts only the one line for the wanted station with the numpy.where
                        #print('Doing the station_configuration ****')           
                        
                        try: 
                            """  
                            if 'sci' not in locals(): 
                                sci  = numpy.where(cdm[k]['primary_id']     == '0-20000-0-'+ station_id)[0]
                                sec = numpy.where(cdm[k]['secondary_id'] == station_id)[0]
                            if len(sci)>0 and len(sec) <1:
                                groups[k][d.element_name]=({k+'_len':1}, cdm[k][d.element_name].values[sci])
                                sci_found = True

                            elif len(sci) < 1 and len(sec) > 0:
                                groups[k][d.element_name]=({k+'_len':1}, cdm[k][d.element_name].values[sec]) # added the secondary id if primary not available 
                                sci_found = True
                            """
                        
                            if 'sci' not in locals():
                                sci = numpy.where(cdm[k]['primary_id']=='0-20000-0-'+ station_id) [0]

                            if len(sci)>0:
                                #print('Found a primary_if matching the station_id: ', station_id)                                                                                                                                                                                        
                                groups[k][d.element_name]=({k+'_len':1},  cdm[k][d.element_name].values[sci] )
                                sci_found = True

                            elif len(sci) == 0:
                                    secondary = list (cdm[k]['secondary_id'].values ) # list of secondary ids in the station_configuration file. I find the element with that specific secondary id                                                                                       
                                    #secondary = [ eval(s)[0] for s in secondary ]                                                                                                                                                                                                        
                                    for s in secondary:
                                        try:                                        
                                            lista = [eval(s)[0] ]
                                        except IndexError:
                                            lista = []
                                            sci_found = False 
                                        if int(station_id) in lista:
                                                sec = numpy.where(cdm[k]['secondary_id']== s )
                                                groups[k][d.element_name]=({k+'_len':1},  cdm[k][d.element_name].values[sec] )
                                                sci_found = True
                                                continue
    
                        except KeyError:
                            pass                     
                        
                    elif k in ('source_configuration'): # storing the source configuration info, e.g. original file name, 
                        #print('Doing the source_configuration ****')                        
                        if d.element_name == 'source_file' :
                            groups[k][d.element_name] = ( {'hdrlen':fbds.variables['date@hdr'].shape[0] } ,  np.full( fbds.variables['date@hdr'].shape[0] , source_file  ) ) 
                        elif d.element_name == 'product_code' :
                            groups[k][d.element_name] = ( {'hdrlen':fbds.variables['date@hdr'].shape[0] } ,  np.full( fbds.variables['date@hdr'].shape[0] , dataset  ) ) 

                        else:    
                            groups[k][d.element_name] = ( {'hdrlen':fbds.variables['date@hdr'].shape[0] } ,  np.full( fbds.variables['date@hdr'].shape[0] , np.nan ) )                                                     
                            
                    else : # this is the case where the cdm tables DO exist
                        try:   
                            groups[k][d.element_name]=({k+'_len':len(cdm[k])},
                                        cdm[k][d.element_name].values) # element_name is the netcdf variable name, which is the column name of the cdm table k 
                        except KeyError:
                            pass
                        
                    if k == 'station_configuration' or k == 'source_configuration':    
                        try:
                            groups[k][d.element_name].attrs['external_table'] = d.external_table # defining variable attributes that point to other tables (3rd and 4th columns)
                            groups[k][d.element_name].attrs['description']      = d.description
                            groupencodings[k][d.element_name] = {'compression': 'gzip'}                            
                        except KeyError:
                            print('bad:', k, d.element_name)
                            pass
                        
                    else:
                        try:
                            groups[k][d.element_name].attrs['external_table'] = d.external_table # defining variable attributes that point to other tables (3rd and 4th columns)
                            groups[k][d.element_name].attrs['description']      = d.description
                            if d.element_name not in ['report_id', 'observation_id']:                                
                                groupencodings[k][d.element_name] = {'compression': 'gzip' ,  'dtype' : np.dtype(ttrans(d.kind, kinds=okinds) )}  ### does not work properly with all the encodings!  
                            else:
                                groupencodings[k][d.element_name] = {'compression': 'gzip' ,  'dtype' : np.dtype(int) }
                        except KeyError:
                            print('bad:', k, d.element_name)
                            pass                            
                          
            #this writes the dateindex to the netcdf file. For faster access it is written into the root group
            """ Wiriting the di (date index) as a separate xarray. """
            di.to_netcdf(fno, format='netCDF4', engine='h5netcdf', mode='w')
         
            """ Writing the content of the original odb file to the netCDF. For each variable, use the proper type encoding."""
            print('Writing the output netCDF file (era5fb) ****** ')
            fbds.to_netcdf(fno, format='netCDF4', engine='h5netcdf', encoding=fbencodings, group='era5fb',mode='a')
                        
            """ Writing each separate CDM table to the netCDF file """
            for k in groups.keys():
                print('Writing the output netCDF file group ' , k , ' **** ' )              
                groups[k].to_netcdf(fno, format='netCDF4', engine='h5netcdf', encoding=groupencodings[k], group=k, mode='a') 
                
            print('sizes: in: {:6.2f} out: {:6.2f}'.format( os.path.getsize( fn) /1024/1024, os.path.getsize( fno )/1024/1024) )
            del fbds
        
    if sci_found == True:
        station_id_ok.write(fn + '_' + station_id + '\n' )
    else:
        station_id_fails.write(fn + '_' + station_id + '\n')
    station_id_fails.close()
    station_id_ok.close()
    print(fno,time.time()-t)
    
    return 0


            
            
            

def load_cdm_tables():
    """ Load the cdm tables into Panda DataFrames, reading the tables from the cdm GitHub page FF To do 
    
          Return:
                      dictionary with a Panda DataFrame for each table """
    
    
    
    """ # Uncomment to get the list of all the .csv files present at the url specified
    url = 'https://github.com/glamod/common_data_model/tree/master/table_definitions'
    cdmtabledeflist = csvListFromUrls(url)
    """
    tpath = os.getcwd() + '/../data'
    cdmpath='https://raw.githubusercontent.com/glamod/common_data_model/master/tables/' # cdm tables            
    
    """ Selecting the list of table definitions. Some of the entires do not have the corresponding implemented tables """
    cdmtabledeflist=['id_scheme', 'crs', 'station_type', 'observed_variable', 'station_configuration', 'station_configuration_codes', 'observations_table', 'header_table', 'source_configuration', 'units' , 'z_coordinate_type']  
    cdm_tabdef = dict()
    for key in cdmtabledeflist:
        url='table_definitions'.join(cdmpath.split('tables'))+key+'.csv' # https://github.com/glamod/common_data_model/tree/master/table_definitions/ + ..._.dat 
        f=urllib.request.urlopen(url)
        col_names=pd.read_csv(f,delimiter='\t',quoting=3,nrows=0,comment='#')
        f=urllib.request.urlopen(url)
        tdict={col: str for col in col_names}
        cdm_tabdef[key]=pd.read_csv(f,delimiter='\t',quoting=3,dtype=tdict,na_filter=False,comment='#')
        
    
    """ Selecting the list of tables. 'station_configuration_codes','observations_table','header_table' are not implemented in the CDM GitHub"""        
    cdmtablelist=['id_scheme', 'crs', 'station_type', 'observed_variable', 'station_configuration_codes','units']        
    cdm_tab=dict() # dictionary where each key is the name of the cdm table, and the value is read from the .dat file    
    for key in cdmtablelist:
        f=urllib.request.urlopen(cdmpath+key+'.dat')
        col_names=pd.read_csv(f,delimiter='\t',quoting=3,nrows=0)
        f=urllib.request.urlopen(cdmpath+key+'.dat')
        tdict={col: str for col in col_names}
        cdm_tab[key]=pd.read_csv(f,delimiter='\t',quoting=3,dtype=tdict,na_filter=False)


    """ Adding the  tables that currently only have the definitions but not the implementation in the CDM, OR    need extensions """  
    cdm_tabdef['header_table']          = pd.read_csv(tpath+'/table_definitions/header_table.csv',delimiter='\t',quoting=3,comment='#')
    cdm_tabdef['observations_table'] = pd.read_csv(tpath+'/table_definitions/observations_table.csv',delimiter='\t',quoting=3,comment='#')

    id_scheme={ cdm_tabdef['id_scheme'].element_name.values[0]:[0,1,2,3,4,5,6],
                         cdm_tabdef['id_scheme'].element_name.values[1]:['WMO Identifier','Volunteer Observing Ships network code',
                                                             'WBAN Identifier','ICAO call sign','CHUAN Identifier',
                                                             'WIGOS Identifier','Specially constructed Identifier']}

    cdm_tab['id_scheme']=pd.DataFrame(id_scheme)
    #cdm['id_scheme'].to_csv(tpath+'/id_scheme_ua.dat')
    cdm_tab['crs']=pd.DataFrame({'crs':[0],'description':['wgs84']})
    #cdm['crs'].to_csv(tpath+'/crs_ua.dat')
    
    """ Here we add missing entries, e.g. in the z_coordinate_type for the pressure levels in Pascal (the available CDM table in the glamod GitHub rep.  contains onle the altitude in [meter] """
    
    cdm_tab['station_type']=pd.DataFrame({'type':[0,1],'description':['Radiosonde','Pilot']}) 
    cdm_tab['z_coordinate_type']=pd.DataFrame({'type':[0,1],'description':['height (m) above sea level','pressure (Pa)']})  # only the m above sea level is available currently in the GitHub cdm table, added pressure 
    
    #cdm['station_type'].to_csv(tpath+'/station_type_ua.dat')
    #cdm['observed_variable']=pd.read_csv(tpath+'/observed_variable.dat',delimiter='\t',quoting=3,dtype=tdict,na_filter=False,comment='#')   
    
    
    return cdm_tabdef  , cdm_tab, tdict


def csvListFromUrls(url=''):
    """ Return a list of csv files, as fond in the url on the cdm GitHub """   
    urlpath = urlopen(url)
    string = urlpath.read().decode('utf-8')
    split = string.split(' ')
    csv_files_list = [m.replace('"','') for m in [n.split('title="')[1] for n in split if '.csv' in n and "title" in n] ] 
    return csv_files_list



def filelist_cleaner(lista, dataset=''):
    """ Removes unwanted files that might be present in the database directories """
    print('Cleaning the list of files to be converted')
    if dataset == 'ncar':
        cleaned = [ l for l in lista if '.nc' not in l ]
    if dataset == 'bufr':
        cleaned = [ l for l in lista if '.bfr' in l ]
    if 'era5' in dataset:
        cleaned = [ l for l in lista if '.nc' not in l and '.conv.' in l ]
    else:
        cleaned = lista
    
    return cleaned
   
""" Sources of the files """
db   = { 'era5_1'       : { 'dbpath' : '/raid60/scratch/leo/scratch/era5/odbs/1'            , 'stat_conf' : 'station_configuration_era5_1.dat'       , 'example': 'era5.conv._01009'    } ,
              'era5_3188' : { 'dbpath' : '/raid60/scratch/leo/scratch/era5/odbs/3188'      , 'stat_conf' : 'station_configuration_era5_3188.dat'  , 'example': 'era5.3188.conv.C:6072'    } ,
              'era5_1759' : { 'dbpath' : '/raid60/scratch/leo/scratch/era5/odbs/1759'      , 'stat_conf' : 'station_configuration_era5_1759.dat'  , 'example': 'era5.1759.conv.6:99041'   } ,
              'era5_1761' : { 'dbpath' : '/raid60/scratch/leo/scratch/era5/odbs/1761'      , 'stat_conf' : 'station_configuration_era5_1761.dat'  , 'example': 'era5.1761.conv.9:967'     } ,
              'ncar'           : { 'dbpath' : '/raid60/scratch/federico/databases/UADB'         , 'stat_conf' : 'station_configuration_ncar.dat'            , 'example': 'uadb_trhc_81405.txt' } ,
              'ncar'           : { 'dbpath' : '/raid60/scratch/federico/databases/UADB'         , 'stat_conf' : 'station_configuration_ncar.dat'            , 'example': 'uadb_windc_97086.txt' } ,
              'igra2'          : { 'dbpath' : '/raid60/scratch/federico/databases/IGRAv2'      , 'stat_conf' : 'station_configuration_igra2.dat'           , 'example': 'BRM00082571-data.txt' } ,
              'bufr'            : { 'dbpath' : '/raid60/scratch/leo/scratch/era5/odbs/ai_bfr'    , 'stat_conf' : 'station_configuration_bufr.dat'             , 'example': 'era5.94998.bfr'     }    }



if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Make CDM compliant netCDFs")
    parser.add_argument('--dataset' , '-d', 
                    help="Select the dataset to convert. Available options: all, era5_1, era5_1759, era5_1761, bufr, igra2, ncar, test. If not selected or equal to 'test', the script will run the example files in the /examples directory."  ,
                    default = 'test',
                    type = str)
    
    parser.add_argument('--output' , '-o', 
                    help="Select the output directory. If not selected, converted files will be stored in the 'converted_files' directory."  ,
                    default = 'converted_files',
                    type = str)    
    
    parser.add_argument('--files' , '-f',
                    help = "File to be processed."  ,
                        default = '',
                        type = str)    
    
    """
    parser.add_argument('--auxtables_dir' , '-a', 
                    help="Optional: path to the auxiliary tables directory. If not given, will use the files in the data/tables directory" ,
                    default = '../../cdm/data/',
                    type = str)
    parser.add_argument('--odbtables_dir' , '-odb', 
                    help="Optional: path to the odb tables directory. If not given, will use the files in the data/tables directory" ,
                    #default = '../../cdm/data/tables/',
                    default = '/raid60/scratch/leo/scratch/era5/odbs/',
                    type = str)
    parser.add_argument('--output_dir' , '-out',
                    help="Optional: path to the netcdf output directory" ,
                    default = '../../cdm/data/tables',
                    type = str)
    

    args = parser.parse_args()
    dpath = args.database_dir
    tpath = args.auxtables_dir
    output_dir = args.output_dir
    odbpath = args.odbtables_dir
    """
    
    args = parser.parse_args()
    dataset = args.dataset 
    out_dir = args.output
    Files = args.files

    if dataset not in ['era5_1', 'era5_3188', 'era5_1759', 'era5_1761', 'bufr', 'igra2', 'ncar', 'test', 'all' ]:
        raise ValueError(" The selected dataset is not valid. Please choose from ['era5_1', 'era5_1759', 'era5_1761', 'era5_3188', 'bufr', 'igra2', 'ncar', 'test', 'all' ]  ")
    
                        
    """ Loading the CDM tables into pandas dataframes """
    cdm_tabdef  , cdm_tab , tdict = load_cdm_tables()
    
 
    """ Paths to the databases """    
    examples_dir = os.getcwd() + '/examples'
    stat_conf_dir = os.getcwd() + '/stations_configurations/'   

    if dataset == 'test':
        
        if not os.path.isdir(out_dir):
            os.system('mkdir ' + out_dir )
                 
        output_dir = out_dir + '/tests'        
        if not os.path.isdir(output_dir):
                os.system('mkdir ' + output_dir )
        
        """  To run one example file included in the examples/ directory """
        print( blue + '*** Running the example files stored in ' + examples_dir + ' ***  \n \n ' + cend)

        #for s in db.keys() :
        for s in ['igra2']:
                        
            stat_conf_file = stat_conf_dir +  db[s]['stat_conf']            
            f = examples_dir + '/' + db[s]['example']    
            
            print('Analyzing the file: *** ', f  )            
            cdm_tab['station_configuration']=pd.read_csv(stat_conf_file,  delimiter='\t', quoting=3, dtype=tdict, na_filter=False, comment='#')
            
            if 'era5' in s and 'bufr' not in s:                             
                odb_to_cdm(cdm_tab, cdm_tabdef, output_dir, dataset, f)    

            else:    
                df_to_cdm(cdm_tab, cdm_tabdef, output_dir, dataset, f)
        
        print('****** \n \n \n Finished processing the file : ', f)
        
    else:
        Files = Files.split(',')
        
        if not os.path.isdir(out_dir):
            os.system('mkdir ' + out_dir )       
            
        output_dir = out_dir + '/' + dataset           
        if not os.path.isdir(output_dir):
            os.system('mkdir ' + output_dir )
            
        for File in Files:
                 
            print( blue + '*** Processing the database ' + dataset + ' ***  \n \n *** file: ' + File + '\n'  + cend)
                
            stat_conf_file = stat_conf_dir +  db[dataset]['stat_conf']
                
            # adding the station configuration to the cdm tables      
            cdm_tab['station_configuration']=pd.read_csv(stat_conf_file,  delimiter='\t', quoting=3, dtype=tdict, na_filter=False, comment='#')
                
            if 'era5' in dataset and 'bufr' not in dataset:   
                odb_to_cdm( cdm_tab, cdm_tabdef, output_dir, dataset, File)
            else:
                df_to_cdm( cdm_tab, cdm_tabdef, output_dir, dataset, File)
            print('*** CONVERTED: ' , File )
      
    print(' ***** Convertion of  ' , Files,  '  completed ! ***** ')




""" Example command lines to run and save in the directory 'OUTPUT' 

/opt/anaconda3/bin/python3 build_311c_cdmfiles_ALL_split.py -f /raid60/scratch/leo/scratch/era5/odbs/1/era5.conv._82930 -d era5_1 -o OUTPUT
/opt/anaconda3/bin/python3 build_311c_cdmfiles_ALL_split.py -f /raid60/scratch/leo/scratch/era5/odbs/1759/era5.1759.conv.1:82930 -d era5_1759 -o OUTPUT
/opt/anaconda3/bin/python3 build_311c_cdmfiles_ALL_split.py -f /raid60/scratch/federico/databases/IGRAv2/BRM00082930-data.txt -d igra2 -o OUTPUT
/opt/anaconda3/bin/python3 build_311c_cdmfiles_ALL_split.py -f /raid60/scratch/federico/databases/UADB//uadb_windc_82930.txt -d ncar -o OUTPUT
/opt/anaconda3/bin/python3 build_311c_cdmfiles_ALL_split.py -f /raid60/scratch/leo/scratch/era5/odbs/ai_bfr/era5.82930.bfr -d bufr -o OUTPUT


 ['/raid60/scratch/leo/scratch/era5/odbs/ai_bfr/era5.62760.bfr', '/raid60/scratch/leo/scratch/era5/odbs/ai_bfr/era5.62805.bfr', '/raid60/scratch/leo/scratch/era5/odbs/ai_bfr/era5.63630.bfr',
 
 
"""


