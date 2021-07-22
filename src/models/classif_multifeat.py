from src.saflow_params import BIDS_PATH, SUBJ_LIST, BLOCS_LIST, FREQS_NAMES, ZONE_CONDS, RESULTS_PATH
import pickle
from src.utils import get_SAflow_bids
import numpy as np
from sklearn.model_selection import StratifiedShuffleSplit, GroupShuffleSplit, ShuffleSplit, LeaveOneGroupOut, KFold
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from mlneurotools.ml import classification, StratifiedShuffleGroupSplit
import argparse
import os
import random

parser = argparse.ArgumentParser()
parser.add_argument(
    "-c",
    "--channel",
    default=None,
    type=int,
    help="Channels to compute",
)
parser.add_argument(
    "-p",
    "--n_permutations",
    default=1000,
    type=int,
    help="Number of permutations",
)
parser.add_argument(
    "-s",
    "--split",
    default=[25, 75],
    type=int,
    nargs='+',
    help="Bounds of percentile split",
)
parser.add_argument(
    "-by",
    "--by",
    default="VTC",
    type=str,
    help="Choose the classification problem ('VTC' or 'odd')",
)

#The arguments for the model selection can be :
#KNN for K neearest neighbors
#SVM for support vector machine
#DT for decision tree
#LR for Logistic Regression
parser.add_argument(
    "-m",
    "--model",
    default="LDA", 
    type=str,
    help="Classifier to apply",
)

args = parser.parse_args()

def classif_multifeat(X,y,groups, n_perms, model):
    
    if model == "LDA" : 
        clf = LinearDiscriminantAnalysis()    
    elif model == "KNN" :
        clf = KNeighborsClassifier(n_neighbors=5)
    elif model == "SVM" :
        clf = SVC()
    elif model == "DT" : 
        clf = DecisionTreeClassifier()
    elif model == "LR":
        clf = LogisticRegression()

    cv = LeaveOneGroupOut()
    results = classification(clf, cv, X, y, groups=groups, perm=n_perms, n_jobs=8)
    print('Done')
    print('DA : ' + str(results['acc_score']))
    print('p value : ' + str(results['acc_pvalue']))
    return results

def prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, FREQS_NAMES, conds_list, CHAN=0, balance=False):
    # Prepare data
    X = []
    y = []
    groups = []
    for i_subj, subj in enumerate(SUBJ_LIST):
        for run in BLOCS_LIST:
            for i_cond, cond in enumerate(conds_list):
                _, fpath_condA = get_SAflow_bids(BIDS_PATH, subj, run, stage='PSD', cond=cond)
                with open(fpath_condA, 'rb') as f:
                    data = pickle.load(f)
                for x in data[:, CHAN, :]:
                    X.append(x)
                    y.append(i_cond)
                    groups.append(i_subj)
    if balance :
        X_balanced = []
        y_balanced = []
        groups_balanced = []
        # We want to balance the trials across subjects
        for subj_idx in np.unique(groups):
            y_subj = [label for i, label in enumerate(y) if groups[i] == subj_idx]
            max_trials = min(np.unique(y_subj, return_counts=True)[1])

            X_subj_0 = [x for i, x in enumerate(X) if groups[i] == subj_idx and y[i] == 0]
            X_subj_1 = [x for i, x in enumerate(X) if groups[i] == subj_idx and y[i] == 1]

            idx_list_0 = [x for x in range(len(X_subj_0))]
            idx_list_1 = [x for x in range(len(X_subj_1))]
            picks_0 = random.sample(idx_list_0, max_trials)
            picks_1 = random.sample(idx_list_1, max_trials)

            for i in range(max_trials):
                X_balanced.append(X_subj_0[picks_0[i]])
                y_balanced.append(0)
                groups_balanced.append(subj_idx)
                X_balanced.append(X_subj_1[picks_1[i]])
                y_balanced.append(1)
                groups_balanced.append(subj_idx)
        X = X_balanced
        y = y_balanced
        groups = groups_balanced
    X = np.array(X).reshape(-1, len(FREQS_NAMES))
    return X, y, groups

if __name__ == "__main__":
    model = args.model
    split = args.split
    n_perms = args.n_permutations
    conds_list = (ZONE_CONDS[0] + str(split[0]), ZONE_CONDS[1] + str(split[1]))
    by = args.by
    if by == 'VTC':
        conds_list = (ZONE_CONDS[0] + str(split[0]), ZONE_CONDS[1] + str(split[1]))
        balance = True
    elif by == 'odd':
        conds_list = ['FREQhits', 'RAREhits']
        balance = True

    savepath = RESULTS_PATH + '{}_'.format(by) + model + 'mf_LOGO_{}perm_{}{}/'.format(n_perms, split[0], split[1])

    if not(os.path.isdir(savepath)):
        os.makedirs(savepath)

    if args.channel != None:
        CHAN = args.channel
    if args.channel != None :
        savename = 'chan_{}.pkl'.format(CHAN)
        X, y, groups = prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, FREQS_NAMES, conds_list, CHAN=CHAN, balance=balance)
        result = classif_singlefeat(X,y, groups, n_perms=n_perms, model=model)
        with open(savepath + savename, 'wb') as f:
            pickle.dump(result, f)
    else:
        for CHAN in range(270):
            savename = 'chan_{}.pkl'.format(CHAN)
            if not(os.path.isfile(savepath + savename)):
                X, y, groups = prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, FREQS_NAMES, conds_list, CHAN=CHAN, balance=balance)
                result = classif_multifeat(X,y, groups, n_perms=n_perms, model=model)
                with open(savepath + savename, 'wb') as f:
                    pickle.dump(result, f)
            print('Ok.')
