""" Analyse and plot the u,v wind components time series from netCDF files.

author: Ambrogi Federico

This files gives retrives basic information and creates the plots
for the u,v wind compontents from the nectCDF files.

The netCDF files were converted from the odb format to net CDF using the 
version of script 'readodbstationfiles.py'.
Databases included: ['1', 3188','1759','1761'] in the root dir '/raid60/scratch/leo/scratch/era5/odbs/'

netCDF file root directory:  '/raid8/srvx1/federico/odb_netCDF/$FSCRATCH/ei6'

"""
import netCDF4
import matplotlib.pylab as plt
import os,sys
import os.path
import matplotlib.gridspec as gridspec

class netCDF:
     """" Class containing the main properties and functionalities to handle netCDF files
          Args:
               res_dir : root directory containing the results 
               file_name : base name
               var : variable type. i.e. 'temp','uwind','vwind'           
     """
     #global database_dir 
     def __init__(self, database_dir, res, file_name):
          """ Information identifying the file 
              Args:
                   database_dir: root directory where the results for each dataset are stored e.g /raid8/srvx1/federico/odb_netCDF/$New_Results
                   res: specific datased considered e.g. 1759 
                   file_name: base file name stripped from extension and specific variable e.g. ERA5_1_16087_          
          """
          self.database = database_dir
          self.res = res
          self.file_name  = file_name
          self.uwind = ''
          self.vwind = ''
          self.temp = ''
          
          self.datum_uwind = ''
          self.datum_vwind = ''
          self.datum_temp = ''
          
          self.variables = ''
          
     def load(self,var):
          """ Loading the u,v wind comp. files.
              The 'datum' and 'variables' should be identical """
          #print ('DATABASE is', self.database)
          file_dir = self.database + '/' + self.res + '/' + self.file_name
          print ('base dir:' , file_dir )
          print ('res dir:'  , self.res )
          print ('file name:', self.file_name )
          
          # example: /raid8/srvx1/federico/odb_netCDF/$New_Results/1759/1:87418
          # 
          uwind_path = file_dir + 'u.nc'
          vwind_path = file_dir + 'v.nc'
          temp_path  = file_dir + 't.nc'
          
          if var == 'uwind':           
               if os.path.isfile(uwind_path):
                    f_u = netCDF4.Dataset(uwind_path) 
                    self.variables = f_u.variables.keys()
                    self.datum_uwind = [ 1900 + d for d in f_u.variables['datum'][0,:]/365.25 ] # converting the datum in years   
                    self.uwind = f_u.variables['uwind'][0,12,:]
               else: raise ValueError('netCDF files:', uwind_path, ' not found!!!')
               
          elif var == 'vwind':           
               if os.path.isfile(vwind_path):
                    f_v = netCDF4.Dataset(vwind_path) 
                    self.datum_vwind = [ 1900 + d for d in f_v.variables['datum'][0,:]/365.25 ]    
                    self.vwind = f_v.variables['vwind'][0,12,:]  
               else: raise ValueError('netCDF files:', vwind_path, ' not found!!!')
            
          elif var == 'temp':           
               if os.path.isfile(temp_path):
                    f_t = netCDF4.Dataset(temp_path) 
                    self.datum_temp = [ 1900 + d for d in f_t.variables['datum'][0,:]/365.25 ]
                    print(f_t.variables.keys())
                    self.temp = f_t.variables['temperatures'][0,12,:]
               else: raise ValueError('netCDF files:', temp_path, ' not found!!!')

     def printInfo(self):
          print('Basic info for *** ', self.file_name, '\n')
          print('The available variables are: ')
          for v in self.variables:
               print(v)

     def analyser(self):
          """Module that analyses the netCDF file"""
          print('Will do something')
          
          

