
#############################################################
# pippi: parse it, plot it
# ------------------------
# Parsing program for pippi.
#
# Author: Pat Scott (patscott@physics.mcgill.ca)
# Originally developed: March 2012
#############################################################

from pippi_utils import *
from scipy.special import gammaincinv as deltaLnLike
from scipy.interpolate import InterpolatedUnivariateSpline as oneDspline
from scipy.interpolate import RectBivariateSpline as twoDspline

# Define parse-specific pip file entries
labelFile = dataObject('labels_from_file',string)
labels = dataObject('quantity_labels',string_dictionary)
logPlots = dataObject('use_log_scale',int_list)
rescalings = dataObject('quantity_rescalings',float_dictionary)
nBins = dataObject('number_of_bins',integer)
resolution = dataObject('interpolated_resolution',integer)
chainType = dataObject('chain_type',internal)
doEvidence = dataObject('compute_evidence',boolean)
keys = keys+[labelFile,nBins,chainType,resolution,doEvidence,labels,logPlots,rescalings]

# Initialise variables
doPosteriorMean = True
firstLikeKey = None
dataRanges = {}

def parse(filename):
  #input: 	filename = the name of the pip file
  global doPosteriorMean
    
  #Parse pip file
  getIniData(filename,keys,savekeys=[labels])

  #Read in label data if it is not in the pip file
  if labelFile.value is not None: getIniData(labelFile.value,[labels])  

  #Check that flags match up for profile likelihood
  if all(x not in labels.value for x in permittedLikes) and doProfile.value:
    print '  Warning: no likelihood in chain labels.\n  Skipping profile likelihood...'
    doProfile.value = False

  #Work out whether to do posterior mean and check that flags match up for posterior pdf
  if all(x not in labels.value for x in permittedMults):
    doPosteriorMean = False
    if doPosterior.value:
      print '  Warning: no multiplicity in chain labels.\n  Skipping posterior PDF...'
      doPosterior.value = False
  else: doPosteriorMean = True

  #Check that flags match up for evidence
  if doEvidence.value:
    if chainType.value is mcmc:      
      if all(x not in labels.value for x in permittedLikes) or \
         all(x not in labels.value for x in permittedMults) or \
         all(x not in labels.value for x in permittedPriors): 
        print '  The evidence cannot be calculated without multiplicity, prior and likelihood.\n  Skipping evidence...'
        doEvidence.value = False
    else:
      print '  The evidence can only be calculated from an MCMC chain.\n  Skipping evidence...'
      doEvidence.value = False  

  # Open main chain and read in contents
  mainArray = getChainData(mainChain.value)

  #Check that flags and match up for quantities selected for plotting
  oneDlist = [] if oneDplots.value is None else oneDplots.value
  twoDlist = [] if twoDplots.value is None else twoDplots.value  
  setOfRequestedColumns = set(oneDlist + [y for x in twoDlist for y in x])
  for plot in setOfRequestedColumns:
    if plot > mainArray.shape[1]:
      sys.exit('Error: requested column number '+str(plot)+' does not exist in chain '+mainChain.value+'.\nQuitting...\n')
    try:
      label = labels.value[plot]
    except KeyError:
      sys.exit('Error: please provide a label for column '+str(plot)+' if you want to plot it.\nQuitting...\n')

  # Parse main chain
  outputBaseFilename = re.sub(r"\..?.?.?$", '', mainChain.value)
  doParse(mainArray,outputBaseFilename,setOfRequestedColumns)

  # If a comparison chain is specified, parse it too
  if secChain.value is not None: 
    # Open secondary chain and read in contents
    outputBaseFilename = re.sub(r"\..?.?.?$", '', secChain.value)
    secArray = getChainData(secChain.value)
    if secArray.shape[1] >= max(setOfRequestedColumns):
      # Parse comparison chain
      doParse(secArray,outputBaseFilename,setOfRequestedColumns)
    else:
      print '    Chain '+secChain.value+' has less columns than required to do all requested plots.'
      print '    Skipping parsing of this chain...'
    

