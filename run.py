import gc
import itertools
import json
import logging
import traceback
from copy import deepcopy
from functools import partial
import joblib, re
import numpy as np
import send2trash

from tqdm import tqdm
import sys
import os
import socket
from argparse import ArgumentParser
from datetime import datetime
from warnings import simplefilter
import pandas as pd
from sklearn.model_selection import train_test_split

import metrics
from models import models
from run_experiments import utils_prepare_data
import inspect
from models.hybrid_models import Hybrid5, Hybrid1, Hybrid2, Hybrid3, Hybrid4, ExponentiatedGradientPmf

from run_experiments.utils_experiment import get_config_by_id
from utils_general import DeprecateAction, mark_deprecated_help_strings, Singleton
from run_experiments.utils_prepare_data import get_constraint


def to_arg(list_p, dict_p, original_argv):
    res_string = original_argv + list_p
    for key, value in dict_p.items():
        if isinstance(value, list) or isinstance(value, range):
            value = [str(x) for x in value]
            # value = ' '.join([str(x) for x in value])
        else:
            value = [value]
        res_string += [key] + value
        # res_string += [f'{key}={value}']
    return res_string


def execute_experiment(list_p, dict_p, original_argv):
    orig_argv = sys.argv
    sys.argv = to_arg(list_p, dict_p, original_argv)
    exp_run = ExperimentRun()
    exp_run.run()
    sys.argv = orig_argv


params_initials_map = {'d': 'dataset', 'm': 'method', 'e': 'eps', 'ndp': 'num_data_points', 'nf': 'num_features',
                       't': 'theta', 'g': 'groups', 'gp': 'group_prob', 'yp': 'y_prob', 'sp': 'switch_pos',
                       'sn': 'switch_neg', 'sv': 'sample_variations', 'ef': 'exp_fractions', 'gf': 'grid_fractions',
                       'egr': 'exp_grid_ratio', 'es': 'exp_subset', 's': 'states', 'rs': 'random_seed',
                       'rls': 'run_linprog_step', 'rt': 'redo_tuning', 're': 'redo_exp', 'bmc': 'base_model_code',
                       'cc': 'constraint_code', 'gri': 'grid_fractions', 'tts': 'train_test_split',
                       'eps': 'eps', 'exp': 'exp_fraction'}


def get_initials(s: str, split_char='_'):
    return "".join([x[0] for x in re.split(split_char, s)])


def launch_experiment_by_id(experiment_id: str):
    exp_dict = get_config_by_id(experiment_id)
    if exp_dict is None:
        raise ValueError(f"{experiment_id} is not a valid experiment id")
    exp_dict_orig = exp_dict.copy()
    for attr in ['dataset_names', 'model_names']:
        if attr not in exp_dict.keys():
            raise ValueError(f'You must specify some value for {attr} parameter. It\'s empty.')
    dataset_name_list = exp_dict.pop('dataset_names')
    model_name_list = exp_dict.pop('model_names')
    try:
        base_model_code_list = exp_dict.pop('base_model_code')
    except:
        base_model_code_list = [None]
    if 'params' in exp_dict.keys():
        params = exp_dict.pop('params')
    else:
        params = []

    host_name = socket.gethostname()
    results_dir = os.path.join(f'results', host_name, experiment_id)
    os.makedirs(results_dir, exist_ok=True)
    if "." in host_name:
        host_name = host_name.split(".")[-1]
    try:
        for filepath in os.scandir(results_dir):
            send2trash.send2trash(filepath)
    except:
        pass
    # logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s:%(name)s: %(message)s', datefmt='%d/%m/%y %H:%M:%S',
                        handlers=[logging.FileHandler(os.path.join(results_dir, 'run.log'), mode='a'),
                                  logging.StreamHandler()], force=True)

    def exc_handler(exctype, value, tb):
        logging.exception(''.join(traceback.format_exception(exctype, value, tb)))

    sys.excepthook = exc_handler
    logging.info(f'Parameters of experiment {experiment_id}\n' +
                 json.dumps(exp_dict_orig, default=list).replace(', \"', ',\n\t\"'))
    a = datetime.now()
    logging.info(f'Started logging.')
    to_iter = itertools.product(base_model_code_list, dataset_name_list, model_name_list)
    original_argv = sys.argv.copy()
    for base_model_code, dataset_name, model_name in to_iter:
        gc.collect()
        turn_a = datetime.now()
        logging.info(f'Starting combination:'
                     f' base model: {base_model_code}, dataset_name: {dataset_name}, model_name: {model_name}')
        args = [dataset_name, model_name] + params
        kwargs = {}
        for key in exp_dict.keys():
            kwargs[f'--{key}'] = exp_dict[key]
        if base_model_code is not None:
            kwargs['--base_model_code'] = base_model_code
        execute_experiment(args, kwargs, original_argv)
        turn_b = datetime.now()
        logging.info(
            f'Ended: {base_model_code}, dataset_name: {dataset_name}, model_name: {model_name} in:\n {turn_b - turn_a}')
    b = datetime.now()
    logging.info(f'Ended experiment. It took: {b - a}')


