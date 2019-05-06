""" Module for cloning the CDM GitHUb repository

    Author      :: Ambrogi Federico , federico.ambrogi@univie.ac.at

"""

import os,sys
import git
destination = "CDM"
os.mkdir("CDM")
print("Cloning the CDM GitHub repository in %s" %destination)
git.Git("").clone("https://github.com/glamod/common_data_model.git")
