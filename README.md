# Fairness Evaluation and Testing Repository

## Introduction

This repository is dedicated to the evaluation and testing of a novel fairness approach in machine learning. The experiments are conducted using a Python file, `run.py`, which launches various configurations stored in the `utils_experiment_parameters.py` file.

## Launching Experiments

To launch an experiment you can run Python script that read experiment parameters from a module (reccomended) or launch the experiment directly from the command line.

Using a Python script is more powerful and flexible, as it allows to launch multiple experiments in a row.
It also allows to define experiment envolving multiple datasets and models in a single experiment.

[//]: # (It allows to use variables to avoid code duplication, and to define the configurations in a single file.)
The configurations are more readable, and it is easier to manage them in a single file.


E.g.
```python
import run

if __name__ == "__main__":
    conf_todo = [
        'experiment_code.0',
        # ... (list of configurations to be executed)
    ]
    for x in conf_todo:
        run.launch_experiment_by_id(x)

```
The `run.py` file contains the code to launch the experiments.
The configurations are read from `utils_experiment_parameters.py` module, and are organized in a list of dictionaries.
e.g.:
```python
import json

# Experiment configurations example
RANDOM_SEEDS_v1 = [0,1]
BASE_EPS_V1 = [0.005]
train_fractions_v1 = [0.001, 0.004, 0.016, 0.063, 0.251, 1]
eta_params_v1 = json.dumps({'eta0': [0.5, 1.0, 2.0], 'run_linprog_step': [False],
                            'max_iter': [5, 10, 20, 50, 100]})

experiment_configurations = [
{
    'experiment_id': 'experiment_code.0', 
    'dataset_names': ['ACSEmployment'], # list of dataset names
    'model_names': ['hybrids'], # list of model names
    'eps': BASE_EPS_V1, # list of epsilons
    'train_fractions': train_fractions_v1, # list of fractions     
    'base_model_code': ['lr', 'lgbm'], # list of base model codes
    'random_seeds': RANDOM_SEEDS_v1, # list of random seeds
    'constraint_code': 'dp', # constraint code
    'model_params': eta_params_v1,
},
]
```

Otherways, you can launch the experiment directly from the command line using the following command:

```bash
python -m run.py ACSEmployment hybrids --experiment_id experiment_code.0 --eps 0.005 --train_fractions 0.001 0.004 0.016 0.063 0.251 1 --random_seeds 0 1 --constraint_code dp --model_params {"eta0": [0.5, 1.0, 2.0], "run_linprog_step": [false], "max_iter": [5, 10, 20, 50, 100]} --base_model_code lr
```

List of available models can be found in the `models.wrappers` module.
It is possible to define new models by importing the model in the `models.wrappers` module and add the name and class as key, value pair in the `additional_models_dict` dictionary.

```python
from example_model import ExampleModel

additional_models_dict = {
    # model_name: model_class,
    'example_model': ExampleModel
}

```

# Links etc.
### Links:
* Parul’s latest nb with documentation: https://github.com/UMass-Responsible-AI/fairlearn/blob/pargupta/experiment/notebooks/hybrid-scalable-model.ipynb 
* Github forking Fairlearn: https://github.com/UMass-Responsible-AI/fairlearn/


### Papers:
* Original Fairlearn: https://arxiv.org/pdf/1803.02453.pdf 
* Maliha’s: https://people.cs.umass.edu/~afariha/papers/FairnessAnalysis.pdf
* Paper using CelabA (and Adult): https://openaccess.thecvf.com/content_CVPR_2019/papers/Quadrianto_Discovering_Fair_Representations_in_the_Data_Domain_CVPR_2019_paper.pdf


### Submission options:
1. VLDB Scalable Data Science (in Research Track)<br>
   8 pages<br>
   Deadlines every 1st of each month (we could submit on February 1st or March 1st)<br>
   Area: Data Management Issues and Support for Machine Learning and AI <br>
   About it: http://wp.sigmod.org/?p=3033<br>
   Call: https://vldb.org/2021/?call-for-research-track<br>
2. DEEM Workshop:<br>
    Intersection of applied machine learning, data management and systems research<br>
    Regular research papers describing preliminary and ongoing research results<br>
    Short (4 pages) or long (10 pages)<br>
    Last year’s: http://deem-workshop.org/ <br>
    Last year’s deadline: March 1st<br>
3. KDD<br>
    Paper Submission: Feb 8th, 2021<br>
    Mining, Inference, and Learning<br>
    Not exactly about “scalability” issues


[//]: # ()
[//]: # (# Scalable Fairlearn)

[//]: # ()
[//]: # ()
[//]: # (## Example Runs)

[//]: # ()
[//]: # (#### Synth)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py synth hybrids --eps=0.05 -n=10000 -f=3 -t=0.5 -t0=0.3 -t1=0.6 -v=1 --test_ratio=0.3 --sample_seeds=0,1,2,3,4,5,6,7,8,9 --train_fractions=0.016 --grid-fraction=0.5)

[//]: # (```)

[//]: # ()
[//]: # (```)

[//]: # (time stdbuf -oL python run.py synth hybrids --eps=0.05 -n=1000000 -f=3 -t=0.5 -t0=0.3 -t1=0.6 -v=1 --test_ratio=0.3 --sample_seeds=0,1,2,3,4,5,6,7,8,9 --train_fractions=0.016 --grid-fraction=0.5)

[//]: # (```)

[//]: # ()
[//]: # (##### Unmitigated)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py synth unmitigated -n=10000 -f=3 -t=0.5 -t0=0.3 -t1=0.6 -v=1 --test_ratio=0.3)

[//]: # (```)

[//]: # ()
[//]: # (##### Fairlearn)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py synth fairlearn --eps=0.05 -f=3 -t=0.5 -t0=0.3 -t1=0.6 -v=1 --test_ratio=0.3 -n=10000)

[//]: # (```)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py synth fairlearn --eps=0.05 -f=3 -t=0.5 -t0=0.3 -t1=0.6 -v=1 --test_ratio=0.3 -n=1000000)

[//]: # (```)

[//]: # ()
[//]: # ()
[//]: # (#### Adult)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py adult unmitigated)

[//]: # (```)

[//]: # ()
[//]: # ()
[//]: # (```)

[//]: # (time stdbuf -oL python run.py adult fairlearn --eps=0.05)

[//]: # (```)

[//]: # (```)

[//]: # (time stdbuf -oL python run.py adult hybrids --eps=0.05 --sample_seeds=0,1,2,3,4,5,6,7,8,9 --train_fractions=0.001,0.004,0.016,0.063,0.251,1 --grid-fraction=0.5)

[//]: # (```)

[//]: # ()
[//]: # ()
[//]: # ()
[//]: # ()
[//]: # (## TODOs)

[//]: # ()
[//]: # (### Complete Hybrid Method)

[//]: # (* Single hybrid method that gets the best of all hybrid methods we have)

[//]: # (* Show that it works on both train and test data)

[//]: # ()
[//]: # (### Scaling experiments)

[//]: # (* Show running time savings when dataset is very large &#40;use synthetic data&#41;)

[//]: # (* Also try logistic regression on large image dataset)

[//]: # ()
[//]: # (### Multiple datasets)

[//]: # (* Show it works on three datasets)

[//]: # (* Try logistic regression on large image dataset)

[//]: # ()
[//]: # (### Increasing number of attributes)

[//]: # (* Decide if we can do that experiment...)

[//]: # ()
[//]: # (### Other things)

[//]: # (* How to subsample for the scalability plot to ensure + and - points are treated equally &#40;stratified data sampling?&#41;)
