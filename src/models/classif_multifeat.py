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
from sklearn.model_selection import RandomizedSearchCV
from mlneurotools.ml import classification, StratifiedShuffleGroupSplit
from xgboost import XGBClassifier
from scipy.stats import uniform
from itertools import permutations
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
#KNN for K nearest neighbors
#SVM for support vector machine
#DT for decision tree
#LR for Logistic Regression
#XGBC for XGBoost Classifier
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
        clf = KNeighborsClassifier()
        distributions = dict(n_neighbors=np.arange(1, 16, 1),
                            weights = ['uniform', 'distance'],
                            metric = ['minkowski', 'euclidean', 'manhattan'])
    elif model == "SVM" :
        clf = SVC()
        distributions = dict()
    elif model == "DT" :
        clf = DecisionTreeClassifier()
        distributions = dict(criterion=['gini', 'entropy'], splitter=['best', 'random']) #Idk if need more hp
    elif model == "LR":
        clf = LogisticRegression()
        distributions = dict(C=uniform(loc=0, scale=4),
                                penalty=['l2', 'l1', 'elasticnet', 'none'], solver=['newton-cg', 'lbfgs', 'liblinear', 'sag', 'saga'],
                                multi_class = ['auto', 'ovr', 'multinomial'])
    elif model == "XGBC" :
        clf = XGBClassifier()

    #Loop for permutations

    #Find best parameters
    if model!='XGBC' and model!='LDA':
        outer_cv = LeaveOneGroupOut()
        inner_cv = LeaveOneGroupOut()
        DA_list = []
        best_params_list = []

        for train_outer, test_outer in outer_cv.split(X, y, groups):
            #Need to add the "fixed" randomized search
            search = RandomizedSearchCV(clf, distributions, cv=inner_cv, random_state=0).fit(X[train_outer], y[train_outer], groups[train_outer])
            best_params = search.best_params_
            #Apply best hyperparameters to our classifier (with perms this time)
            if model == "KNN" :
                metric = best_params['metric']
                n_neighbors = best_params['n_neighbors']
                weights= best_params['weights']
                clf = KNeighborsClassifier(n_neighbors=n_neighbors, metric=metric, weights=weights)
            elif model == "SVM" :
                clf = SVC(best_params)
            elif model == "DT" :
                criterion=best_params['criterion']
                splitter = best_params['splitter']
                clf = DecisionTreeClassifier(criterion=criterion, splitter=splitter)
            elif model == "LR":
                C = best_params['C']
                penalty = best_params['penalty']
                solver = best_params['solver']
                multi_class = best_params['multi_class']
                clf = LogisticRegression(C=C, penalty=penalty, solver=solver, multi_class=multi_class)
        
            for _ in range(n_perms) :
                #Randomized y for permutations
                y_perm = permutations(y)
                clf.fit(X[train_outer], y[train_outer])
                DA = clf.score(X[test_outer], y[test_outer])
                print('Done')
                print('DA : ' + str(DA))
                print('Best params : ' + str(best_params))
               
                #Store DA and best_params
                best_params_list.append(best_params)
                DA_list.append(DA)


            #Find the higher DA and its best_params
            index = 0
            max_DA = max(DA_list)
            hyperparameters = []
            for i, elt in enumerate(DA_list): 
                if elt == max_DA : 
                    index = i 
            hyperparameters = best_params_list[index]

                # TODO :
                # - Need to add the pvalue

            #Save DA and hyperparameters into results
            results={}
            results['acc_score'] = max_DA
            results['best_params'] = hyperparameters

            #Print the best DA with its hyperparameters
            print('Best DA :' + str(max_DA))
            print('Best hyperparameters : ' +str(hyperparameters))
           
    else:
        inner_cv = LeaveOneGroupOut()
        results = classification(clf, inner_cv, X, y, groups=groups, perm=n_perms, n_jobs=8)
        print('Done')
        print('DA : ' + str(results['acc_score']))
        print('p value : ' + str(results['acc_pvalue']))


    return results


def prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, conds_list, CHAN=0, balance=False):
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
    X = np.array(X).reshape(-1, len(X_balanced[0]))
    y = np.asarray(y)
    groups = np.asarray(groups)
    return X, y, groups

if __name__ == "__main__":
    model = args.model
    split = args.split
    n_perms = args.n_permutations
    by = args.by
    if by == 'VTC':
        conds_list = (ZONE_CONDS[0] + str(split[0]), ZONE_CONDS[1] + str(split[1]))
        balance = True
    elif by == 'odd':
        conds_list = ['FREQhits', 'RAREhits']
        balance = True

    if model!='XGBC' and model!='LDA' :
        savepath = RESULTS_PATH + '{}_'.format(by) + model + 'mf_LOGO_RSCV_{}perm_{}{}/'.format(n_perms, split[0], split[1])
    else :
        savepath = RESULTS_PATH + '{}_'.format(by) + model + 'mf_LOGO_{}perm_{}{}/'.format(n_perms, split[0], split[1])

    if not(os.path.isdir(savepath)):
        os.makedirs(savepath)

    if args.channel != None:
        CHAN = args.channel
        savename = 'chan_{}.pkl'.format(CHAN)
        X, y, groups = prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, conds_list, CHAN=CHAN, balance=balance)
        result = classif_multifeat(X,y, groups, n_perms=n_perms, model=model)
        with open(savepath + savename, 'wb') as f:
            pickle.dump(result, f)
    else:
        for CHAN in range(270):
            savename = 'chan_{}.pkl'.format(CHAN)
            print(savename)
            if not(os.path.isfile(savepath + savename)):
                X, y, groups = prepare_data(BIDS_PATH, SUBJ_LIST, BLOCS_LIST, conds_list, CHAN=CHAN, balance=balance)
                result = classif_multifeat(X,y, groups, n_perms=n_perms, model=model)
                with open(savepath + savename, 'wb') as f:
                    pickle.dump(result, f)
            print('Ok.')