class ExperimentRun(metaclass=Singleton):

    def __init__(self):
        host_name = socket.gethostname()
        if "." in host_name:
            host_name = host_name.split(".")[-1]
        self.host_name = host_name
        self.base_result_dir = f'results/{host_name}/'
        self.time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def get_arguments(self):
        simplefilter(action='ignore', category=FutureWarning)
        arg_parser = ArgumentParser()
        arg_parser.add_argument("dataset")
        arg_parser.add_argument("method")

        arg_parser.add_argument("--metrics", choices=['default',
                                                      'conversion_to_binary_sensitive_attribute'
                                                      ], default='default')
        arg_parser.add_argument("--preprocessing", choices=['default',
                                                            'conversion_to_binary_sensitive_attribute'
                                                            ], default='default')
        # For Fairlearn and Hybrids
        arg_parser.add_argument("--eps", nargs='+', type=float, default=[None])
        arg_parser.add_argument("--constraint_code", choices=['dp', 'eo'], default='dp')
        # For hybrid methods
        arg_parser.add_argument("--exp_fractions", nargs='+', type=float, default=[1])
        arg_parser.add_argument("--grid_fractions", nargs='+', type=float, default=[None])
        arg_parser.add_argument("--exp_grid_ratio", choices=['sqrt', None], default=None, nargs='+')
        arg_parser.add_argument("--no_exp_subset", action="store_false", default=True, dest='exp_subset')
        # Others
        arg_parser.add_argument("--save", default=True)
        arg_parser.add_argument("-v", "--random_seeds", help='random_seeds for everything. (aka random_state) '
                                                             'For models it\'s summed to train_test_fold when cross validating ',
                                default=0,
                                nargs='+', type=int)
        arg_parser.add_argument('--train_test_seeds', help='seeds for train test split', default=None, nargs='+',
                                type=int, action=DeprecateAction)
        arg_parser.add_argument('--test_size',
                                help='when splitting without cross validation train_test_split test_size', default=0.3,
                                type=float)
        arg_parser.add_argument('--split_strategy', help='splitting strategy. default: ',
                                choices=['StratifiedKFold', 'stratified_train_test_split', None],
                                default='StratifiedKFold', type=str)
        arg_parser.add_argument('--train_test_fold', help='train_test_fold to run with k-fold', default=[0, 1, 2],
                                nargs='+',
                                type=int)
        arg_parser.add_argument("--no_run_linprog_step", default=True, dest='run_linprog_step', action='store_false')
        arg_parser.add_argument("--redo_tuning", action="store_true", default=False)
        arg_parser.add_argument("--redo_exp", action="store_true", default=False)
        arg_parser.add_argument("--states", nargs='+', type=str)
        arg_parser.add_argument("--base_model_code", default=None)
        arg_parser.add_argument("--experiment_id", default=None)
        arg_parser.add_argument("--other_params", default={}, type=json.loads,
                                help='dict with keys as name of params to add and list of values to'
                                     ' be iterated combining each value with the other combination of params ')
        # For synthetic data
        arg_parser.add_argument("--num_data_points", type=int)
        arg_parser.add_argument("--num_features", type=int)
        arg_parser.add_argument("--theta", type=float, default=0.5)
        arg_parser.add_argument('--groups')
        arg_parser.add_argument('--group_prob')
        arg_parser.add_argument('--y_prob')
        arg_parser.add_argument('--switch_pos')
        arg_parser.add_argument('--switch_neg')
        # arg_parser.add_argument("--test_ratio", type=float, default=0.3)
        mark_deprecated_help_strings(arg_parser)
        args = arg_parser.parse_args()
        params_to_initials_map = {get_initials(key): key for key in args.__dict__.keys()}
        prm = args.__dict__.copy()
        if args.grid_fractions is not None:
            assert args.exp_grid_ratio is None, '--exp_grid_ratio must not be set if using --grid_fractions'
        if prm['train_test_seeds'] is None:
            prm['train_test_seeds'] = [None]
        print('Configuration:')
        for key, value in prm.items():
            print(f'{key}: {value}')
        print('*' * 100)
        self.prm = prm
        ### Load dataset
        self.dataset_str = prm['dataset']

        self.metrics_dict = metrics.get_metrics_dict(prm['metrics'])

        return prm

    def run(self):
        prm = self.get_arguments()

        datasets = utils_prepare_data.get_dataset(self.dataset_str, prm=self.prm)
        datasets = utils_prepare_data.preprocess_dataset(datasets, prm=self.prm)


        self.datasets = datasets
        X, y, A = datasets[:3]

        for original_random_seed, train_test_seed in itertools.product(prm['random_seeds'], prm['train_test_seeds']):
            if train_test_seed is None:
                train_test_seed = original_random_seed
            self.set_base_data_dict()
            if prm['base_model_code'] is not None:
                self.tuning_step(base_model_code=prm['base_model_code'], X=X, y=y, fractions=prm['exp_fractions'],
                                 random_seed=0,
                                 redo_tuning=prm[
                                     'redo_tuning'])  # TODO: random_seed=0 to simplify, may be corrected later.

            for train_test_fold, datasets_divided in tqdm(enumerate(
                    utils_prepare_data.split_dataset_generator(self.dataset_str, datasets, train_test_seed,
                                                               prm['split_strategy'], test_size=prm['test_size']))):
                print('')
                if train_test_fold not in prm['train_test_fold']:
                    continue
                random_seed = original_random_seed + train_test_fold
                self.data_dict['train_test_seed'] = train_test_seed
                self.data_dict['train_test_fold'] = train_test_fold
                self.data_dict['random_seed'] = random_seed
                params_to_iterate = {'eps': self.prm['eps']}
                params_to_iterate.update(**self.prm['other_params'])
                keys = params_to_iterate.keys()
                for values in itertools.product(*params_to_iterate.values()):
                    turn_params_dict = dict(zip(keys, values))
                    self.data_dict.update(**turn_params_dict)
                    logging.info(f'Starting step: random_seed: {random_seed}, train_test_seed: {train_test_seed}, '
                                 f'train_test_fold: {train_test_fold} \n'
                                 + json.dumps(turn_params_dict, default=list))
                    a = datetime.now()
                    self.run_model(datasets_divided=datasets_divided, random_seed=random_seed,
                                   other_params=turn_params_dict)
                    b = datetime.now()
                    logging.info(f'Ended step in: {b - a}')

    def run_model(self, datasets_divided, random_seed, other_params):
        results_list = []
        if 'hybrids' == self.prm['method']:
            print(
                f"\nRunning Hybrids with random_seed {random_seed} and fractions {self.prm['exp_fractions']}, "
                f"and grid-fraction={self.prm['grid_fractions']}...\n")
            turn_results = self.run_hybrids(*datasets_divided,
                                            exp_fractions=self.prm['exp_fractions'],
                                            grid_fractions=self.prm['grid_fractions'],
                                            exp_subset=self.prm['exp_subset'],
                                            exp_grid_ratio=self.prm['exp_grid_ratio'],
                                            base_model_code=self.prm['base_model_code'],
                                            run_linprog_step=self.prm['run_linprog_step'],
                                            random_seed=random_seed,
                                            constraint_code=self.prm['constraint_code'],
                                            **other_params)
        elif 'unmitigated' == self.prm['method']:
            turn_results = self.run_unmitigated(*datasets_divided,
                                                random_seed=random_seed,
                                                base_model_code=self.prm['base_model_code'])
        # elif 'fairlearn' == self.prm['method']:
        #     turn_results = self.run_fairlearn_full(*datasets_divided, eps=self.prm['eps'],
        #                                            run_linprog_step=self.prm['run_linprog_step'],
        #                                            random_seed=random_seed,
        #                                            base_model_code=self.prm['base_model_code'], )
        else:
            turn_results = self.run_general_fairness_model(*datasets_divided,
                                                           random_seed=random_seed,
                                                           base_model_code=self.prm['base_model_code'], **other_params)
        results_list += turn_results
        results_df = pd.DataFrame(results_list)
        self.save_result(df=results_df)

    def save_result(self, df, name=None, additional_dir=None):
        if self.prm['save'] is not None and self.prm['save'] == 'False':
            print('Not saving...')
            return 0
        assert self.dataset_str is not None
        if self.prm['experiment_id'] is not None and name is None:
            name = self.prm['experiment_id']
            directory = os.path.join(self.base_result_dir, name)
        else:
            directory = os.path.join(self.base_result_dir, self.dataset_str)
        if additional_dir is not None:
            directory = os.path.join(directory, additional_dir)
        os.makedirs(directory, exist_ok=True)
        for prefix in [  # f'{self.time_str}',
            f'last']:
            path = os.path.join(directory, f'{prefix}_{name}_{self.prm["dataset"]}_{self.prm["base_model_code"]}.csv')
            if os.path.isfile(path):
                old_df = pd.read_csv(path)
                df = pd.concat([old_df, df])
            df.to_csv(path, index=False)
            print(f'Saving results in: {path}')

    def set_base_data_dict(self):
        keys = ['dataset', 'method', 'frac', 'model_name', 'base_model_code',
                'constraint_code', 'train_test_fold', 'total_train_size', 'total_test_size', 'phase',
                'time']
        self.data_dict = {key: None for key in keys}
        prm_keys = self.prm.keys()
        for t_key in keys:
            if t_key in prm_keys:
                self.data_dict[t_key] = self.prm[t_key]
            else:
                self.data_dict[t_key] = 'empty'

    def run_hybrids(self, train_data: list, test_data: list, eps,
                    random_seed, exp_fractions, grid_fractions, base_model_code='lr',
                    exp_subset=True, exp_grid_ratio=None, run_linprog_step=True,
                    constraint_code='dp', add_unconstrained=False):
        simplefilter(action='ignore', category=FutureWarning)
        X_train_all, y_train_all, S_train_all = train_data
        X_test_all, y_test_all, S_test_all = test_data
        # Combine all training data into a single data frame
        train_all_X_y_A = pd.concat([pd.DataFrame(x) for x in [X_train_all, y_train_all, S_train_all]], axis=1)
        self.data_dict.update(**{'random_seed': random_seed, 'base_model_code': base_model_code,
                                 'constraint_code': constraint_code,
                                 'total_train_size': X_train_all.shape[0], 'total_test_size': X_test_all.shape[0]})
        run_lp_suffix = '_LP_off' if run_linprog_step is False else ''
        eval_dataset_dict = {'train': [X_train_all, y_train_all, S_train_all],
                             'test': [X_test_all, y_test_all, S_test_all]}
        all_params = dict(X=X_train_all, y=y_train_all, sensitive_features=S_train_all)
        if exp_grid_ratio is not None:
            assert grid_fractions is None
            grid_fractions = exp_grid_ratio

        self.turn_results = []
        base_model = self.load_base_model_with_best_param(base_model_code=base_model_code, fraction=1,
                                                          random_state=random_seed)
        self.data_dict['model_name'] = 'unconstrained'
        unconstrained_model = deepcopy(base_model)
        metrics_res, time_unconstrained_dict, time_eval_dict = self.fit_evaluate_model(
            unconstrained_model, dict(X=X_train_all, y=y_train_all), eval_dataset_dict)
        time_unconstrained_dict['phase'] = 'unconstrained'
        self.add_turn_results(metrics_res, [time_eval_dict, time_unconstrained_dict])
        if not hasattr(eps, '__iter__'):
            eps = [eps]
        to_iter = list(itertools.product(eps, exp_fractions, grid_fractions))
        # Iterations on difference fractions
        for i, (turn_eps, exp_f, grid_f) in tqdm(list(enumerate(to_iter))):
            print('')
            self.data_dict['eps'] = turn_eps
            self.data_dict['exp_frac'] = exp_f
            if type(grid_f) == str:
                if grid_f == 'sqrt':
                    grid_f = np.sqrt(exp_f)
            self.data_dict["grid_frac"] = grid_f
            # self.data_dict['exp_size'] = int(n_data * exp_f)
            # self.data_dict['grid_size'] = int(n_data * grid_f)
            constraint = get_constraint(constraint_code=constraint_code, eps=turn_eps)

            print(f"Processing: fraction {exp_f: <5}, sample {random_seed: ^10} turn_eps: {turn_eps: ^3}")

            # GridSearch data fraction
            if grid_f is not None:
                print(f"GridSearch fraction={grid_f:0<5}")
                grid_sample = train_all_X_y_A.sample(frac=grid_f, random_state=random_seed + 60, replace=False)
                grid_sample = grid_sample.reset_index(drop=True)
                grid_params = dict(X=grid_sample.iloc[:, :-2],
                                   y=grid_sample.iloc[:, -2],
                                   sensitive_features=grid_sample.iloc[:, -1])

            if exp_subset and grid_f is not None:
                exp_sample = grid_sample.sample(frac=exp_f / grid_f, random_state=random_seed + 20, replace=False)
            else:
                exp_sample = train_all_X_y_A.sample(frac=exp_f, random_state=random_seed + 20, replace=False)
            exp_sample = exp_sample.reset_index(drop=True)
            exp_params = dict(X=exp_sample.iloc[:, :-2],
                              y=exp_sample.iloc[:, -2],
                              sensitive_features=exp_sample.iloc[:, -1])
            # Unconstrained on sample
            base_model = self.load_base_model_with_best_param(base_model_code=base_model_code, fraction=1,
                                                              random_state=random_seed)
            self.data_dict['model_name'] = 'unconstrained_frac'
            unconstrained_model_frac = deepcopy(base_model)
            metrics_res, time_uncons_frac_dict, time_eval_dict = self.fit_evaluate_model(
                unconstrained_model_frac, dict(X=exp_params['X'], y=exp_params['y']), eval_dataset_dict)
            self.add_turn_results(metrics_res, [time_eval_dict, time_uncons_frac_dict])

            # Expgrad on sample
            self.data_dict['model_name'] = f'expgrad_fracs{run_lp_suffix}'
            expgrad_frac = ExponentiatedGradientPmf(estimator=deepcopy(base_model), run_linprog_step=run_linprog_step,
                                                    constraints=deepcopy(constraint), eps=turn_eps, nu=1e-6,
                                                    random_state=random_seed)
            metrics_res, time_exp_dict, time_eval_dict = self.fit_evaluate_model(expgrad_frac, exp_params,
                                                                                 eval_dataset_dict)
            exp_data_dict = utils_prepare_data.get_data_from_expgrad(expgrad_frac)
            self.data_dict.update(**exp_data_dict)
            time_exp_dict['phase'] = 'expgrad_fracs'
            print(f"ExponentiatedGradient on subset done in {time_exp_dict['time']}")
            self.add_turn_results(metrics_res, [time_eval_dict, time_exp_dict])

            #################################################################################################
            # 7
            #################################################################################################
            self.data_dict['model_name'] = f'hybrid_7{run_lp_suffix}'
            print(f"Running {self.data_dict['model_name']}")
            subsample_size = int(X_train_all.shape[0] * exp_f)
            expgrad_subsample = ExponentiatedGradientPmf(estimator=deepcopy(base_model),
                                                         run_linprog_step=run_linprog_step,
                                                         constraints=deepcopy(constraint), eps=turn_eps, nu=1e-6,
                                                         subsample=subsample_size, random_state=random_seed)
            metrics_res, time_exp_adaptive_dict, time_eval_dict = self.fit_evaluate_model(expgrad_subsample, all_params,
                                                                                          eval_dataset_dict)
            time_exp_adaptive_dict['phase'] = 'expgrad_fracs'
            exp_data_dict = utils_prepare_data.get_data_from_expgrad(expgrad_subsample)
            self.data_dict.update(**exp_data_dict)
            self.add_turn_results(metrics_res, [time_eval_dict, time_exp_adaptive_dict])

            for turn_expgrad, prefix in [(expgrad_frac, ''), (expgrad_subsample, 'sub_')]:
                turn_time_exp_dict = time_exp_adaptive_dict if prefix == 'sub' else time_exp_dict

                #################################################################################################
                # Hybrid 5: Run LP with full dataset on predictors trained on partial dataset only
                # Get rid
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_5{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                model5 = Hybrid5(constraint=deepcopy(constraint), expgrad_frac=turn_expgrad, eps=turn_eps, )
                metrics_res, time_lp_dict, time_eval_dict = self.fit_evaluate_model(model5, all_params,
                                                                                    eval_dataset_dict)
                time_lp_dict['phase'] = 'lin_prog'
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_lp_dict])

                if add_unconstrained:
                    #################################################################################################
                    # H5 + unconstrained
                    #################################################################################################
                    self.data_dict['model_name'] = f'{prefix}hybrid_5_U{run_lp_suffix}'
                    print(f"Running {self.data_dict['model_name']}")
                    model5.unconstrained_model = unconstrained_model
                    metrics_res, time_lp_dict, time_eval_dict = self.fit_evaluate_model(model5, all_params,
                                                                                        eval_dataset_dict)
                    time_lp_dict['phase'] = 'lin_prog'
                    self.add_turn_results(metrics_res,
                                          [time_eval_dict, turn_time_exp_dict, time_unconstrained_dict, time_lp_dict,
                                           ])
                if grid_f is None:
                    continue

                #################################################################################################
                # Hybrid 1: Just Grid Search -> expgrad partial + grid search
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_1{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                grid_subsample_size = int(X_train_all.shape[0] * grid_f)
                model = Hybrid1(expgrad=turn_expgrad, eps=turn_eps, constraint=deepcopy(constraint),
                                base_model=deepcopy(base_model), grid_subsample=grid_subsample_size)
                metrics_res, time_grid_dict, time_eval_dict = self.fit_evaluate_model(model, grid_params,
                                                                                      eval_dataset_dict)
                time_grid_dict['phase'] = 'grid_frac'
                time_grid_dict['grid_oracle_times'] = model.grid_search_frac.oracle_execution_times_
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_grid_dict])
                grid_search_frac = model.grid_search_frac

                #################################################################################################
                # Hybrid 2: pmf_predict with exp grid weights in grid search
                # Keep this, remove Hybrid 1.
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_2{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                model = Hybrid2(expgrad=turn_expgrad, grid_search_frac=grid_search_frac, eps=turn_eps,
                                constraint=deepcopy(constraint))
                metrics_res, _, time_eval_dict = self.fit_evaluate_model(model, grid_params, eval_dataset_dict)
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_grid_dict])

                #################################################################################################
                # Hybrid 3: re-weight using LP
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_3{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                model = Hybrid3(grid_search_frac=grid_search_frac, eps=turn_eps, constraint=deepcopy(constraint))
                metrics_res, time_lp3_dict, time_eval_dict = self.fit_evaluate_model(model, all_params,
                                                                                     eval_dataset_dict)
                time_lp3_dict['phase'] = 'lin_prog'
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_grid_dict, time_lp3_dict])

                if add_unconstrained:
                    #################################################################################################
                    # Hybrid 3 +U: re-weight using LP + unconstrained
                    #################################################################################################
                    self.data_dict['model_name'] = f'{prefix}hybrid_3_U{run_lp_suffix}'
                    print(f"Running {self.data_dict['model_name']}")
                    model = Hybrid3(grid_search_frac=grid_search_frac, eps=turn_eps, constraint=deepcopy(constraint),
                                    unconstrained_model=unconstrained_model)
                    metrics_res, time_lp3_dict, time_eval_dict = self.fit_evaluate_model(model, all_params,
                                                                                         eval_dataset_dict)
                    time_lp3_dict['phase'] = 'lin_prog'
                    self.add_turn_results(metrics_res,
                                          [time_eval_dict, turn_time_exp_dict, time_grid_dict, time_lp3_dict,
                                           time_unconstrained_dict])

                #################################################################################################
                # Hybrid 4: re-weight only the non-zero weight predictors using LP
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_4{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                model = Hybrid4(expgrad=turn_expgrad, grid_search_frac=grid_search_frac, eps=turn_eps,
                                constraint=deepcopy(constraint))
                metrics_res, time_lp4_dict, time_eval_dict = self.fit_evaluate_model(model, all_params,
                                                                                     eval_dataset_dict)
                time_lp4_dict['phase'] = 'lin_prog'
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_grid_dict, time_lp4_dict])

                #################################################################################################
                # Hybrid 6: exp + grid predictors
                #################################################################################################
                self.data_dict['model_name'] = f'{prefix}hybrid_6{run_lp_suffix}'
                print(f"Running {self.data_dict['model_name']}")
                model = Hybrid3(add_exp_predictors=True, grid_search_frac=grid_search_frac, expgrad=turn_expgrad,
                                eps=turn_eps, constraint=deepcopy(constraint))
                metrics_res, time_lp_dict, time_eval_dict = self.fit_evaluate_model(model, all_params,
                                                                                    eval_dataset_dict)
                time_lp_dict['phase'] = 'lin_prog'
                self.add_turn_results(metrics_res, [time_eval_dict, turn_time_exp_dict, time_grid_dict, time_lp_dict])

                if add_unconstrained:
                    #################################################################################################
                    # Hybrid 6 + U: exp + grid predictors + unconstrained
                    #################################################################################################
                    self.data_dict['model_name'] = f'{prefix}hybrid_6_U{run_lp_suffix}'
                    print(f"Running {self.data_dict['model_name']}")
                    model = Hybrid3(add_exp_predictors=True, grid_search_frac=grid_search_frac, expgrad=turn_expgrad,
                                    eps=turn_eps, constraint=deepcopy(constraint),
                                    unconstrained_model=unconstrained_model)
                    metrics_res, time_lp_dict, time_eval_dict = self.fit_evaluate_model(model, all_params,
                                                                                        eval_dataset_dict)
                    time_lp_dict['phase'] = 'lin_prog'
                    self.add_turn_results(metrics_res,
                                          [time_eval_dict, turn_time_exp_dict, time_grid_dict, time_lp_dict,
                                           time_unconstrained_dict])

            #################################################################################################
            # End models
            #################################################################################################
            print("Fraction processing complete.\n")
        return self.turn_results

    def run_general_fairness_model(self, train_data: list, test_data: list,
                                   **kwargs):
        self.train_data = train_data
        self.test_data = test_data
        model = self.init_fairness_model(**kwargs)
        self.turn_results = []
        self.data_dict.update({'model_name': self.prm['method']})
        self.data_dict.update(**kwargs)
        eval_dataset_dict = {'train': train_data,
                             'test': test_data}
        metrics_res, time_train_dict, time_eval_dict = self.fit_evaluate_model(model, train_data, eval_dataset_dict)
        time_train_dict['phase'] = 'train'
        if hasattr(model, 'get_stats_dict'):
            self.data_dict.update(**model.get_stats_dict())
        self.add_turn_results(metrics_res, [time_train_dict, time_eval_dict])
        return self.turn_results

    def init_fairness_model(self, base_model_code=None, random_seed=None, fraction=1, **kwargs):
        constraint_code_to_name = {'dp': 'demographic_parity',
                                   'eo': 'equalized_odds'}
        base_model = self.load_base_model_with_best_param(base_model_code, random_state=random_seed,
                                                          fraction=fraction)  # TODO: fix random seed. Using 0 to simplify
        constrain_name = constraint_code_to_name[self.prm['constraint_code']]
        return models.get_model(method_str=self.prm['method'], base_model=base_model, constrain_name=constrain_name,
                                random_state=random_seed, datasets=self.datasets, **kwargs)

    def run_unmitigated(self, X_train_all, y_train_all, A_train_all, X_test_all, y_test_all, A_test_all,
                        base_model_code, random_seed=0):
        self.turn_results = []
        eval_dataset_dict = {'train': [X_train_all, y_train_all, A_train_all],
                             'test': [X_test_all, y_test_all, A_test_all]}
        base_model = self.load_base_model_with_best_param(base_model_code=base_model_code, random_state=random_seed)
        train_data = dict(X=X_train_all, y=y_train_all, sensitive_features=A_train_all)
        metrics_res, time_exp_dict, time_eval_dict = self.fit_evaluate_model(base_model, train_data,
                                                                             eval_dataset_dict)
        time_exp_dict['phase'] = 'unconstrained'
        self.add_turn_results(metrics_res, [time_eval_dict, time_exp_dict])
        return self.turn_results

    # Fairlearn on full dataset
    def run_fairlearn_full(self, X_train_all, y_train_all, A_train_all, X_test_all, y_test_all, A_test_all, eps,
                           base_model_code,
                           random_seed=0, run_linprog_step=True):
        assert base_model_code is not None
        self.turn_results = []
        eval_dataset_dict = {'train': [X_train_all, y_train_all, A_train_all],
                             'test': [X_test_all, y_test_all, A_test_all]}
        num_samples = 1
        to_iter = list(itertools.product(eps, [num_samples]))

        for i, (turn_eps, n) in tqdm(list(enumerate(to_iter))):
            print('')
            constraint = get_constraint(constraint_code=self.prm['constraint_code'], eps=turn_eps)
            self.data_dict['eps'] = turn_eps
            base_model = self.load_base_model_with_best_param(base_model_code=base_model_code, random_state=random_seed)
            expgrad_X_logistic = ExponentiatedGradientPmf(base_model,
                                                          constraints=deepcopy(constraint),
                                                          eps=turn_eps, nu=1e-6,
                                                          run_linprog_step=run_linprog_step)
            print("Fitting Exponentiated Gradient on full dataset...")
            train_data = dict(X=X_train_all, y=y_train_all, sensitive_features=A_train_all)
            metrics_res, time_exp_dict, time_eval_dict = self.fit_evaluate_model(expgrad_X_logistic,
                                                                                 train_data,
                                                                                 eval_dataset_dict)
            time_exp_dict['phase'] = 'expgrad'
            exp_data_dict = utils_prepare_data.get_data_from_expgrad(expgrad_X_logistic)
            self.data_dict.update(**exp_data_dict)
            self.add_turn_results(metrics_res, [time_eval_dict, time_exp_dict])

            print(f'Exponentiated Gradient on full dataset : ')
            for key, value in self.data_dict.items():
                if key not in ['model_name', 'phase']:
                    print(f'{key} : {value}')
        return self.turn_results

    def add_turn_results(self, metrics_res, time_dict_list):
        base_dict = self.data_dict
        base_dict.update(**metrics_res)
        for t_time_dict in time_dict_list:
            turn_dict = deepcopy(base_dict)
            turn_dict.update(**t_time_dict)
            self.turn_results.append(turn_dict)

    @staticmethod
    def get_metrics(dataset_dict: dict, predict_method, metrics_dict, return_times=False):
        metrics_res = {}
        time_list = []
        time_dict = {}
        for phase, dataset_list in dataset_dict.items():
            data_values = utils_prepare_data.DataValuesSingleton()
            data_values.set_phase(phase)

            X, Y, S = dataset_list[:3]

            params = inspect.signature(predict_method).parameters.keys()
            data = [X]
            if 'sensitive_features' in params:
                # data += [S]
                t_predict_method = partial(predict_method, sensitive_features=S)
            else:
                t_predict_method = predict_method

            if len(dataset_list) > 3:
                data += dataset_list[3:]
            a = datetime.now()
            y_pred = t_predict_method(*data)
            b = datetime.now()
            time_dict.update(metric=f'{phase}_prediction', time=(b - a).total_seconds())
            time_list.append(deepcopy(time_dict))
            for name, eval_method in metrics_dict.items():
                turn_name = f'{phase}_{name}'
                params = inspect.signature(eval_method).parameters.keys()
                a = datetime.now()
                if 'predict_method' in params:
                    turn_res = eval_method(*dataset_list, predict_method=t_predict_method)
                elif 'y_pred' in params:
                    turn_res = eval_method(*dataset_list, y_pred=y_pred)
                else:
                    raise AssertionError(
                        'Metric method is not taking in input y_pred or predict_method. This is not allowed!')
                b = datetime.now()
                time_dict.update(metric=turn_name, time=(b - a).total_seconds())
                time_list.append(deepcopy(time_dict))
                metrics_res[turn_name] = turn_res
        if return_times:
            return metrics_res, time_list
        return metrics_res

    @staticmethod
    def fit_evaluate_model(model, train_dataset, evaluate_dataset_dict):
        # TODO delete not used option
        # if isinstance(train_dataset, dict):
        #     train_dataset = list(train_dataset.values())
        # a = datetime.now()
        # model.fit(*train_dataset)
        # b = datetime.now()
        logging.info(f'Starting fit...')
        if isinstance(train_dataset, dict):
            a = datetime.now()
            model.fit(**train_dataset)
            b = datetime.now()
        else:
            a = datetime.now()
            model.fit(*train_dataset)
            b = datetime.now()

        logging.info(f'Ended fit:  in: {b - a} ||| Starting evaluation...')
        time_fit_dict = {'time': (b - a).total_seconds(), 'phase': 'train'}

        exp_run = ExperimentRun()

        a = datetime.now()
        metrics_res, metrics_time = ExperimentRun.get_metrics(evaluate_dataset_dict, model.predict,
                                                              metrics_dict=exp_run.metrics_dict,
                                                              return_times=True)
        b = datetime.now()
        logging.info(f'Ended evaluation:  in: {b - a}')
        time_eval_dict = {'time': (b - a).total_seconds(), 'phase': 'evaluation', 'metrics_time': metrics_time}
        return metrics_res, time_fit_dict, time_eval_dict

    def load_base_model_with_best_param(self, base_model_code=None, random_state=None, fraction=1):
        fraction = float(fraction)
        if base_model_code is None:
            base_model_code = self.data_dict['base_model_code']
            if base_model_code is None:
                # raise ValueError(f'base_model_code is None, this is not allowed')
                return None
        if random_state is None:
            random_state = self.data_dict['random_seed']
        best_params = self.load_best_params(base_model_code, fraction=fraction,
                                            random_seed=0)  # todo change random seed. For simplicity in fine tuning it is 0.
        model = models.get_base_model(base_model_code=base_model_code, random_seed=random_state)
        model.set_params(**best_params)
        return model

    def tuning_step(self, base_model_code, X, y, fractions, random_seed=0, redo_tuning=False):
        if base_model_code is None:
            print(f'base_model_code is None. Not starting finetuning.')
            return
        fractions = deepcopy(fractions)
        if 1 not in fractions:  # always add fraction 1 because it is used in run_hybrids
            fractions += [1]
        fractions = [float(x) for x in fractions]
        for turn_frac in (pbar := tqdm(fractions)):
            pbar.set_description(f'fraction: {turn_frac: <5}')
            directory = os.path.join(self.base_result_dir, self.dataset_str, 'tuned_models')
            os.makedirs(directory, exist_ok=True)
            name = f'grid_search_{base_model_code}_rnd{random_seed}_frac{turn_frac}'
            path = os.path.join(directory, name + '.pkl')
            if redo_tuning or not os.path.exists(path):
                print(f'Starting finetuning of {base_model_code}')
                size = X.shape[0]
                sample_mask = np.arange(size)
                if turn_frac != 1:
                    sample_mask, _ = train_test_split(sample_mask, train_size=turn_frac, stratify=y,
                                                      random_state=random_seed, shuffle=True)
                a = datetime.now()
                clf = models.finetune_model(base_model_code, pd.DataFrame(X).iloc[sample_mask],
                                            pd.Series(y.ravel()).iloc[sample_mask],
                                            random_seed=random_seed)
                b = datetime.now()
                joblib.dump(clf, path, compress=1)

                finetuning_time_df = pd.DataFrame(
                    [{'phase': 'grid_searh_finetuning', 'time': (b - a).total_seconds()}])
                self.save_result(finetuning_time_df, 'time_' + name, additional_dir='tuned_models')
            else:
                print(f'Skipping finetuning of {base_model_code}. Already done.')

    def load_best_params(self, base_model_code, fraction, random_seed=0):
        directory = os.path.join(self.base_result_dir, self.dataset_str, 'tuned_models')
        # os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f'grid_search_{base_model_code}_rnd{random_seed}_frac{fraction}.pkl')
        grid_clf = joblib.load(path)
        return grid_clf.best_params_


if __name__ == "__main__":
    exp_run = ExperimentRun()
    exp_run.run()