def doParse(dataArray,outputBaseFilename,setOfRequestedColumns):
  #Perform all numerical operations required for chain parsing
    
  # Standardise likelihood, prior and multiplicity labels, and rescale likelihood and columns if necessary
  standardise(dataArray)
  # Sort array if required
  doSort(dataArray)
  # Find best-fit point
  [bestFit,worstFit,bestFitIndex] = getBestFit(dataArray,outputBaseFilename)
  # Find posterior mean
  [totalMult, posteriorMean] = getPosteriorMean(dataArray,outputBaseFilename)
  # Get evidence for mcmc
  [lnZMain,lnZMainError] = getEvidence(dataArray,bestFit,totalMult,outputBaseFilename)
  # Save data minima and maxima
  saveExtrema(dataArray,outputBaseFilename,setOfRequestedColumns)
  # Do binning for 1D plots
  oneDsampler(dataArray,bestFit,worstFit,outputBaseFilename)
  # Do binning for 2D plots
  twoDsampler(dataArray,bestFit,worstFit,outputBaseFilename)


def standardise(dataArray):
  global firstLikeKey
  # Standardise likelihood, prior and multiplicity labels, rescale likelihood if necessary,
  for key, entry in labels.value.copy().iteritems():
    if any(key == mult for mult in permittedMults):
      labels.value[refMult] = labels.value[key]
      if key != refMult: del labels.value[key]
    if any(key == prior for prior in permittedPriors):
      labels.value[refPrior] = labels.value[key]
      if key != refPrior: del labels.value[key]
    if any(key == like for like in permittedLikes):
      if firstLikeKey is None: firstLikeKey = key 
      dataArray[:,labels.value[key]] = mapToRefLike(firstLikeKey,dataArray[:,labels.value[key]])
      labels.value[refLike] = labels.value[key]
      if key != refLike: del labels.value[key]
    if any(entry == mult for mult in permittedMults): labels.value[key] = refMult
    if any(entry == prior for prior in permittedPriors): labels.value[key] = refPrior
    if any(entry == like for like in permittedLikes): labels.value[key] = refLike
  # Rescale columns if requested
  if rescalings.value is not None: 
    for key, entry in rescalings.value.iteritems(): dataArray[:,key] *= entry
  # Convert columns to log if requested
  if logPlots.value is not None:
    for column in logPlots.value: dataArray[:,column] = np.log10(dataArray[:,column])
  

def doSort(dataArray):
  # Sort chain in order of increasing posterior mass (i.e. multiplicity)
  if doPosterior.value and contours.value is not None:
    viewString = 'float64' + ',float64' * (dataArray.shape[1]-1)
    dataArray.view(viewString).sort(order = ['f'+str(labels.value[refMult])], axis=0)   


