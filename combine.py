import pandas as pd
import os, sys
import argparse
import pickle
import pdb

argp = argparse.ArgumentParser()
argp.add_argument("-f", "--file-name", type=str, default='',  help="File stem for imageDB and tracks to read from directory")
argp.add_argument("-d", "--directory", type=str, default='pickled_data/',  help="Specify the directory where the multiprocessing file output are. Default=pickled_data")
args = argp.parse_args()

# combined retired subjects and image_db pickles

files = os.listdir(args.directory)
imageDB_list = []
tracks_list = []
for names in files:
    if names.startswith('imageDB_'+args.file_name):
        imageDB_list.append(names)
    elif names.startswith('tracks_'+args.file_name):
        tracks_list.append(names)
imageDB_list.sort()
tracks_list.sort()

tracks={}
for f in tracks_list:
    with open(args.directory+f,"rb") as f:
        temp = pickle.load(f)
        tracks.update(temp)

imageDB = pd.DataFrame()
for f in imageDB_list:
    temp = pd.read_pickle(args.directory+f)
    imageDB =imageDB.append(temp)

imageDB.to_pickle(args.directory+'imageDB_'+args.file_name+'.pkl')
pickle.dump(tracks, open('tracks_'+args.file_name+'.pkl', "wb" ))
