
#############################################################
# pippi: parse it, plot it
# ------------------------
# Post-processing module for pippi.
#
# Author: Pat Scott (patscott@physics.mcgill.ca)
# Originally developed: March 2012
#############################################################

from pippi_utils import *
from importlib import import_module

def pare(argstring):

  # Make sure all the goods are present
  if (len(argstring) != 3):
    usage()
    return

  # Strip trailing .py (if any) on module name
  argstring[1] = re.sub(r'\.py$', '', argstring[1])
  
  try:
    # Hit up the external module
    pareMod = import_module(argstring[1])
  except ImportError:
    # or not
    sys.exit('Error: cannot import module '+argstring[1]+'; it doesn\'t seem to exist.\nQuitting...\n')

  try:
    # Check that the function is actually good to go
    pareFunc = getattr(pareMod, argstring[2])
  except:
    sys.exit('Error: module '+argstring[1]+' looks OK, but failed to load function '+argstring[2]+'.\nQuitting...\n')

  # Open chain for paring
  chainArray = getChainData(argstring[0],silent=True)

  # Pump it through the user-supplied function, printing each new point to stdout
  for i in range(chainArray.shape[0]): 
    print '\t'.join([str(x) for x in pareFunc(chainArray[i,:])])


