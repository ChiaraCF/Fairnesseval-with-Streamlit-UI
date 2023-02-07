from copy import deepcopy

import numpy as np
import pandas as pd
import scipy.optimize as opt
from sklearn.model_selection import GridSearchCV, RepeatedStratifiedKFold

from fairlearn.reductions import ErrorRate, GridSearch
from fairlearn.reductions import ExponentiatedGradient, DemographicParity
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression


def solve_linprog_strict(errors=None, gammas=None, eps=0.05, nu=1e-6, pred=None):
    B = 1 / eps
    n_hs = len(pred)
    n_constraints = 4  # len()

    c = np.concatenate(errors)
    A_ub = gammas  # gammas @ weights <= eps
    b_ub = np.repeat(eps, n_constraints)
    A_eq = np.ones(1, n_hs)
    b_eq = np.ones(1)
    result = opt.linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, method='highs-ds')
    Q = pd.Series(result.x[:-1])
    return Q


def solve_linprog(errors=None, gammas=None, eps=0.05, nu=1e-6, pred=None):
    B = 1 / eps
    n_hs = len(pred)
    n_constraints = gammas.shape[0]  # len()

    c = np.concatenate((errors, [B ** 2]))  # min err @ weights + B^2 * x5 # for feasibility
    A_ub = np.concatenate((gammas, -np.ones((n_constraints, 1))), axis=1)  # vio @ weights <= eps + x5
    b_ub = np.repeat(eps, n_constraints)
    A_eq = np.array([[1] * n_hs + [0]])
    b_eq = np.ones((1, 1))
    result = opt.linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, method='highs-ds')
    Q = pd.Series(result.x[:-1])
    return Q


def _pmf_predict(X, predictors, weights):
    pred_dict = {}
    for t in range(len(predictors)):
        pred_dict[t] = predictors[t].predict(X)
    pred = pd.DataFrame(pred_dict)
    positive_probs = pred[weights.index].dot(weights).to_frame()
    return np.concatenate((1 - positive_probs, positive_probs), axis=1)


class ExponentiatedGradientPmf(ExponentiatedGradient):
    def predict(self, X, random_state=None):
        return self._pmf_predict(X)[:, 1]


class Hybrid5(BaseEstimator):

    def __init__(self, expgrad_frac=None, eps=None, constraint=None, unconstrained_model=None):
        if constraint is None:
            constraint = DemographicParity(difference_bound=eps)
        self.constraint = constraint
        self.expgrad_logistic_frac = expgrad_frac
        self.eps = eps
        self.unconstrained_model = unconstrained_model

        self.add_exp_predictors = False

    def fit_expgrad(self, X, y, sensitive_features):
        expgrad_frac = ExponentiatedGradient(LogisticRegression(solver='liblinear', fit_intercept=True),
                                             constraints=self.constraint, eps=self.eps, nu=1e-6)
        print("Fitting ExponentiatedGradient on subset...")
        expgrad_frac.fit(X, y, sensitive_features=sensitive_features)
        self.expgrad_logistic_frac = expgrad_frac

    def get_error_violation(self, X, y, sensitive_features, predictors):
        error_list = []
        violation_dict = {}
        # violation of log res
        disparity_moment = DemographicParity()
        disparity_moment.load_data(X, y,
                                   sensitive_features=sensitive_features)  # try different demographic parity function
        # error of log res
        error = ErrorRate()
        error.load_data(X, y, sensitive_features=sensitive_features)  # Add timing here
        for x, turn_predictor in enumerate(predictors):
            def Q_preds(X): return turn_predictor.predict(X)

            turn_violation = disparity_moment.gamma(Q_preds)
            turn_error = error.gamma(Q_preds)['all']

            violation_dict[x] = turn_violation
            error_list.append(turn_error)

        error_list = pd.Series(error_list)
        return error_list, pd.DataFrame(violation_dict)

    def fit(self, X, y, sensitive_features):
        if self.expgrad_logistic_frac is None:
            self.fit_expgrad(X, y, sensitive_features)
        self.predictors = self.expgrad_logistic_frac.predictors_  # fairlearn==0.5.0
        # self.expgrad_predictors = expgrad_frac._predictors  # fairlearn==0.4
        self.concat_predictors()
        # In hybrid 5, lin program is done on top of expgrad partial.
        # a = datetime.now() # TODO
        errors, violations = self.get_error_violation(X, y, sensitive_features, self.predictors)
        self.weights = solve_linprog(errors=errors, gammas=violations, eps=self.eps, nu=1e-6,
                                     pred=self.predictors)
        return self

    def predict(self, X):
        return _pmf_predict(X, self.predictors, self.weights)[:, 1]

    def concat_predictors(self):
        if self.add_exp_predictors is not None and self.add_exp_predictors == True:
            self.predictors = list(self.predictors) + list(self.expgrad_logistic_frac.predictors_)
        if self.unconstrained_model is not None:
            self.predictors_no_unconstrained = deepcopy(self.predictors)
            self.predictors = list(self.predictors_no_unconstrained) + [self.unconstrained_model]


