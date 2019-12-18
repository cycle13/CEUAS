""" Merging the station configuration files """

import os,sys
import netCDF4 as nc
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pylab as plt
import argparse
from datetime import datetime, timedelta
import numpy.ma as ma
import math
import h5py as h5py
import xarray as xr 
import time 
from numba import njit

pd.set_option('display.max_rows', 50)
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 300)


def now( time ):
      a = datetime.fromtimestamp(time).strftime('%Y-%m-%d %H:%M:%S')
      return  a

"""
For v.0 of the merged dataset

- skip all the data with no pressure information (might have only gepotential; to use these, we will rely on reanalyses data. To Do for next versions)
- igra removed data which did not pass the quality check. If the record is selected from other datasets for some reasons, we keep the data even if removed
- we create a unique record id for the merged dataset in the following way:
     create a nu,bering scheme for each dataset, see dictionary  dataset_id_scheme = {} 
     multiply this number by 1 billion
     add the original dataset record_id to the number
This way, the merged observation_id is unique and it also sotres the original dataset observation_id 
"""
      
class Merger():
      """ Class for the merging of the data from different netCDF files """
      def __init__(self ):
            self.data = {}
            self.datasets = ''
            self.datasets_keys = ''
            self.datasets_all = ['igra2' , 'era5_1' , 'ncar' , 'bufr' , 'era5_1759' , 'era5_1761' , 'era5_3188']
            self.observation_ids_merged = {  'igra2':1 , 'ncar':2 , 'bufr':3,  'era5_1':4 , 'era5_1759' :5 , 'era5_1761':6 ,  'era5_3188' :7}  
            
      def InitializeData(self, datasets = {} , fast = False ):
            """ Initialize dataset. 
                       Args:: datasets (dictionary where key+ dataset name e.g. bufr, igra2 etc. , and value is the path to the netCDF file """
            data = {}
            self.datasets = datasets
            self.datasets_keys = datasets.keys()
            if fast:
                return  
            for k,v in datasets.items() :
                  data[k] = {} 
                  
                  ### xarray                  
                  #ds =  xr.load_dataset(v)   
                  #observations_table =  xr.open_dataset(v , engine = 'h5netcdf' , group = 'observations_table')   
                  
                  #print('xarray')
                  #data[k]['df'] = ds # storing the entire file                
                  #data[k]['dateindex']       = ds['dateindex'][0,:]  # storing the dateindex 
                  #data[k]['source_file']      = ds['source_configuration']['source_file'][0]
                  #data[k]['product_code'] = ds['source_configuration']['product_code'][0]                                       
                  
                  ###for h5py but cant extract date time units !!!                  
                  ds =  h5py.File(v)   
                  data[k]['df'] = ds # storing the entire file                
                  data[k]['dateindex']       = ds['dateindex'][0,:]  # storing the dateindex 
                  data[k]['source_file']      = ds['source_configuration']['source_file'][0]
                  data[k]['product_code']  = ds['source_configuration']['product_code'][0]                  
                  #ds.close()
                  

                  data[k]['station_configuration'] = xr.open_dataset(v , engine = 'h5netcdf' , group = 'station_configuration').to_dataframe()  # this is a single line dataframe 
                  data[k]['source_configuration'] = xr.open_dataset(v , engine = 'h5netcdf' , group = 'source_configuration').to_dataframe()  # this is a single line dataframe 
                  
                  ### for netCDF4
                  #ds =  nc.Dataset(v)                   
                  #data[k]['dateindex'] = ds.variables['dateindex'][0,:]  # storing the dateindex                
                  #data[k]['source_file']      = ds.groups['source_configuration']['source_file'][0]
                  #data[k]['product_code']  = ds.groups['source_configuration']['product_code'][0]
               
            self.data = data
            self.MakeCDMOutputTables()
            self.MakeDataframe()

        
      def MakeCDMOutputTables(self):
            """ Store the CDM tables for the output netCDF file """
            tables = { 'observations_table' : { 'observation_value'   : [] ,
                                                                    'observed_variable'  : [] , 
                                                                    'z_coordinate_type'  : [] ,
                                                                    'date_time'               : [] ,
                                                                    'longitude'                : [] ,
                                                                    'latitude'                   : [] , 
                                                                    'observation_id'        : [] ,     
                                                                    'source_id'                : [] } ,
                       
                             'source_configuration' : {'source_id' : [] ,
                                                                     'source_file' : [] }                      
                       }
            
            source_configuration = {}
            
            for k,v in self.datasets.items():
                  source_configuration[k] = {} 
                  source_configuration[k]['source_file'] = [ c for c in v.split('/') if '.nc' in c][0]
             
            self.source_configuration =  source_configuration
            self.CDMTables = tables       
           

      def MakeDateTime(self, date_time = '', time_offset = '' , shortener = False):   # only consider a small number of entries           
            """ Calculating the actual date_time from the time offset and the time deltas stored in ['observations_table']['date_time'] """
            print('*** Calculating the real date_time from the first date_time observed and the date_time deltas')
                                    
            time_offset_value           = time_offset.split('since ')[1]                            
            time_offset_value           = datetime.strptime(time_offset_value, '%Y-%m-%d %H:%M:%S')
           
            if 'minutes' in  time_offset:
                  delta = [ timedelta(minutes = float(i) ) for i in date_time ]
            elif 'hours' in time_offset:
                  delta = [ timedelta(hours = float(i) )    for i in date_time ]                  

            real_time = 0
            dt = [i for i in  [  time_offset_value + i  for i in delta  ] ]                              
            return dt   
        
      def MakeDataframe(self):
            """ Creating a panda df out of the netCDF file """
            for k in self.datasets_keys:
            #for k in ['igra2' , 'ncar']:
            
                  print('*** Creating the dataframe for the dataset:  ' , k )
                  
                  p_levels               = self.data[k]['df']['observations_table']['z_coordinate'][:]
                  print('     Loading the  z_coordinate')
                  z_type                 = self.data[k]['df']['observations_table']['z_coordinate_type'][:]
                  print('     Loading the  z_coordinate_type')
                  obs_variable        = self.data[k]['df']['observations_table']['observed_variable'][:]
                  print('     Loading the  observed_variable')
                  obs_values          = self.data[k]['df']['observations_table']['observation_value'][:]
                  print('     Loading the  observation_value')
                  observation_id    = self.data[k]['df']['observations_table']['observation_id'][:]
                  print('     Loading the  observation_id')
                  report_id             = self.data[k]['df']['header_table']['report_id'][:]
                  print('     Loading the  report_id')
                  date_time           = self.data[k]['df']['observations_table']['date_time'][:]
                  print('     Loading the  date_time (deltas)')
                  lat , lon = self.data[k]['df']['observations_table']['latitude'][:] , self.data[k]['df']['observations_table']['longitude'][:]
                  
                  self.data[k]['df'].close()
                  
                  """ Converting to proper date_time using the time offset i.e. earliest date_time of observation """ 
                  time_offset = nc.Dataset(self.datasets[k])
                  time_offset = time_offset.groups['observations_table']['date_time'].units # cannot use h5py
                  date_time = self.MakeDateTime(date_time= date_time, time_offset = time_offset , shortener=False)                                 
                                 
                  """ Creating a dataframe """               
                  columns = ['date_time' , 'z_coordinate' , 'z_coordinate_type', 'observed_variable' , 'observation_value' , 'report_id' , 'observation_id' , 'latitude' , 'longitude' ]
                  
                  df = pd.DataFrame( list(zip( date_time , p_levels, z_type, obs_variable , obs_values, report_id,  observation_id , lat , lon ) ) , columns = columns )                 
                  df.sort_values(by = ['date_time', 'observed_variable' ] )    
                  
                  """ Converting variables to a specific data type """
                  variables_types = { 'z_coordinate' : 'float' , 'z_coordinate_type': 'int', 'observation_value':'float' , 'observed_variable':'int' , 'report_id': 'int' , 'observation_id':'int'} 
                  if 'era5' in k:
                        lista = df.index[:]
                        df['report_id'] = lista
                        df['observation_id'] = lista
                        
                  for p,v in variables_types.items(): 
                        df[p].astype(v) 
                        
                  """ Storing the dataframe """      ### try using xarrays ??? 
                  self.data[k]['dataframe'] = df
                  
                  print('      Dataframe created !!! ')
   
      def Save_DataFrame(self):
            for k in  self.datasets_keys:                 
                  self.data[k]['dataframe'].to_pickle(k + '_dic')       
            
      def MakeAllData(self , pickle = False):            
            """ Creates a global dataframe from the dataframe of each dataset.
                 """
            if pickle:
                  print('Loading pickle file')
                  a = np.load('all_data.npy' , allow_pickle = True)
                  print('Pickle Loaded')
                  return a 
            
            def vectorize_panda_numpy(dt='', all_data = '', k='' , index = '' , index_up = ''):
                  dataframe = self.data[k]['dataframe'][index:index_up]
                  observed_variable = dataframe['observed_variable'].values
                  press    = dataframe['z_coordinate'].values
                  z_type    = dataframe['z_coordinate_type'].values                  
                  for v,p,z in zip (observed_variable, press, z_type):
                        if p == -99999.0 :
                              continue
                        if z != 2 :                    # i.e. not equal to geopotential           
                              try:
                                    all_data[dt][k][v].append( p )
                              except:
                                    all_data[dt][k][v] = []
                                    all_data[dt][k][v].append( p )
                        '''
                        #TODO deal with geopotential 
                        elif z==2:
                              try:
                                    all_data[dt][k][v].append( np.nan )
                              except:
                                    all_data[dt][k][v] = []
                                    all_data[dt][k][v].append( np.nan )                              
                        '''
      
            all_data = { }
            print('   Making all data')
            for k in self.datasets_keys:
                  print('--- ', k )
                  unique = self.unique_dates[k]['unique_dates'] 
                  indices, indices_up = self.unique_dates[k]['indices'] , self.unique_dates[k]['indices_up']

                  print('Starting the loop over the dataframe at ',  datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') )
                  
                  for dt, indices, indices_up in zip(unique, indices, indices_up):                                            
                        try:
                              all_data[dt][k] = {}                                      
                        except:
                              all_data[dt] = {}                           
                              all_data[dt][k] = {}           
                         
                        """ For each differnet dt I extract the different pressures I have for each different variable v :: all_data[dt][k][v].append(p) """      
                        a = vectorize_panda_numpy(dt=dt, all_data=all_data, k=k, index=indices, index_up=indices_up)

                        #loc = smaller_df.loc[smaller_df['date_time'] == dt]  # extract the items for this particular date_time 
         
                  print('Finished the loop over the dataframe at ',  datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return all_data
   
           
      def MakeAllDateTime(self): 
            """ Creates a dictionary of unique date_times for each dataset, and a global list of date_times from all the different dataset. 
                  For each date_time, it also stores the index where it is found in each dataset """
            print('Extracting all the observation date_time ***')
      
            unique_dates = {}  
            all_dates = {}
            all_dates['all_dates'] = []
            
            for k in self.datasets_keys:
                  print ("dates for dataset:" , k )
                  
                  unique_dates[k] = {}
                  unique_dates[k]['index'] = {} 
                  unique_dates[k]['index_up'] = {} 

                  unique_dates[k]['indices'] = [] 
                  unique_dates[k]['indices_up'] = []
                   
                  all_dates[k] = {}  # store the index of the date_time of each dictionary
                  
                  date_time = self.data[k]['dataframe']['date_time'].values 
                                  
                  unique = np.unique(np.asarray( date_time ) )
                  unique.sort()
                  unique_dates[k]['unique_dates'] = unique
                                   
                  for dt in unique :                             
                        unique_dates[k]['index'][dt] = ''
                        matching = np.where( date_time== dt)                       
                        index = min(matching[0] )
                        index_up = max(matching[0] ) + 1
                        
                        unique_dates[k]['index'][dt] = index
                        unique_dates[k]['index_up'][dt] = index_up                         
                        unique_dates[k]['indices'].append(index) 
                        unique_dates[k]['indices_up'].append(index_up) 
                                                           
                  all_dates['all_dates'] = all_dates['all_dates'] + list(unique)                   
                                  
                  print('check indices')
                        
            all_dates['all_dates'].sort()
            print('Done with the date_times ***')
            
            self.all_dates = all_dates
            self.unique_dates = unique_dates


      def MergeAllData(self, dictionary_data = ''):
            """ Construct a dictionary with all the dataframes of each dataset, either reading it from saved pickles or reading it from memory """
            
            print('***** Starting the merging process ')
            
            date_times = list(dictionary_data.keys())  # all possible observation dates 
            date_times.sort()
               
            all_var = [38, 85, 106, 107, 117, -7777 ]   # all possible variables (hardcoded) , -7777 is dummy
            all_merged_df = []
            
            """ Dictionary that will contain the merged file. """            
            Merged = {}             
            #for dt in date_times[0:4]: # loop over all the possible date_times 
            for dt in date_times: # loop over all the possible date_times 
            
                  merged_data = { 'date_time' : [] , 'z_coordinate' : [] , 'observed_variable' : []  }       
                  for k in self.datasets_all:
                        merged_data[k] = []
                        merged_data[k + '_id'] = []
                        merged_data[k + '_lat'] = []
                        merged_data[k + '_lon'] = []
                        
                  print('Analize the date_time number ', str(date_times.index(dt)) , '   ' , dt ,  '   ', now(time.time()) )
                  
                  #if dt == np.datetime64('1979-04-03T13:00:00.000000000'): 
                  #      print('Check date time' , dt )
                                                                                          
                  """ Creating a list of pressure for the available date_time dt and dataset k """   # To Do check if necessary 
                 


                  for k in (self.datasets_all  - dictionary_data[dt].keys() ):
                                    merged_data[k].append(-7777)
                                    merged_data[k+ '_id'].append(-7777)
                                    merged_data[k+ '_lat'].append(-7777)
                                    merged_data[k+ '_lon'].append(-7777)
                                                                  
                              
                  """ Dataset with data i.e. the dataset is a key of  the dictionary_data[dt] and I expect to find data, eventually NaNs or dummy values contained in the original dataset """ 
                  value, Id =  -7777, ''         # dummy values to be replaced with actual one if observations are available 
                  lat , lon = -7777, -7777
                  #for k in list( set(dictionary_data[dt].keys()) ) :
                                    
                  num_records = {} 
                  for k in dictionary_data[dt].keys() :
                                    index, index_up = self.unique_dates[k]['index'][dt] , self.unique_dates[k]['index_up'][dt]  # extracting the exact chunk of the dataframe where the data of this are stored
                                    num_records[k] =  index_up - index
                                
                                     
      
      
                  best_ds, all_ds , best_datasets = 'dummy' , [] , []   
                  most_records = max( [ num_records[v] for v in  num_records.keys() ] )  # maximum numebr of records per date_time           
                  for k, v in num_records.items():                 
                        if v == 0:
                              continue
                        if v == most_records:
                              best_datasets.append(k)                                
                        if v > 0:
                              all_ds.append(k)                               
                              
                  if 'igra2' in best_datasets:
                        best_ds = 'igra2'
                  elif 'ncar' in best_datasets:
                        best_ds = 'ncar'
                  else:
                        best_ds = best_datasets[0]                              
                                                            
                  Merged = self.data[best_ds]['dataframe'] [ self.unique_dates[best_ds]['index'][dt]  :  self.unique_dates[best_ds]['index_up'][dt]  ] # slicing the dataframe                       
                  Merged = Merged.loc[ : , ['date_time' , 'z_coordinate' ,  'observed_variable', best_ds,  best_ds+'_id' , best_ds +  '_lat',  best_ds + '_lon'] ]
                  Merged = Merged.rename(columns={best_ds : "observation_value", best_ds+'_id': "observation_id" ,  best_ds +  '_lat' : 'latitude',  best_ds + '_lon' : 'longitude'} )
                  
                  Merged['source_id'] = best_ds   # adding extra columns i.e. chosen dataset, other dataset with data, number of pressure levels 
                  #Merged['other_dataset'] = all_ds  # TODO dont know where to store this information !!!
                  
                  all_merged_df.append(Merged)
       
                  
                  
            print('*** Concatenating the dataframes  ' , now(time.time()) )      
            Merg = pd.concat (all_merged_df)
            print('*** Finished concatenating the dataframes  ' , now(time.time()) )      
            self.MergedDF = Merg       
            print('Final Merged: ' , Merg )      
            return 0      
      
      
      def AnalizeDecideMergeRecord_noPanda(self, summedRecord = '', dt = '' ):
            """ This is the main function that analize each record (i.e. separate ascent) and decides which one to keep as merged.
                 Args ::
                                 summedRecord         , dataframe including all datasets 
                 Return ::
                                 mergedRecord.index , indices of the record to keep
                                 ds                              , name of the dataset to keep
                                 num_record               , number of records (plevels * variables)
                                 all_ds [string]             , other datasets with available data but not selected 
               
               """
            

            record_dataset_legth ={}     
            
            cleaned = {} 
            for k in self.datasets_all:
                  clean = summedRecord.loc[ (summedRecord[k] != -7777)  &   (summedRecord[k] != -99999.0) & (summedRecord[k] != -999.0) & (summedRecord[k] != np.nan)  ]
                  clean = clean [ clean[k].notnull()   ] 
                  record_dataset_legth[k] = len( clean  )   # total number of observation for the particular dataset 
                  cleaned[k] = clean 
                  
            """ For now, choosing the dataset with more records of all (considering all not NaNs values for all variables), or igra2 data if available and with same number of records """
            
            best_ds, all_ds , best_datasets = 'dummy' , [] , [] # total number of records, name of the chosen dataset , list of other possible dataset with available data 
                     
            most_records = max( [ record_dataset_legth[v] for v in  record_dataset_legth.keys() ] )  # maximum numebr of records per date_time           
            for k, v in record_dataset_legth.items():                 
                  if v == 0:
                        continue
                  if v == most_records:
                        best_datasets.append(k)                                  
                  if v > 0:
                        all_ds.append(k) # all other datasets with smaller number of records than the maximum found 
   
            if len(best_datasets) ==0:
                  return 0,0,0,0 
            
   
            if 'igra2' in best_datasets:
                  best_ds = 'igra2'
            elif 'ncar' in best_datasets:
                  best_ds = 'ncar'
            else:
                  best_ds = best_datasets[0]
                  
            mergedRecord = cleaned[best_ds]                
            
            all_ds = list(np.unique(np.asarray(all_ds)))
            try:
                  all_ds.remove(best_ds)
            except:
                  pass
            
            if len(all_ds)>1:
                  all_ds = ",".join(all_ds)
            elif len(all_ds)==1:
                  all_ds = all_ds[0]
            else:
                  all_ds = np.nan

            #print ('I use ' , best_ds , '   record since it has more entries: ', most_records , ' but other available datasets are : ' , all_ds ) 
            return mergedRecord.index , best_ds , most_records  , all_ds
      
      
      
      
      
      def AnalizeDecideMergeRecord(self, summedRecord = '', dt = '' ):
            """ This is the main function that analize each record (i.e. separate ascent) and decides which one to keep as merged.
                 Args ::
                                 summedRecord         , dataframe including all datasets 
                 Return ::
                                 mergedRecord.index , indices of the record to keep
                                 ds                              , name of the dataset to keep
                                 num_record               , number of records (plevels * variables)
                                 all_ds [string]             , other datasets with available data but not selected 
               
               """
            

            record_dataset_legth ={}     
            
            cleaned = {} 
            for k in self.datasets_all:
                  clean = summedRecord.loc[ (summedRecord[k] != -7777)  &   (summedRecord[k] != -99999.0) & (summedRecord[k] != -999.0) & (summedRecord[k] != np.nan)  ]
                  clean = clean [ clean[k].notnull()   ] 
                  record_dataset_legth[k] = len( clean  )   # total number of observation for the particular dataset 
                  cleaned[k] = clean 
                  
            """ For now, choosing the dataset with more records of all (considering all not NaNs values for all variables), or igra2 data if available and with same number of records """
            
            best_ds, all_ds , best_datasets = 'dummy' , [] , [] # total number of records, name of the chosen dataset , list of other possible dataset with available data 
                     
            most_records = max( [ record_dataset_legth[v] for v in  record_dataset_legth.keys() ] )  # maximum numebr of records per date_time           
            for k, v in record_dataset_legth.items():                 
                  if v == 0:
                        continue
                  if v == most_records:
                        best_datasets.append(k)                                  
                  if v > 0:
                        all_ds.append(k) # all other datasets with smaller number of records than the maximum found 
   
            if len(best_datasets) ==0:
                  return 0,0,0,0 
            
   
            if 'igra2' in best_datasets:
                  best_ds = 'igra2'
            elif 'ncar' in best_datasets:
                  best_ds = 'ncar'
            else:
                  best_ds = best_datasets[0]
                  
            mergedRecord = cleaned[best_ds]                
            
            all_ds = list(np.unique(np.asarray(all_ds)))
            try:
                  all_ds.remove(best_ds)
            except:
                  pass
            
            if len(all_ds)>1:
                  all_ds = ",".join(all_ds)
            elif len(all_ds)==1:
                  all_ds = all_ds[0]
            else:
                  all_ds = np.nan

            #print ('I use ' , best_ds , '   record since it has more entries: ', most_records , ' but other available datasets are : ' , all_ds ) 
            return mergedRecord.index , best_ds , most_records  , all_ds
  
      def WriteMergedFile(self):
            """ Module to write the output file as netCDF """
            
            filled_df = self.MergedDF[ ['date_time' , 'latitude', 'longitude' ,  'observation_value' , 'observed_variable' , 'source_id' , 'observation_id',  'z_coordinate' ]     ]
            xarr = filled_df.to_xarray() 
            out_name = os.getcwd() + '/merged_FASTVERSION_' + [ x for x in self.datasets[ list(self.datasets_keys)[0]].split('/') if '.nc' in x   ] [0] 
            
            xarr.to_netcdf(out_name, format='netCDF4', engine='h5netcdf', mode='w' , group = 'observations_table')  # writing the merged observations_table 
            
           
            for k in self.data.keys():
                  group_name = k + '_station_configuration'
                  sc = self.data[k]['station_configuration'].to_xarray()
                  sc.to_netcdf(out_name, format='netCDF4', engine='h5netcdf', mode='a' , group = group_name )
                  
                  group_name = k + '_source_configuration'
                  sc = self.data[k]['source_configuration'][:1] .to_xarray()
                  sc.to_netcdf(out_name, format='netCDF4', engine='h5netcdf', mode='a' , group = group_name )            
                  
            print('***** Done writing the output netCDF file !')       
            
            
      def Merge_new(self, limit = False , dataframeIsPickled = False):                                           
            a = self.MakeAllDateTime()     # creates a dictionary with the unique observation date_time for each dataset , plus a list with all the dates from any datase
            dictionary_data = self.MakeAllData(pickle = dataframeIsPickled)    
            
            if dataframeIsPickled: 
                  dataframe_data = self.Read_Pickle()                             
            dummy = self.MergeAllData(dictionary_data = dictionary_data )            
            print('Finished merging !!! \n *** NOW: witing the output file' )         
            a = self.WriteMergedFile()
            print('Done writing output !!! ')
            
      def Read_Pickle(self):
            """ Reads the panda dataframe stored in a pickle file (faster in testing) """            
            print(' Loading the pickled dataframes, storing in self.[d]["dataframe"] *** ')
            for d in self.datasets_keys:
                  print(' Loading -- ' + d )
                  self.data[d]['dataframe']= pd.read_pickle(d+'_dic')





""" 
# keys of the station_configuration table
['primary_id', 'primary_id_scheme', 'record_number', 'secondary_id', 'secondary_id_scheme', 'station_name', 'station_abbreviation', 'alternative_name', 'station_crs', 'longitude', 'latitude',
'local_gravity', 'start_date', 'end_date', 'station_type', 'platform_type', 'platform_sub_type', 'operating_institute', 'operating_territory', 'city', 'contact', 'role', 'observing_frequency',
'reporting_time', 'telecommunication_method', 'station_automation', 'measuring_system_model', 'measuring_system_id', 'observed_variables', 'comment', 'optional_data', 'bbox_min_longitude',
'bbox_max_longitude', 'bbox_min_latitude', 'bbox_max_latitude', 'metadata_contact', 'metadata_contact_role']


['primary_id',  'secondary_id', 'station_name', 'alternative_name', 'station_crs', 'longitude', 'latitude',
'start_date', 'end_date',  'city', 
'observed_variables', ]
"""



full_data = { 'ncar'    : 'example_stations/ncar/chuadb_trhc_47646.txt.nc'   ,
               'igra2'   : 'example_stations/igra2/chJAM00047646-data.txt.nc'  ,
               'bufr'     : 'example_stations/bufr/chera5.47646.bfr.nc'  ,
               
               'era5_1' : 'example_stations/era5_1/chera5.conv._47646.nc' , 
               'era5_1759' : 'example_stations/era5_1759/chera5.1759.conv.1:47646.nc' , 
               'era5_1761' : 'example_stations/era5_1761/chera5.1761.conv.1:47646.nc' , 
               'era5_3188' : 'example_stations/era5_3188/chera5.3188.conv.C:5357.nc' , 
               }



small_data = { 'ncar'    : 'example_stations/ncar/chuadb_trhc_47646.txt.nc'       ,
                         'igra2'    : 'example_stations/igra2/chJAM00047646-data.txt.nc'  , }


small_other = {  'ncar'           : 'example_stations/ncar/chuadb_windc_82930.txt.nc'       ,
                           'igra2'          : 'example_stations/igra2/chBRM00082930-data.txt.nc'  ,
                           'era5_1'       :  'example_stations/era5_1/chera5.conv._82930.nc',
                           'era5_1759' : 'example_stations/era5_1759/chera5.1759.conv.1:82930.nc',
                           'bufr'           : 'example_stations/bufr/chera5.82930.bfr.nc',                          
}



if __name__ == '__main__':

      """ Initialize the Merger class """
      Merging = Merger()
      
      fast  = False # se to True if the dataframe for the station have been stored and can be loaded # TODO check, it might not work anymore 
      
      if fast == False:
            print('*** Initialising the data ***' , now(time.time()) )      
            Merging.InitializeData( datasets = small_other ) #  Read each dataset netCDF file, initialize the dataframes, calculated proper date_time arrays 
            save = Merging.Save_DataFrame()
            print('Dataframes have been saved! ', now(time.time())  )
            Merging.Merge_new(limit = '', dataframeIsPickled = False)
           
      elif fast == True:
            Merging.InitializeData( datasets = full_data , fast = True )       
            Merging.Merge_new(limit ='', pickled = True) # Merging procedure 






print('Done ALL ')