class Plotter():
     """ Class containing the basic functionalities 
     for plotting the u,v wind components """
     def __init__(self, netCDF, var=''):
          self.file  = netCDF
          self.name = netCDF.file_name
          self.var     = var

          self.x_data = ''
          self.y_data = ''
          
          '''
          """ wind components """          
          self.datum_u = netCDF.datum_u
          self.datum_v = netCDF.datum_u
          self.uwind = netCDF.uwind
          self.vwind = netCDF.vwind
          """ temperature  """          
          self.datum_temp = netCDF.datum_u
          self.temp       = netCDF.uwind
          '''
          
     
     def load_xy(self):
          ''' Loading the x and y data to plot and analyze, accoridng the chosen variable'''
          var = self.var
          print('The var is: ', var )
          if var == 'temp':
               self.x_data = self.file.datum_temp
               self.y_data = self.file.temp
          elif var == 'uwind':
               self.x_data = self.file.datum_uwind
               self.y_data = self.file.uwind
          elif var == 'vwind':
               self.x_data = self.file.datum_vwind
               self.y_data = self.file.vwind          
          else:
               raise ValueError('Unknown variable:', var, ' !!!')
               
               
     def create_outDir(self,out_path):
          if not os.path.isdir(out_path):
               print('Creating the PLOT output directory: ', out_path)
               os.mkdir(out_path)
               
     
     def style_dic(self):          
          dic_prop = { 'uwind':{'xlab':'Year', 'ylab':'Speed [m/s]'    ,'leg':'uwind'      , 'ax':[1920,2019,-50,50]  ,'c':'blue'  } ,
                       'vwind':{'xlab':'Year', 'ylab':'Speed [m/s]'    ,'leg':'vwind'      , 'ax':[1920,2019,-50,50]  ,'c':'cyan'  } ,
                       'temp' :{'xlab':'Year', 'ylab':'Temperature [K]','leg':'Temperature', 'ax':[1920,2019,200 ,300],'c':'orange'} ,
                       'hum'  :{'xlab':'Year', 'ylab':'Humidity [???]' ,'leg':'Humidity'   , 'ax':[1920,2019,0   ,300],'c':'cyan'  } ,
                           }
          return dic_prop
               
     def plotter_prop(self, xlabel = True):
          var = self.var
          dic_prop = self.style_dic()
          fnt_size = 13
          plt.axis(dic_prop[var]['ax'])
          if xlabel: plt.xlabel(dic_prop[var]['xlab'], fontsize = fnt_size)
          plt.ylabel(dic_prop[var]['ylab'], fontsize = fnt_size)
          plt.legend(loc = 'lower left', fontsize = 12)
          
     def plotter(self, out_dir='', save = True, xlabel = True):
          self.load_xy()                     
          x = self.x_data 
          y = self.y_data
          
          print('x: ', x , 'y: ', y)
          dic_prop = self.style_dic()
          plt.plot( x , y , label = dic_prop[self.var]['leg'], linestyle = '-', color = dic_prop[self.var]['c'] )
          self.plotter_prop(xlabel = xlabel)
          plt.grid(linestyle = ':')                    
          if save: 
               save_path = out_dir + '/' + self.name + '_' + self.var +'.pdf'
               self.create_outDir(out_path=out_dir)
               plt.savefig(save_path,  bbox_inches='tight')
               plt.close()
 
 
                     
#netCDF_file = netCDF(test)     
#netCDF_file.load()
#print ('the file is', netCDF_file.path , netCDF_file.variables)


''' Reading the list of dataset contained in the database directory,
storing the absolute path '''


database_dir = '/raid8/srvx1/federico/odb_netCDF/$New_Results/1759'
dataset = [ res for res in os.listdir(database_dir)][:10]

print ('The results dataset is: ', dataset)
vars = ['uwind', 'vwind' ,'temp']

out_dir = os.getcwd() + '/ciao/' 

