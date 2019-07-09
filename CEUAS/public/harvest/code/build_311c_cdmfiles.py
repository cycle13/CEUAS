#!/usr/bin/env python
import sys
import os.path
import glob

import subprocess
import urllib.request
import xarray as xr
import numpy
#import h5pickle as h5py
import h5py
from datetime import date, datetime
import time
from multiprocessing import Pool
from netCDF4 import Dataset
import gzip
import pandas as pd
from functools import partial
#from rasotools.utils import *
#from eccodes import *
from numba import *
import matplotlib.pylab as plt
import cartopy.crs as ccrs
import argparse
import copy
from io import StringIO
import h5netcdf

"""  using fixed lenght strings (80 chars) 
Compression does not work well with normal strings 

"""
okinds={'varchar (pk)':numpy.dtype('|S80'),'varchar':numpy.dtype('|S80'),'numeric':numpy.float32,'int':numpy.int32,
       'timestamp with timezone':numpy.datetime64,
       'int[]*':list,'int[]':list,'varchar[]*':list,'varchar[]':list}


kinds={'varchar (pk)':str,'varchar':str,'numeric':numpy.float32,'int':numpy.int32,
       'timestamp with timezone':numpy.datetime64,
       'int[]*':list,'int[]':list,'varchar[]*':list,'varchar[]':list}



