import os,sys
import argparse
from harvest_convert_to_netCDF import db

import numpy as np
import subprocess

#from check_correct import *


""" Select the databases, split the files into the number of wanted processes and run in parallel """
def filelist_cleaner(lista, d=''):
       """ Removes unwanted files that might be present in the database directories """
       print('Cleaning the list of files to be converted')
       if d == 'ncar':
              cleaned = [ l for l in lista if '.nc' not in l ]
       if d == 'bufr':
              cleaned = [ l for l in lista if '.bfr' in l and 'era5.' in l and '+100-' not in l and 'undef' not in l]
       if d in ['era5_1759', 'era5_1761']:
              cleaned = [ l for l in lista if '.nc' not in l and '.conv.' in l ]
       if d =='igra2':
              cleaned = [ l for l in lista if '-data' in l ]
       if d == 'era5_3188':
              cleaned = [ l for l in lista if '.conv.C' in l and '.nc' not in l ]
       if d == 'era5_1':
              cleaned = [ f for f in lista if '.conv._' in f and '.nc' not in f and '.gz' not in f ]
       if d == 'era5_1761':
              cleaned = [ l for l in lista if '.conv.' in l and '.nc' not in l ]
       cleaned = [c for c in cleaned if '.py' not in c and '.nc' not in c and '.gz' not in c ]
       return cleaned


def chunk_it(seq, num):
       """ Creates sub sets of the input file list """
       avg = len(seq) / float(num)
       out = []
       last = 0.0
   
       while last < len(seq):
           out.append(seq[int(last):int(last + avg)])
           last += avg
   
       return out


out_dir = '/raid60/scratch/federico/12MARCH2020_harvested'

processes = 5 # number of process PER DATASET 

""" Select the dataset to be processed """ 
#datasets = ['era5_1', 'era5_3188', 'era5_1759', 'era5_1761', 'ncar', 'igra2', 'bufr' ]
datasets = ['ncar']

""" Check processed files """
check_missing = False
processed_dir = '/raid60/scratch/federico/READY_06MARCH2020/bufr'


def rerun_list(f_list, processed_dir = '', split = '' , input_dir = ''):
       
       processed = [ f.split('harvested_')[1].replace('.nc','') for f in os.listdir(processed_dir)  ]
       f_list          = [ f.split(input_dir)[1] for f in f_list ]


       to_be_processed = []
       for file in f_list:
              file = file.replace('/','')
              if file in processed:
                     continue
              else:
                     to_be_processed.append(input_dir + '/' + file )
       print('total to be processed: ', len(to_be_processed) )
       return to_be_processed



for d in datasets:
       print ('DATASET IS', d )
       files_list = [ db[d]['dbpath'] + '/' + f for f in os.listdir(db[d]['dbpath']) if os.path.isfile( db[d]['dbpath']+'/'+f ) ] # extracting the files list stores in the database path                   
       f_list = [ f for f in files_list if os.path.getsize(f) > 1 ] # cleaning the list of files in the original database directories                                                               
       #files_list = open('/raid60/scratch/federico/ncar_MISS.txt', 'r').readlines()
       f_list = filelist_cleaner(f_list, d = d)
       f_list = [ f.replace('\n','')  for f in f_list ]
       if check_missing == True:
              f_list = rerun_list(f_list, processed_dir = processed_dir , split = 'ai_bfr' , input_dir =  db[d]['dbpath']  )
   
       chunks = chunk_it(f_list, processes)
       print('+++++++++ TOTAL NUMBER OF FILES: ', len(f_list) )
       for c in chunks:
              print ('*** I am running CHUNK: ', chunks.index(c) , ' *** with: ' ,  len(c), ' files \n'  )
              c = str(','.join(c)).replace('#','')
                   
              os.system('/opt/anaconda3/bin/python3  harvest_convert_to_netCDF_newfixes.py  -d ' + d + ' -o ' + out_dir + ' -f ' + c + ' & ')                                                                                                                                 

print('\n\n\n *** Finished with the parallel running ***')