class Hybrid1(Hybrid5):

    def __init__(self, base_model=None, expgrad=None, grid_search_frac=None, eps=None, constraint=None,
                 unconstrained_model=None, subsample=None, random_state=None):
        super().__init__(eps=eps, constraint=constraint, unconstrained_model=unconstrained_model)
        self.expgrad_logistic_frac = expgrad
        self.grid_search_frac = grid_search_frac
        self.base_model = base_model
        self.subsample = subsample
        self.random_state = random_state

    def fit_grid(self, X, y, sensitive_features, ):
        if self.expgrad_logistic_frac is None:
            self.fit_expgrad(X, y, sensitive_features)
        self.grid_search_frac = GridSearch(subsample=self.subsample, random_state=self.random_state,
                                           estimator=self.base_model, constraints=self.constraint,
                                           grid=self.expgrad_logistic_frac.lambda_vecs_)
        # _lambda_vecs_lagrangian  # fairlearn==0.4
        self.grid_search_frac.fit(X, y, sensitive_features=sensitive_features)

    def fit(self, X, y, sensitive_features):
        if self.expgrad_logistic_frac is None:
            self.fit_expgrad(X, y, sensitive_features)
        if self.grid_search_frac is None:
            self.fit_grid(X, y, sensitive_features)
        return self

    def predict(self, X):
        return self.grid_search_frac.predict(X)


class Hybrid2(Hybrid1):
    def predict(self, X):
        self.weights = self.expgrad_logistic_frac.weights_
        self.predictors = self.grid_search_frac.predictors_
        return _pmf_predict(X, self.predictors, self.weights)[:, 1]


class Hybrid3(Hybrid1):

    def __init__(self, add_exp_predictors=False, expgrad=None, grid_search_frac=None, eps=None, constraint=None,
                 unconstrained_model=None):
        super().__init__(expgrad=expgrad, grid_search_frac=grid_search_frac, eps=eps, constraint=constraint,
                         unconstrained_model=unconstrained_model)
        self.add_exp_predictors = add_exp_predictors

    def fit(self, X, y, sensitive_features):
        if self.grid_search_frac is None:
            self.fit_grid(X, y, sensitive_features)
        self.predictors = self.grid_search_frac.predictors_  # fairlearn==0.5.0
        # self.expgrad_predictors = expgrad_frac._predictors  # fairlearn==0.4

        self.concat_predictors()
        errors, violations = self.get_error_violation(X, y, sensitive_features, self.predictors)
        self.weights = solve_linprog(errors=errors, gammas=violations, eps=self.eps, nu=1e-6,
                                     pred=self.predictors)
        return self

    def predict(self, X):
        return _pmf_predict(X, self.predictors, self.weights)[:, 1]


class Hybrid4(Hybrid1):

    def fit(self, X, y, sensitive_features):
        super().fit(X, y, sensitive_features)
        weights_logistic = self.expgrad_logistic_frac.weights_
        predictors = self.grid_search_frac.predictors_
        re_wts_predictors = [predictors[idx] for idx, turn_weight in enumerate(weights_logistic) if turn_weight != 0]
        self.predictors = re_wts_predictors
        self.concat_predictors()
        errors, violations = self.get_error_violation(X, y, sensitive_features, self.predictors)
        self.weights = solve_linprog(errors=errors, gammas=violations, eps=self.eps, nu=1e-6,
                                     pred=self.predictors)

    def predict(self, X):
        return _pmf_predict(X, self.predictors, self.weights)[:, 1]


def get_base_model(base_model_code, random_seed=0):
    if base_model_code is None or base_model_code == 'lr':
        # Unmitigated LogRes
        model = LogisticRegression(solver='liblinear', fit_intercept=True, random_state=random_seed)
    elif base_model_code == 'gbm':
        model = GradientBoostingClassifier(random_state=random_seed)
    elif base_model_code == 'lgbm':
        model = HistGradientBoostingClassifier(random_state=random_seed)
    else:
        assert False, f'available model codes are:{["lr", "gbm", "lgbm"]}'
    return model


def get_model_parameter_grid(base_model_code=None):
    if base_model_code is None or base_model_code == 'lr':
        # Unmitigated LogRes
        return {'solver': [  # 'newton-cg',
            'lbfgs',
            'liblinear'
        ],
            'penalty': ['l2'],
            'C': [0.01, 0.005, 0.001],
            # [10, 1.0, 0.1, 0.05, 0.01],
            # max-iter': 100,
        }
    elif base_model_code == 'gbm':
        return dict(n_estimators=[10, 100, 500],
                    learning_rate=[0.001, 0.01, 0.1],
                    subsample=[0.5, 0.7, 1.0],
                    max_depth=[3, 7, 9])
    elif base_model_code == 'lgbm':
        return dict(
            l2_regularization=[10, 0.1, 0.01],
            learning_rate=[0.001, 0.01, 0.1],
            max_depth=[3, 7, 9])
    else:
        assert False, f'available model codes are:{["lr", "gbm", "lgbm"]}'


def finetune_model(base_model_code, X, y, random_seed=0):
    base_model = get_base_model(base_model_code=base_model_code, random_seed=random_seed)
    parameters = get_model_parameter_grid(base_model_code=base_model_code)
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=1, random_state=random_seed)
    clf = GridSearchCV(base_model, parameters, cv=cv, n_jobs=1, scoring=['f1', 'accuracy'], refit='f1')
    clf.fit(X, y)
    return clf