def make_datetime(dvar,tvar):
    """ Converts into dat-time """
    dvari=dvar.values.astype(numpy.int)
    tvari=tvar.values.astype(numpy.int)
    df=pd.DataFrame({'year':dvar//10000,'month':(dvar%10000)//100,'day':dvar%100,
                        'hour':tvar//10000,'minute':(tvar%10000)//100,'second':tvar%100})
    dt=pd.to_datetime(df).values
    return dt


""" Translates the odb variables name  into cdm var """
cdmfb={'observation_value':'obsvalue@body',
       'observed_variable':'varno@body',
       'z_coordinate_type':'vertco_type@body',
       'z_coordinate':'vertco_reference_1@body',
       'date_time':[make_datetime,'date@hdr','time@hdr'],
       'longitude':'lon@hdr',
       'latitude':'lat@hdr'}
    
def read_all_odbsql_stn_withfeedback(odbfile):

    #countlist=glob.glob(opath+'/*.count')
    alldata=''

    alldict=xr.Dataset()
    t=time.time()
    sonde_type=True
    obstype=True
    if os.path.getsize(odbfile)>0:
        """ Read first the odbb header to extract the column names and type """
        try:
            rdata=subprocess.check_output(["odb","header",odbfile])
            rdata=rdata.decode('latin-1').split('\n')
            columns=[]
            kinds=[]
            tdict={}
            for r in rdata[2:-2]:
                try:
                    print(r[:6])
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
                            tdict[columns[-1]]=numpy.dtype('S8') # dict containng column name and type
                                     
                            
                except IndexError:
                    pass
        except:
            print('could not read odbfile '+odbfile)
            return alldict
        try:
            rdata=subprocess.check_output(["odb","sql","-q","select *","-i",odbfile,'--no_alignment']) # after reading th eheader it does the query
            # returns a byte string
            print('after odb:',time.time()-t)
            rdata=''.join(rdata.decode('latin-1').split("'")) # decoding the stirng into a unicode
            f=StringIO(rdata) # access the string like a file, return a file pointer to read the string with pandas
            # nb  if you have null values, reading of integer fails and are read as floats
            # to improve, you can convert the columns with nabs in the alldicts (pandas data frame) into int(np.nans)
            # date values are large so float 32 precision is not sufficient 
            alldict=pd.read_csv(f,delimiter='\t',quoting=3,comment='#',dtype=tdict)
            del f,rdata

 
            """ alternative method to read the odb           
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
       
        except subprocess.CalledProcessError as e:
            print('odb failed!:'+' '+odbfile)
            return alldict

    print(odbfile,time.time()-t)
    #idy=numpy.lexsort((alldict['varno@body'],
                       #-alldict['vertco_reference_1@body'],
                       #alldict['time@hdr'],
                       #alldict['date@hdr']))
    #for k in alldict.columns:
        #alldict[k]=alldict[k][idy]

    print(odbfile,time.time()-t)

    """ may not be necessary to convert into x_array sicne you can write a pandas df into an HDF file """
    return alldict.to_xarray()

def fromfb(fbv,cdmfb,cdmkind):
    """ input: 
               fbv    : feedback variable (cdm compliant)
               cdmfb  :  
               cdmkind: data type of the cdmfb
    """
    x=0
    # checks if the type of the variable is a list, so that it uses the function to extract the date time 
    if type(cdmfb) is list:
        x=cdmfb[0](fbv[cdmfb[1]],fbv[cdmfb[2]])
    else:
        if cdmfb=='varno@body':
            tr=numpy.zeros(113,dtype=int) 
            """ translates odb variables number to Lot3 numbering convention """
            tr[1]=117  # should change
            tr[2]=85
            tr[3]=104
            tr[4]=105
            tr[7]=39 #spec hum
            tr[29]=38 #relative hum
            tr[59]=36 # dew point
            tr[111]=106 #dd
            tr[112]=107  #ff
            #
            tr[39]= 85 # 2m T
            tr[40]= 36 # 2m Td
            tr[41]= 104 #10m U
            tr[42]= 105  #10m V
            tr[58]=38 # 2m rel hum
            
            x=tr[fbv[cdmfb].values.astype(int)] # reads the varno from the odb feedback and writes it into the variable id of the cdm 
        else:    
            x=fbv[cdmfb].values
        
    return x

def ttrans(cdmtype,kinds=kinds):
    """ convert the cdm types to numpy types """    
    nptype=numpy.float32
    try:
        nptype=kinds[cdmtype.strip()]
    except:
        print(cdmtype,'not found, using numpy.float32')
        
    
    return nptype

@njit
def find_dateindex(y):
    """ creates the indices list from the dates, for quick access 
        nb the benchmark script will not work with these files since the definition of the array size is swapped i.e. (x.shape[0], 3)"""        


    x=numpy.unique(y)
    z=numpy.zeros((3,x.shape[0]),dtype=numpy.int32)
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
                print('Error')
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
                print('Error')
    z[0,:]=x
    return z

def odb_to_cdm(cdm,cdmd,fn):
    """ input:
              fn: odb file name (e.g. era5.conv._10393)
              cdm: cdm tables (read with pandas)
              cdmd: cdm tables definitions ("") """


    recl=0
    
    t=time.time()
    #f=gzip.open(fn)
    #fn=fn[:-3]
    fnl=fn.split('/')
    fnl[-1]='ch'+fnl[-1]
    fno=output_dir + '/' + fnl[-1] + '.nc' # creating an output file name e.g. chera5.conv._10393.nc  , try 01009 faster
    if not False:
        
        # era5 analysis feedback is read from compressed netcdf files era5.conv._?????.nc.gz in $RSCRATCH/era5/odbs/1
        fbds=read_all_odbsql_stn_withfeedback(fn) # i.e. the xarray 
        #fbds=xr.open_dataset(f)
        print(time.time()-t) # to check the reading of the odb
        # the fbencodings dictionary specifies how fbds will be written to disk in the CDM compliant netCDF file.
        # float64 is often not necessary. Also int64 is often not necessary. 
        fbencodings={}
        for d in fbds._variables.keys():
            if fbds.variables[d].dtype==numpy.dtype('float64'):
                if d!='date@hdr':             
                    fbencodings[d]={'dtype':numpy.dtype('float32'),'compression': 'gzip'} # probably dtype not neccessary, but compression must be there
                else:
                    fbencodings[d]={'dtype':numpy.dtype('int32'),'compression': 'gzip'}               
            else:
                fbencodings[d]={'compression': 'gzip'}
                
        y=fbds['date@hdr'].values
        z=find_dateindex(y)
        di=xr.Dataset() 
        di['dateindex']=({'days':z.shape[1],'drange':z.shape[0]},z) # date, index of the first occurrance, index of the last 
    

        # odb is read into xarray. now we must encode the cdm into several xarray datasets
        # each cdm table is written into an hdf group, groups is the dict of all the groups
        # to write the group to the disk, you need the group encoding dict
        groups={}
        groupencodings={}
        for k in cdmd.keys(): # loop over all the table definitions 
            groups[k]=xr.Dataset() # create an  xarray
            groupencodings[k]={} # create a dict of group econding

            for i in range(len(cdmd[k])): # in the cdm table definitions you always have the element(column) name, the type, the external table and the description 
                d=cdmd[k].iloc[i] # so here loop over all the rows of the table definition . iloc is just the index of the element
                # two possibilities: 1. the corresponding  table already exists in the cdm (case in the final else)
                #                    2. the corr table needs to be created from the local data sources (e.g. the feedback or IGRA or smt else). 
                # These are the observation_tables, the header_tables and the station_configuration.
                # These tables are contained in the CEUAS GitHub but not in the cdm GitHub
                if k in ('observations_table'):
                    try:
                        # fbds is an xarray dataset , fbds._variables is a dict of the variables 
                        groups[k][d.element_name]=({'hdrlen':fbds.variables['date@hdr'].shape[0]},
                                    fromfb(fbds._variables,cdmfb[d.element_name],ttrans(d.kind,kinds=okinds)))
                    except KeyError:
                        x=numpy.zeros(fbds.variables['date@hdr'].values.shape[0],dtype=numpy.dtype(ttrans(d.kind,kinds=okinds)))
                        x.fill(numpy.nan)
                        groups[k][d.element_name]=({'hdrlen':fbds.variables['date@hdr'].shape[0]},x)
                        
                elif k in ('header_table'):
                    # if the element_name is found in the cdmfb dict, then it copies the data from the odb into the header_table
                    try:
                        groups[k][d.element_name]=({'hdrlen':fbds.variables['date@hdr'].shape[0]},
                                    fromfb(fbds._variables,cdmfb[d.element_name],ttrans(d.kind,kinds=okinds)))
                    except KeyError:
                        # if not found, it fills the columns with nans of the specified kind. Same for the observation_tables 
                        x=numpy.zeros(fbds.variables['date@hdr'].values.shape[0],dtype=numpy.dtype(ttrans(d.kind,kinds=okinds)))
                        x.fill(numpy.nan)
                        groups[k][d.element_name]=({'hdrlen':fbds.variables['date@hdr'].shape[0]},x)
                        
                elif k in ('station_configuration'): # station_configurationt contains info of all the stations, so this extracts only the one line for the wanted station with the numpy.where
                    try:   
                        if 'sci' not in locals(): 
                            sci=numpy.where(cdm[k]['primary_id']=='0-20000-0-'+fbds['statid@hdr'].values[0].decode('latin1'))[0]
                        if len(sci)>0:
                            groups[k][d.element_name]=({k+'_len':1},
                                    cdm[k][d.element_name].values[sci])
                    except KeyError:
                        pass
                        
                else : # this is the case where the cdm tables DO exist
                    try:   
                        groups[k][d.element_name]=({k+'_len':len(cdm[k])},
                                    cdm[k][d.element_name].values) # element_name is the netcdf variable name, which is the column name of the cdm table k 
                    except KeyError:
                        pass
                try:
                    groups[k][d.element_name].attrs['external_table']=d.external_table # defining variable attributes that point to other tables (3rd and 4th columns)
                    groups[k][d.element_name].attrs['description']=d.description
                    print('good:',k,d.element_name)
                    groupencodings[k][d.element_name]={'compression': 'gzip'}
                except KeyError:
                    print('bad:',k,d.element_name)
                    pass

        #this writes the dateindex to the netcdf file. For faster access it is written into the root group
        di.to_netcdf(fno,format='netCDF4',engine='h5netcdf',mode='w')
        # add era5 feedback to the netcdf file. 
        # fbds is the 60 col. xarray
        fbds.to_netcdf(fno,format='netCDF4',engine='h5netcdf',encoding=fbencodings,group='era5fb',mode='a')
        
        for k in groups.keys():
            #this code deletes some variables to check how well they are compressed. Variable strings are badly compressed
            #gk=list(groups[k].keys())
            #for l in gk:
                #if groups[k][l].dtype==numpy.dtype('<U1'):
                    #del groups[k][l]
                    #del groupencodings[k][l]
            
            #this appends group by group to the netcdf file
            groups[k].to_netcdf(fno,format='netCDF4',engine='h5netcdf',encoding=groupencodings[k],group=k,mode='a') #
        print('sizes: in: {:6.2f} out: {:6.2f}'.format(os.path.getsize(fn)/1024/1024,
                                              os.path.getsize(fno)/1024/1024))
        del fbds
    

    # speed test for accessing dateindex
    #for k in range(10):
        
        #t=time.time()
        #with h5py.File(fno,'r') as f:
            #di=f['dateindex'][:]
            #idx=numpy.where(di[0,:]==19950101)[0]
            #print(numpy.nanmean(f['observations_table']['observation_value'][di[1,idx[0]]:di[2,idx[0]]+1]))
        #print('ch',time.time()-t)
        #fng='cgera5'.join(fno.split('chera5'))
        #t=time.time()
        #with h5py.File(fng,'r') as g:
            #do=g['dateindex'][:]
            #idx=numpy.where(do[:,2]==19950101)[0]
            #print(numpy.nanmean(g['obsvalue@body'][do[idx[0],0]:do[idx[0],1]+1]))
        #print('cg',time.time()-t)
        
        
    # first implementation of inner join  - resolving numeric variable code 
    #with h5py.File(fno,'r') as f:
        #ext=f['observations_table']['observed_variable'].attrs['external_table']
        #lext=ext.split(':')
        
        #l=[]
        #lidx=[]
        #llen=len(f['observations_table']['observed_variable'][:])
        #for i in range(llen):
            #obv=f['observations_table']['observed_variable'][i]
            #if obv not in l:
                #idx=numpy.where(f[lext[0]][lext[1]][:]==obv)[0][0]
                #l.append(obv)
                #lidx.append(idx)
            #else:
                #idx=lidx[l.index(obv)]
            #for k in f[lext[0]].keys():
                #print(k,':',f[lext[0]][k][idx],)
            #print('value:',f['observations_table']['observation_value'][i])
        #print(f)

    
    print(fno,time.time()-t)

    return recl

if __name__ == '__main__':


    parser = argparse.ArgumentParser(description="Make CDM compliant netCDFs")
    parser.add_argument('--database_dir' , '-d', 
                    help="Optional: path to the database directory. If not given, will use the files in the data directory" ,
                    default = '../../../cdm/data/',
                    type = str)
    parser.add_argument('--auxtables_dir' , '-a', 
                    help="Optional: path to the auxiliary tables directory. If not given, will use the files in the data/tables directory" ,
                    default = '../../../cdm/data/tables/',
                    type = str)
    parser.add_argument('--odbtables_dir' , '-odb', 
                    help="Optional: path to the odb tables directory. If not given, will use the files in the data/tables directory" ,
                    default = '../data/tables/',
                    type = str)

    parser.add_argument('--output_dir' , '-out',
                    help="Optional: path to the netcdf output directory" ,
                    default = '../data/tables',
                    type = str)


    args = parser.parse_args()
    dpath = args.database_dir
    tpath = args.auxtables_dir
    output_dir = args.output_dir
    odbpath = args.odbtables_dir

    print ('THE DPATH IS', dpath)
    if not dpath:
        dpath = '../../cdm/code/data/'
   
    if not tpath:
        tpath = dpath+'/tables/'
   
    print ('Analysing the databases stored in ', dpath)
    cdmpath='https://raw.githubusercontent.com/glamod/common_data_model/master/tables/'                                                                                                                                                                                               


    # TODO: get the list of files in the tables directory of the cdm 
    cdmtablelist=['id_scheme','crs','station_type','observed_variable','station_configuration_codes']        
    cdm=dict()
    for key in cdmtablelist:
        f=urllib.request.urlopen(cdmpath+key+'.dat')
        col_names=pd.read_csv(f,delimiter='\t',quoting=3,nrows=0)
        f=urllib.request.urlopen(cdmpath+key+'.dat')
        tdict={col: str for col in col_names}
        cdm[key]=pd.read_csv(f,delimiter='\t',quoting=3,dtype=tdict,na_filter=False)

    cdmd=dict()

    # TODO: get the list of files in the tables_definition directory
    # you need the list of file in the directory, there must be some urllib function for that
    # see that there are more entries than in the rpevious list, since e.g. station_configuration does not exist int he cdm GitHub but was created in the CEUAS GitHub 
    cdmtabledeflist=['id_scheme','crs','station_type','observed_variable','station_configuration','station_configuration_codes','observations_table','header_table']        
    for key in cdmtabledeflist:
        url='table_definitions'.join(cdmpath.split('tables'))+key+'.csv'
        f=urllib.request.urlopen(url)
        col_names=pd.read_csv(f,delimiter='\t',quoting=3,nrows=0,comment='#')
        f=urllib.request.urlopen(url)
        tdict={col: str for col in col_names}
        cdmd[key]=pd.read_csv(f,delimiter='\t',quoting=3,dtype=tdict,na_filter=False,comment='#')

    # up to here: only information read from the public cdm github
 

    # header table is instead read from CEUAS github, cdm directory 
    cdmd['header_table']=pd.read_csv(tpath+'../table_definitions/header_table.csv',delimiter='\t',quoting=3,comment='#')
    cdmd['observations_table']=pd.read_csv(tpath+'../table_definitions/observations_table.csv',delimiter='\t',quoting=3,comment='#')
    id_scheme={cdmd['id_scheme'].element_name.values[0]:[0,1,2,3,4,5,6],
               cdmd['id_scheme'].element_name.values[1]:['WMO Identifier','Volunteer Observing Ships network code',
                                                             'WBAN Identifier','ICAO call sign','CHUAN Identifier',
                                                             'WIGOS Identifier','Specially constructed Identifier']}

    cdm['id_scheme']=pd.DataFrame(id_scheme)
    #cdm['id_scheme'].to_csv(tpath+'/id_scheme_ua.dat')
    cdm['crs']=pd.DataFrame({'crs':[0],'description':['wgs84']})
    #cdm['crs'].to_csv(tpath+'/crs_ua.dat')
    cdm['station_type']=pd.DataFrame({'type':[0,1],'description':['Radiosonde','Pilot']})
    #cdm['station_type'].to_csv(tpath+'/station_type_ua.dat')
    #cdm['observed_variable']=pd.read_csv(tpath+'/observed_variable.dat',delimiter='\t',quoting=3,dtype=tdict,na_filter=False,comment='#')


    func=partial(odb_to_cdm,cdm,cdmd)
    #bfunc=partial(read_bufr_stn_meta,2)
    #rfunc=partial(read_rda_meta) 
    tu=dict()
    p=Pool(25)
    dbs=['1'] #,'igra2','ai_bfr','rda','3188','1759','1761']
    for odir in dbs: 
        cdm['station_configuration']=pd.read_csv(odbpath+'/'+odir+'/station_configuration.dat',delimiter='\t',quoting=3,dtype=tdict,na_filter=False,comment='#')
        if 'ai' in odir:
            pass
        elif 'rda' in odir:
            pass
        elif 'igra2' in odir:
            pass

        else:
            #flist=glob.glob(odbpath+odir+'/'+'era5.conv.*01009.nc.gz')
            flist=glob.glob(odbpath+odir+'/'+'era5.conv._01009')
            transunified=list(map(func,flist))