def getBestFit(dataArray,outputBaseFilename):
  # Find best-fit point
  bestFitIndex = dataArray[:,labels.value[refLike]].argmin()
  bestFit = dataArray[bestFitIndex,labels.value[refLike]]
  worstFit = dataArray[:,labels.value[refLike]].max()
  print '    Best fit -lnlike: ',bestFit
  outfile = smart_open(outputBaseFilename+'.best','w')
  outfile.write('# This best-fit/posterior mean file created by pippi '\
                +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
  outfile.write('Best-fit log-likelihood: '+str(-bestFit)+'\n')
  outfile.write('Best-fit point:\n')
  outfile.write(' '.join([str(x) for x in dataArray[bestFitIndex,:]])+'\n')
  outfile.close
  return [bestFit,worstFit,bestFitIndex]


def getPosteriorMean(dataArray,outputBaseFilename):
  # Find posterior mean
  if doPosteriorMean:
    posteriorMean = []
    # Get total multiplicity for entire chain 
    totalMult = np.sum(dataArray[:,labels.value[refMult]])
    # Calculate posterior mean as weighted average of each point's contribution to each variable
    for i in range(dataArray.shape[1]):
      posteriorMean.append(np.sum(dataArray[:,labels.value[refMult]] * dataArray[:,i])/totalMult)
    outfile = smart_open(outputBaseFilename+'.best','a')
    outfile.write('Posterior mean:\n')
    outfile.write(' '.join([str(x) for x in posteriorMean])+'\n')
    outfile.close
    return [totalMult, posteriorMean]
  else:
    return [None, None]


def getEvidence(dataArray,bestFit,totalMult,outputBaseFilename):
  # Get evidence (sum of mult*prior*like for mcmc)
  if doEvidence.value:
    if chainType.value is mcmc:
      lnZ = np.log(np.sum(dataArray[:,labels.value[refMult]]  * \
                          dataArray[:,labels.value[refPrior]] * \
                          np.exp(bestFit-dataArray[:,labels.value[refLike]]))) \
                          - bestFit - np.log(totalMult)
      lnZError = np.log(1.0 - pow(totalMult,-0.5))
      print '    ln(evidence): ',lnZ,'+/-',lnZError
    else:
      sys.exit('Error: evidence calculation only possible for MCMC (should never get here).')
    outfile = smart_open(outputBaseFilename+'.lnZ','w')
    outfile.write('# This evidence file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
    outfile.write('ln(evidence): '+str(lnZ)+' +/- '+str(lnZError)+'\n')
    outfile.close
    return [lnZ, lnZError]
  else:
    return [None, None]


def saveExtrema(dataArray,outputBaseFilename,setOfRequestedColumns):
  # Save the maxima and minima for each parameter requested for plotting
  outfile = smart_open(outputBaseFilename+'_savedkeys.pip','a')
  outfile.write('axis_ranges =')
  for column in setOfRequestedColumns:
    extrema = [dataArray[:,column].min(), dataArray[:,column].max()]
    dataRanges[column] = extrema
    outfile.write(' '+str(column)+':{'+str(extrema[0])+', '+str(extrema[1])+'}')
  outfile.close


def oneDsampler(dataArray,bestFit,worstFit,outputBaseFilename):
  # Do sample sorting for 1D plots

  if oneDplots.value is None: return

  if contours.value is not None: 
    # Determine profile likelihood contour levels (same for all plots of a given dimensionality)
    profContourLevels = [np.exp(-deltaLnLike(0.5,0.01*contour)) for contour in contours.value]
    outfile = smart_open(outputBaseFilename+'_like1D.contours','w')
    outfile.write('# This 1D profile likelihood ratio contours file created by pippi '\
                  +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
    outfile.write(' '.join([str(x) for x in profContourLevels])+'\n')
    outfile.close

  for plot in oneDplots.value:
 
    print '    Parsing data for 1D plots of quantity ',plot

    likeGrid = np.empty((nBins.value), dtype=np.float64)
    likeGrid[:] = worstFit + 100.0
    postGrid = np.zeros((nBins.value), dtype=np.float64)
    
    # Work out maximum and minimum values of parameter/derived quantity
    minVal = dataRanges[plot][0]
    maxVal = dataRanges[plot][1]
    rangeOfVals = maxVal - minVal

    # Calculate bin centres
    binCentresOrig = np.array([minVal + (x+0.5)*rangeOfVals/nBins.value for x in range(nBins.value)])
    binCentresInterp = np.array([binCentresOrig[0] + x*(binCentresOrig[-1]-binCentresOrig[0])\
                                 /(resolution.value-1) for x in range(resolution.value)])
     
    # Loop over points in chain
    for i in range(dataArray.shape[0]-1,-1,-1):
      index = min(int((dataArray[i,plot]-minVal)/rangeOfVals*nBins.value),nBins.value-1)
  
      # Profile over likelihoods
      if doProfile.value: likeGrid[index] = min(dataArray[i,labels.value[refLike]],likeGrid[index])

      if doPosterior.value: 
        # Marginalise by addding to posterior sample count
        postGrid[index] += dataArray[i,labels.value[refMult]]

    # Save raw binned profile likelihood and posterior pdf for outputting in histogram files
    likeGridHistogram = likeGrid
    postGridHistogram = postGrid

    # Convert -log(profile likelihoods) to profile likelihood ratio (in effect this is done anyway in the next block)
    likeGrid = np.exp(bestFit - likeGrid)

    # Interpolate profile likelihoods and posterior pdfs to requested resolution
    if doProfile.value: 
      interpolator = oneDspline(binCentresOrig, likeGrid)
      likeGrid = interpolator(binCentresInterp)
      # Rescale profile likelihood ratio back into the range [0,1]
      likeMax = likeGrid.max()
      likeMin = min(likeGrid.min(),0.0)
      likeGrid = (likeGrid - likeMin) / (likeMax - likeMin)

    if doPosterior.value: 
      interpolator = oneDspline(binCentresOrig, postGrid)
      postGrid = interpolator(binCentresInterp)
      # Rescale posterior pdf back into the range [0,1]
      postMax = postGrid.max()
      postMin = min(postGrid.min(),0.0)
      postGrid = (postGrid - postMin) / (postMax - postMin)

    # Find posterior pdf contour levels
    if contours.value is not None and doPosterior.value:
      # Zero posterior contour levels
      postContourLevels = [None for contour in contours.value]
      # Zero posterior integral
      integratedPosterior = 0.0
      # Sort bins in order of posterior mass
      sortedPostGrid = np.ma.sort(postGrid)
      # Work out the new total multiplicity
      totalMult = np.sum(sortedPostGrid)
      # Work through bins backwards until total posterior mass adds up to the requested confidence levels
      for i in range(sortedPostGrid.shape[0]-1,-1,-1):
        integratedPosterior += sortedPostGrid[i]/totalMult
        for j,contour in enumerate(contours.value):
          if 100*integratedPosterior >= contour and postContourLevels[j] is None:
            postContourLevels[j] = sortedPostGrid[i]
        if all([x is not None for x in postContourLevels]): break         

    # Write profile likelihood to file
    if doProfile.value:
      outfile = smart_open(outputBaseFilename+'_'+str(plot)+'_like1D.ct2','w')
      outfile.write('# This 1D binned profile likelihood ratio file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresInterp[i])+'\t'+str(x) for i,x in enumerate(likeGrid)]))
      outfile.close
      outfile = smart_open(outputBaseFilename+'_'+str(plot)+'_like1Dhist.ct2','w')
      outfile.write('# This 1D binned profile likelihood ratio file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresOrig[i])+'\t'+str(x) for i,x in enumerate(likeGridHistogram)]))
      outfile.close

    # Write posterior pdf and contours to file
    if doPosterior.value:
      outfile = smart_open(outputBaseFilename+'_'+str(plot)+'_post1D.ct2','w')
      outfile.write('# This 1D binned posterior pdf file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresInterp[i])+'\t'+str(x) for i,x in enumerate(postGrid)]))
      outfile.close
      outfile = smart_open(outputBaseFilename+'_'+str(plot)+'_post1Dhist.ct2','w')
      outfile.write('# This 1D binned posterior pdf file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresOrig[i])+'\t'+str(x) for i,x in enumerate(postGridHistogram)]))
      outfile.close
      if contours.value is not None:
        outfile = smart_open(outputBaseFilename+'_'+str(plot)+'_post1D.contours','w')
        outfile.write('# This 1D posterior pdf contours file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
        outfile.write(' '.join([str(x) for x in postContourLevels])+'\n')
        outfile.close


def twoDsampler(dataArray,bestFit,worstFit,outputBaseFilename):
  # Do sample sorting for 2D plots

  if twoDplots.value is None: return

  # Determine profile likelihood contour levels (same for all plots of a given dimensionality)
  if contours.value is not None:
    profContourLevels = [np.exp(-deltaLnLike(1.0,0.01*contour)) for contour in contours.value]
    outName = outputBaseFilename+'_like2D.contours'
    outfile = smart_open(outName,'w')
    outfile.write('# This 2D profile likelihood ratio contours file created by pippi '\
                  +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
    outfile.write(' '.join([str(x) for x in profContourLevels]))
    outfile.close

  for plot in twoDplots.value:

    print '    Parsing data for 2D plots of quantities ',plot

    likeGrid = np.empty((nBins.value,nBins.value), dtype=np.float64)
    likeGrid[:,:] = worstFit + 100.0
    postGrid = np.zeros((nBins.value,nBins.value), dtype=np.float64)

    # Work out maximum and minimum values of parameters/derived quantities
    minVal = [dataRanges[plot[j]][0] for j in range(2)]
    maxVal = [dataRanges[plot[j]][1] for j in range(2)]
    rangeOfVals = [maxVal[j] - minVal[j] for j in range(2)]
    # Pad edges of grid
    binSep = [rangeOfVals[j]/(nBins.value-2) for j in range(2)]
    minVal = [minVal[j] - binSep[j] for j in range(2)]
    maxVal = [maxVal[j] + binSep[j] for j in range(2)]
    rangeOfVals = [rangeOfVals[j] + 2.0 * binSep[j] for j in range(2)]

    # Calculate bin centres
    binCentresOrig = np.array([[minVal[j] + (x+0.5)*rangeOfVals[j]/nBins.value for x in range(nBins.value)] for j in range(2)])
    binCentresInterp = np.array([[binCentresOrig[j][0] + x*(binCentresOrig[j][-1]-binCentresOrig[j][0])\
                                 /(resolution.value-1) for x in range(resolution.value)] for j in range(2)])
    
    # Loop over points in chain
    for i in range(dataArray.shape[0]-1,-1,-1):
      [in1,in2] = [min(int((dataArray[i,plot[j]]-minVal[j])/rangeOfVals[j]*nBins.value),nBins.value-2) for j in range(2)]
  
      # Profile over likelihoods
      if doProfile.value: likeGrid[in1,in2] = min(dataArray[i,labels.value[refLike]],likeGrid[in1,in2])

      if doPosterior.value: 
        # Marginalise by addding to posterior sample count
        postGrid[in1,in2] += dataArray[i,labels.value[refMult]]

    # Convert -log(profile likelihoods) to profile likelihood ratio (in effect this is done anyway in the next block)
    likeGrid = np.exp(bestFit - likeGrid)

    # Interpolate posterior pdf and profile likelihood to requested display resolution
    if doProfile.value:
      interpolator = twoDspline(binCentresOrig[0,:], binCentresOrig[1,:], likeGrid, ky = 1, kx = 1)
      likeGrid = np.empty((resolution.value,resolution.value), dtype=np.float64)
      likeGrid[:,:] = worstFit + 100.0
      likeGrid = np.array([[interpolator(binCentresInterp[0,j], binCentresInterp[1,i]).flatten() 
                          for i in range(resolution.value)] for j in range(resolution.value)])
      likeGrid = likeGrid[:,:,0]
      # Make sure we haven't erased the best-fit point by interpolating over it
      likeGrid[np.unravel_index(likeGrid.argmax(),likeGrid.shape)] = 1.0

    if doPosterior.value: 
      interpolator = twoDspline(binCentresOrig[0,:], binCentresOrig[1,:], postGrid, ky = 1, kx = 1)
      postGrid = np.zeros((resolution.value,resolution.value), dtype=np.float64)
      postGrid = np.array([[interpolator(binCentresInterp[0,j], binCentresInterp[1,i]).flatten()
                          for i in range(resolution.value)] for j in range(resolution.value)])
      postGrid = postGrid[:,:,0]
      # Rescale posterior pdf back into the range [0,1]
      postMax = postGrid.max()
      postMin = min(postGrid.min(),0.0)
      postGrid = (postGrid - postMin) / (postMax - postMin)
    
    # Find posterior pdf contour levels
    if contours.value is not None and doPosterior.value:
      # Zero posterior contour levels
      postContourLevels = [None for contour in contours.value]
      # Zero posterior integral
      integratedPosterior = 0.0
      # Sort bins in order of posterior mass
      sortedPostGrid = np.ma.sort(postGrid.flatten())
      # Work out the new total multiplicity
      totalMult = np.sum(sortedPostGrid)
      # Work through bins backwards until total posterior mass adds up to the requested confidence levels
      for i in range(sortedPostGrid.shape[0]-1,-1,-1):
        integratedPosterior += sortedPostGrid[i]/totalMult
        for j,contour in enumerate(contours.value):
          if 100*integratedPosterior >= contour and postContourLevels[j] is None:
            postContourLevels[j] = sortedPostGrid[i]
        if all([x is not None for x in postContourLevels]): break

    # Write profile likelihood to file
    if doProfile.value:
      outName = outputBaseFilename+'_'+'_'.join([str(x) for x in plot])+'_like2D.ct2'
      outfile = smart_open(outName,'w')  
      outfile.write('# This 2D binned profile likelihood ratio file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresInterp[0,i])+'\t'+str(binCentresInterp[1,j])+'\t'+str(likeGrid[i,j]) \
                               for i in range(likeGrid.shape[0]) for j in range(likeGrid.shape[1])]))
      outfile.close

    # Write posterior pdf and contours to file
    if doPosterior.value:
      outName = outputBaseFilename+'_'+'_'.join([str(x) for x in plot])+'_post2D.ct2'
      outfile = smart_open(outName,'w')
      outfile.write('# This 2D binned posterior pdf file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
      outfile.write('\n'.join([str(binCentresInterp[0,i])+'\t'+str(binCentresInterp[1,j])+'\t'+str(postGrid[i,j]) \
                               for i in range(postGrid.shape[0]) for j in range(postGrid.shape[1])]))
      outfile.close
      if contours.value is not None:
        outName = outputBaseFilename+'_'+'_'.join([str(x) for x in plot])+'_post2D.contours'
        outfile = smart_open(outName,'w')
        outfile.write('# This 2D posterior pdf contours file created by pippi '\
                     +pippiVersion+' on '+datetime.datetime.now().strftime('%c')+'\n')
        outfile.write(' '.join([str(x) for x in postContourLevels]))
        outfile.close