""" Producing single plots for each variable """
'''
for d in dataset:
     res_dir = database_dir+'/'+d # e.g. /raid8/srvx1/federico/odb_netCDF/$New_Results/1759/
     res_name = os.listdir(res_dir)[0].replace('u.nc','').replace('v.nc','').replace('t.nc','')

     for v in vars:
          print('processing: ', res_name) # e.g. ERA5_1759_2:11903_
          netCDF_file = netCDF(database_dir,d,res_name) 
          
          
          netCDF_file.load(v)     
          netCDF_file.printInfo()
      
          Plot = Plotter(netCDF_file, var=v )
          Plot.plotter(out_dir= out_dir)
'''  

from pylab import rcParams
rcParams['figure.figsize']= 10, 10# first is the height, second is the width


database_dir = '/raid8/srvx1/federico/odb_netCDF/netCDF_1_1759_1761/1'


dataset = [ res for res in os.listdir(database_dir)]
out_dir = os.getcwd() + '/CIAO/' 


for d in dataset:
     
     gs = gridspec.GridSpec(3,1)
     
     res_dir = database_dir+'/'+d # e.g. /raid8/srvx1/federico/odb_netCDF/$New_Results/1759/
     res_name = os.listdir(res_dir)[0].replace('u.nc','').replace('v.nc','').replace('t.nc','')     
  
     ax0 = plt.subplot(gs[0])
  
     netCDF_file = netCDF(database_dir,d,res_name)
     netCDF_file.load('temp')     
     Plot = Plotter(netCDF_file, var='temp' )
     Plot.plotter(out_dir= out_dir, save = False , xlabel = False)
     plt.tight_layout()
     plt.text(1925, 290, 'Dataset: ' + res_dir, fontsize = 12 , color = 'red')
     plt.text(1925, 280, 'Station: ' + res_name.split("_")[2] , fontsize = 12 , color = 'red')    
     
     ax0.xaxis.set_major_formatter(plt.NullFormatter())
  
     ax1 = plt.subplot(gs[1])
     netCDF_file = netCDF(database_dir,d,res_name) 
     netCDF_file.load('uwind')     
     Plot = Plotter(netCDF_file, var='uwind' )
     Plot.plotter(out_dir= out_dir, save = False , xlabel = False)  
     plt.tight_layout()
     ax1.xaxis.set_major_formatter(plt.NullFormatter())
     
     ax2 = plt.subplot(gs[2])
     netCDF_file = netCDF(database_dir,d,res_name) 
     netCDF_file.load('vwind')     
     Plot = Plotter(netCDF_file, var='vwind' )
     Plot.plotter(out_dir= out_dir, save = False , xlabel = True) 
     plt.tight_layout()
  
     plt.savefig('CIAO/' + netCDF_file.file_name + '_all.pdf' , bbox_inches='tight' )    
      

print('done')


'''
test = database_dir +'/16087/ERA5_1_16087_u.nc'
test_false = 'dsgh'

test_netcdf(file=test, print_info=True)

for var,val in vars.items():

    with netCDF4.Dataset( sample1 + var + '.nc') as f:
        plt.plot(f.variables['datum'][:]/365.25,f.variables[val][0,12,:] , 
                 label='ERA_1', color = 'blue')
    
    with netCDF4.Dataset(sample2 + var +  '.nc') as f:
        plt.plot(f.variables['datum'][0,:]/365.25,f.variables[val][0,12,:],
                label ='ERA5_erapresat', color = 'green')
    
    with netCDF4.Dataset(sample3 + var + '.nc') as f:
        plt.plot(f.variables['datum'][0,:]/365.25,f.variables[val][0,12,:],
                 label = 'feedbackmerged' , color = 'orange' )

    print(f.variables.keys())
    plt.ylabel(var)
    plt.xlim(20,120)
    plt.xlabel('Year')
    plt.legend(loc = 'lower left')
    plt.savefig(var + '.png',  bbox_inches='tight')
    plt.close()


print('*** Finished')
'''
