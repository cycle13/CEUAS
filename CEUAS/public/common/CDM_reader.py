""" Module for parsing the CDM data and information

    Author               :: Ambrogi Federico , federico.ambrogi@univie.ac.at
    Original data Source :: https://github.com/glamod/common_data_model/
    
    vars in netCDF files: ['date','time','obstype','codetype','lat','lon','stalt','vertco_type','vertco_reference_1','varno','obsvalue']
"""    

import os,sys
import csv

""" path to the directory where the github repository was cloned 
    path to the csv file containing the information of the observations 
    path to the csv file containing the information of the variables """
cdm_git_root     = 'common_data_model'
observationFile = os.path.join(cdm_git_root, 'table_definitions','observations_table.csv')
variablesFile   = os.path.join(cdm_git_root, 'tables','observed_variable.dat')


def read_observationFile(obsFile= ""):
    """ Return a list of dictionaries for each entry of the observations file obsFile """
    obs=[]
    with open(obsFile) as csvfile:
        reader = csv.DictReader(csvfile, fieldnames = ['element_name','kind','external_table','description'], 
                                         delimiter  = "\t" )
        next(reader)
        next(reader)
        next(reader) # skipping header and first two rows
        
        for l in reader:
            obs.append(l)

    return obs



def read_variableFile(varFile = ""):
    """ Return a list of dictionaries for each entry of the variables file varFile """
    var=[]
    with open(varFile) as csvfile:
        reader = csv.DictReader(csvfile, fieldnames = ['variable','parameter_group','domain','sub_domain','name','units','description'], 
                                         delimiter  = "\t" )
        next(reader) # skipping header

        for l in reader:
            var.append(l)

    return var

    


#print read_observationFile(obs = observationFile)

variables    = read_observationFile(obsFile = observationFile ) 
observations = read_variableFile   (varFile = variablesFile )  
raw_input("continue")




""" Dictionary of variables to be included in the netCDF files
    key   = generic name (appearing e.g. in the readodbstations.py code),
    value = CDM name as found in the the table 
    Note that this MUST be checked and defined by hand """

observation_table = { 'lat'                 : 'latitude'      ,
                      'long'                : 'longitude'     , 
                      'vertco_type'         : 'z_coordinate'  , 
            #'vertco_reference_1'  : 'xx' , 
            #'stalt'               : 'xx' , 
            #'date'                : 'xx' , 
            #'time'                : 'xx' , 
            #'obstype'             : 'xx' , 
            #'codetype'            : 'xx' ,
               }


observed_variable = {'wind'     : 'wind speed', 
                     'pressure' : 'air pressure', 
                     'dewpoint' : 'dew point temperature' , 
                     'humidity' : 'specific humidity', 
                     #'varno'    : 'observed_variable',
                     #'obsvalue' : 'observation_value' }
                     }












odb_vars_numbering = { 'Temperature'            : 2 , 
                       'Wind speed'             : 110,
                       'Wind u-component speed' : -999 , 
                       'Wind v-component speed' : -999 ,
                       'Relative Humidity'      : 29 ,
                       'Dew Point Temp.'        : 59
                      }




'''
top =     [r'\begin{table}[!htbp] ',
           r'\footnotesize',
           r'\begin{center}',
           r'\renewcommand{\arraystretch}{1.3}',
           r'\begin{tabular}{  l p{1.5in} l p{3.0in} } ',
           r'\toprule \toprule', '\n']
 

bottom = [r'\bottomrule \bottomrule',
              r'\end{tabular}',
              r'\end{center}',
              r'\caption{Definition of naming convention, description and units for the variables contained in the netCDF files.}',
              r'\label{CDM}',
              r'\end{table}' ]





def printLatexTab(top = '' , bottom = '' , data = '' , outname = '' ):
    """ prints a latex style table for text editing 
        out is the name of the output tex file
        must be either ObsTab or VarTab, according to the data chosen"""
    out = open('Tex/' + outname + '.tex','w')
 
    for t in top:
        out.write(t + '\n')

    
    tabType = outname.replace('ObsTab','Observation Table').replace('VarTab','Variables Table')    
    
    out.write(r'\multicolumn{4}{c}{ ' + tabType + r' } \toprule \toprule \\' + '\n' )
    out.write(r'\textbf{Variable} & \textbf{CDM Name} & \textbf{Units} & \textbf{Description}  \\ \toprule' + '\n')
    for k in data.keys():
        #print k , D[k]['name'] , D[k]['def'] , D['units'] , '\n'
        n   = data[k]['name'].replace('_','\_')
        d   = data[k]['def'] .replace('_above',' above').replace('_','\_')
        un  = r'$[$' + data[k]['units'] + r'$]$'


        print(k , n , d, un )
        line = k.replace('_','\_') + ' & ' + n + ' & ' + un + ' & ' + d + r'\\ ' + '\n'
        out.write(line)
   
    for b in bottom:
        out.write(b + '\n')

    out.close()


obs = Data['observation_table']
var = Data['observed_variable']

a = printLatexTab(top = top, bottom = bottom , data = obs , outname = 'ObsTab')
b = printLatexTab(top = top, bottom = bottom , data = var , outname = 'VarTab')


'''







