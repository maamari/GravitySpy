import pandas as pd
import numpy as np
import os, sys
import pickle
import pdb
import argparse

### Argument handling ###

argp = argparse.ArgumentParser()
argp.add_argument("-nc", "--num_cores", type=int, help="Specify the number of cores that the retirement code will be parallelized over")
argp.add_argument("-i", "--index", type=int, help="Index which indicates the chunk of image files that retirement will be calculated for")
args = argp.parse_args()



# Obtain number of classes from API
pickle_in = open("pickled_data/workflowDictSubjectSets.pkl","rb")
workflowDictSubjectSets = pickle.load(pickle_in)
classes = sorted(workflowDictSubjectSets[2117].keys())

# From ansers Dict determine number of classes
numClasses = len(classes)

# Flat retirement criteria
retired_thres = .9*np.ones(numClasses)

# Flat priors b/c we do not know what category the image is in
priors = np.ones((numClasses))/numClasses

# Load info about classifications and glitches
print '\nreading classifications...'
classifications = pd.read_pickle('pickled_data/classifications.pkl')
classifications = classifications.loc[~(classifications.annotations_value_choiceINT == -1)]
# NOTE: we remove all classifications that were done on defunct workflows
classifications = classifications.loc[~(classifications.weight == 0.0)]

print 'reading glitches...'
glitches = pd.read_pickle('pickled_data/glitches.pkl')
# filter glitches for only testing images
glitches = glitches.loc[glitches.ImageStatus != 'Training']
glitches['MLScore'] = glitches[classes].max(1)
glitches['MLLabel'] = glitches[classes].idxmax(1)

# Load confusion matrices
print 'reading confusion matrices...'
conf_matrices = pd.read_pickle('pickled_data/conf_matrices.pkl')

# Merge DBs
print 'combining data...'
combined_data = classifications.merge(conf_matrices, on=['id','links_user'])
combined_data = combined_data.merge(glitches, on=['links_subjects', 'uniqueID'])

# Get rid of unnecessary files
classifications, glitches, conf_matrices = 0,0,0
# Remove unnecessary columns from combined_data
col_list = ['id','uniqueID','links_subjects','links_user','MLScore','MLLabel','annotations_value_choiceINT','conf_matrix','weight','metadata_finished_at']+sorted(workflowDictSubjectSets[2117].keys())
combined_data = combined_data[col_list]

# Must start with earlier classifications and work way to new ones
combined_data.drop_duplicates(['links_subjects','links_user'],inplace=True)

# Create imageDB
columnsForImageDB = sorted(workflowDictSubjectSets[2117].keys())
columnsForImageDB.extend(['uniqueID','links_subjects','MLScore','MLLabel','id'])
image_db = combined_data[columnsForImageDB].drop_duplicates(['links_subjects'])
image_db.set_index(['links_subjects'],inplace=True)
image_db['numLabel'] = 0
image_db['retired'] = 0
image_db['numRetire'] = 0
image_db['finalScore'] = 0.0
image_db['finalLabel'] = ''
image_db['cum_weight'] = 0.0


def get_post_contribution(x):
    # NOTE: the subject link is the variable x
    # find all classifications for a particular subject
    glitch = combined_data[combined_data.links_subjects==x]
    # NOTE: for now only take classifications from registered users
    glitch = glitch[glitch.links_user != 0]
    # ensure each classification id has a confusion matrix
    matrices = combined_data[combined_data.id.isin(glitch.id)]
    glitch = glitch[glitch.id.isin(matrices.id)]
    # sort based on when the classification was made
    glitch = glitch.sort_values('metadata_finished_at')
    # counter to keep track of the weighting normalization, starts at 1.0 for machine
    weight_ctr = 1.0

    # loop through all people that classified until retirement is reached
    for person in glitch.links_user:
        # for now, let's assume everything with >20 classifications and no retirement has not retired
        if image_db.loc[x, 'numLabel'] > 20:
            return

        classification = glitch[glitch.links_user == person]
        # if they classified the image multiple times, take the most recent classification
        if len(classification) > 1:
            classification = classification.iloc[-1]
        # save the correct confusion matrix
        matrix = matrices[matrices.id == int(classification.id)].conf_matrix.values[0]
        # for every image they classifiy as a certain type, a users contribution to the posterior for that type is the same for every image. Therefore, it is in our interest to pre-compute all of these values.
        post_contribution = matrix/np.sum(matrix, axis=1)
        # find the row associated with the annotation the user made
        row = int(classification.annotations_value_choiceINT)
        # grab the posterior contribution for that class, weighted by classification weight
        posteriorToAdd = float(classification.weight)*post_contribution[row, :]
        if np.isnan(posteriorToAdd).any():
            return
        # keep track of weighting counter for normalization purposes
        weight_ctr += float(classification.weight)
        # for now, only use posteriors for users that have seen and classified a golden image of this particular class
        # update image_db with the posterior contribution
        image_db.loc[x, classes] = image_db.loc[x, classes].add(np.asarray(posteriorToAdd).squeeze())
        # NOTE: normalize the posterior contribution when saved
        # add 1 to numLabels for all images
        image_db.loc[x, 'numLabel'] = image_db.loc[x, 'numLabel'] + 1
        # check if we have more than 1 label for an image and check for retirement
        # Check if posterior is above threshold, add 1 for the ML component
        #posterior = image_db.loc[x][classes].divide(image_db.loc[x]['numLabel'] + 1)
        posterior = image_db.loc[x][classes]
        if ((posterior.divide(weight_ctr) > retired_thres).any() and image_db.loc[x, 'numLabel'] > 1):
            # save count that was needed to retire image
            image_db.loc[x, classes] = image_db.loc[x, classes].divide(weight_ctr)
            image_db.loc[x, 'numRetire'] = image_db.loc[x, 'numLabel']
            image_db.loc[x, 'finalScore'] = posterior.divide(weight_ctr).max()
            image_db.loc[x, 'finalLabel'] = posterior.divide(weight_ctr).idxmax()
            image_db.loc[x, 'retired'] = 1
            image_db.loc[x, 'cum_weight'] = weight_ctr
            return


print 'determining retired images...'
# sort data based on subjects number
subjects = combined_data.links_subjects.unique()
subjects.sort()

# implementation for multiprocessing
breakdown = np.linspace(0,len(subjects),args.num_cores+1)
cut_subjects = subjects[int(np.floor(breakdown[args.index])):int(np.floor(breakdown[args.index+1]))]
print cut_subjects

for idx, g in enumerate(cut_subjects):
    get_post_contribution(g)
    if idx%100 == 0:
        print '%.2f%% complete' % (100*float(idx)/len(cut_subjects))

retired_db = image_db.loc[image_db.retired == 1]
retired_db.to_pickle('pickled_data/multiproc_jobarray/ret_subjects_'+str(args.index)+'.pkl')
image_db.to_pickle('pickled_data/multiproc_jobarray/image_db_'+str(args.index)+'.pkl')